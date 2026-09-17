"""Downstream recovery chain, reactor design chain, and CHNO stoichiometry.

Public functions
----------------
required_fermenter_output         — backward pass: target production → fermenter output
design_reactor                    — forward pass: kinetics → vessel sizing (liquid routes)
design_gas_fermentation_reactor   — forward pass variant for gas fermentation route
compute_O2_CO2_H2O_coefficients   — Roels degree-of-reduction + C/N/H atom balances
build_growth_reaction             — assemble mass-basis bst.Reaction for liquid routes
build_autotrophic_growth_reaction — mass coefficients for gas fermentation route (§9.5a)

Scope note — gas fermentation stoichiometry:
    compute_O2_CO2_H2O_coefficients uses the Roels per-C-mol-substrate framework,
    which assumes the carbon source and electron donor are the same molecule
    (fructose, acetate, formate).  For gas fermentation, CO2 is the carbon source
    and H2 is the separate electron donor — the per-C-mol framework does not apply.
    build_autotrophic_growth_reaction() uses the literature molar equation directly
    (Framework §9.5a).  Its primary consumer is the gas fermentation model builder
    (pre-saturation split fraction calculation); PerfusionBioreactor takes molar
    coefficients as constructor arguments and does its own internal mass balance.

Framework §5, §9.5, §9.5a / Spec §common/kinetics.py.
"""

from __future__ import annotations
from math import ceil
import re

import biosteam as bst

from common.operating_hours import effective_operating_hours


# BioSTEAM AbstractStirredTankReactor working-volume fraction (V_wf).
# Confirmed from installed source (abstract_stirred_tank_reactor.py):
#   V_wf_default = 0.8
#   _design(): V_total = ins_F_vol * tau / V_wf; N = ceil(V_total / V_max)
# Including V_wf here so the pre-simulation N_capacity estimate matches what
# BioSTEAM will compute during simulation — Framework §5 step 8.
_V_WF: float = 0.8

# Standard IUPAC atomic weights for CHNO — physical constants, not
# model parameters; no Framework §9 registry entry required.
_ATOMIC_WEIGHTS: dict[str, float] = {
    'C': 12.011,
    'H':  1.008,
    'O': 15.999,
    'N': 14.007,
}

# Matches one element symbol + optional integer or decimal count.
# Supports non-integer subscripts (e.g. C4.09H7.13O1.89N0.76).
_FORMULA_RE = re.compile(r'([A-Z][a-z]?)(\d+\.?\d*)?')


# ---------------------------------------------------------------------------
# Downstream recovery chain — backward pass, run before design_reactor
# ---------------------------------------------------------------------------

def required_fermenter_output(
    target_final_product_MT_yr: float,
    downstream_efficiencies: list[float],
) -> float:
    """Adjust production target for downstream recovery losses.

    25,000 MT/yr is the target on *final packaged SCP*, not fermenter output.
    Each downstream step (centrifuge, dryer, …) discards some mass, so the
    fermenter must be sized to a higher rate.  Walk the battery limits
    backward from product to fermenter, dividing by each step's efficiency.
    Framework §5 Downstream Recovery Chain.

    Parameters
    ----------
    target_final_product_MT_yr:
        Final product target in MT/yr (typically 25,000).
    downstream_efficiencies:
        Fractional recovery/yield per downstream step, ordered from fermenter
        output toward final product — e.g. [eta_centrifuge, eta_dryer].

    Returns
    -------
    float
        Required fermenter CDW output (MT/yr).
    """
    result = target_final_product_MT_yr
    for eta in downstream_efficiencies:
        result /= eta
    return result


# ---------------------------------------------------------------------------
# Reactor design chain — liquid-substrate routes (fructose, acetate, formate)
# ---------------------------------------------------------------------------

def design_reactor(
    mu_max: float,
    Yxs: float,
    max_titer: float,
    epsilon: float,
    D_margin: float,
    target_titer_fraction: float,
    adjusted_fermenter_output_MT_yr: float,
    V_max: float = 355.0,
    S_star_max: float | None = None,
) -> dict:
    """Forward reactor design chain for liquid-substrate routes.

    Implements Framework §5 steps 2–9 (extent/D-margin method).  Every
    intermediate value is derived from the six input parameters — no
    additional constants are introduced here.

    NOTE — target_titer_fraction: a per-route design choice (fraction of
    max_titer targeted as X*) that requires a Framework §9 registry entry
    before the route model builders call this function.  This function is
    complete as written; the gap surfaces in the model builder, not here.

    Parameters
    ----------
    mu_max : h⁻¹
        Maximum specific growth rate (Framework §9.1).
    Yxs : g biomass / g substrate
        Biomass yield on substrate (Framework §9.1).
    max_titer : g/L
        Literature ceiling titer (Framework §9.1).
    epsilon : 0–1
        Substrate conversion extent (Framework §9.2).
    D_margin : fraction
        Fraction of mu_max used as dilution-rate setpoint (Framework §9.2).
    target_titer_fraction : 0–1
        X* = target_titer_fraction × max_titer.  Requires §9 entry.
    adjusted_fermenter_output_MT_yr : MT/yr
        From required_fermenter_output() — NOT the raw 25,000 MT/yr target.
    V_max : m³
        Maximum single-vessel volume; 355 m³ = BioSTEAM default.
    S_star_max : g/L or None
        Inhibition ceiling on residual substrate in the CSTR (Framework §9.1).
        When set, also computes X*_inhibition = Yxs × ε × S_star_max / (1−ε)
        and takes X* = min(X*_titer, X*_inhibition).  None = no constraint
        (fructose, gas fermentation routes).

    Returns
    -------
    dict
        X_star               g/L   — target biomass titer (step 2)
        S0                   g/L   — substrate feed concentration (step 3)
        S_star               g/L   — residual substrate; feeds wastewater load (step 4)
        D                    h⁻¹   — operating dilution rate (step 5)
        tau                  h     — hydraulic residence time = 1/D (step 7)
        Q                    m³/h  — required volumetric throughput (step 6)
        V_total              m³    — total vessel volume across all parallel vessels (step 7)
        N_capacity           int   — vessels needed to meet capacity (step 8)
        N_total              int   — N_capacity + 1 redundancy vessel (step 9)
        inhibition_constrained bool — True when S_star_max ceiling is binding (Framework §5)
    """
    # Step 2 — target titer, with optional inhibition ceiling (Framework §5)
    X_star_titer = target_titer_fraction * max_titer      # g/L, unconstrained titer target
    if S_star_max is not None:
        # Max X* compatible with S_star <= S_star_max in a perfectly mixed CSTR.
        # Derivation: S_star = S0*(1-ε),  S0 = X*/(Yxs*ε)
        #   → X*_inhibition = Yxs * ε * S_star_max / (1-ε)  (Framework §5)
        X_star_inhibition = Yxs * epsilon * S_star_max / (1.0 - epsilon)
        X_star = min(X_star_titer, X_star_inhibition)
        inhibition_constrained = X_star < X_star_titer   # True only when ceiling is binding
    else:
        X_star = X_star_titer
        inhibition_constrained = False

    # Step 3 — feed concentration consistent with X* and ε (Framework §5)
    S0 = X_star / (Yxs * epsilon)                        # g/L

    # Step 4 — residual substrate; steady-state standing concentration
    S_star = S0 * (1.0 - epsilon)                        # g/L

    # Step 5 — dilution rate; conservative margin below washout (Framework §5)
    D   = D_margin * mu_max                               # h⁻¹
    tau = 1.0 / D                                         # h

    # Step 6 — required volumetric throughput:
    #   MT/yr × 1e6 g/MT ÷ h/yr ÷ X_star (g/L) ÷ 1000 L/m³ = m³/h
    Q = (adjusted_fermenter_output_MT_yr * 1e6
         / effective_operating_hours()
         / X_star
         / 1000.0)                                        # m³/h

    # Step 7 — total vessel volume.
    # BioSTEAM AbstractStirredTankReactor: V_total = Q × tau / V_wf
    # (working volume Q×tau, divided by fill fraction V_wf = 0.8).
    # Confirmed from installed source; _V_WF defined at module top.
    V_total = Q * tau / _V_WF                            # m³

    # Step 8 — vessel count (replicates BioSTEAM's _design() auto-solve for
    # pre-simulation seed-train sizing — Framework §5 step 8 note)
    N_capacity = ceil(V_total / V_max)

    # Step 9 — N+1 redundancy vessel (Framework §5a)
    N_total = N_capacity + 1

    return dict(
        X_star=X_star, S0=S0, S_star=S_star,
        D=D, tau=tau, Q=Q,
        V_total=V_total, N_capacity=N_capacity, N_total=N_total,
        inhibition_constrained=inhibition_constrained,
    )


# ---------------------------------------------------------------------------
# Reactor design chain — gas fermentation route (S_f fixed, solve forward)
# ---------------------------------------------------------------------------

def design_gas_fermentation_reactor(
    mu_max: float,
    Yxs: float,
    S_f: float,
    epsilon: float,
    D_margin: float,
    adjusted_fermenter_output_MT_yr: float,
    V_max: float = 355.0,
) -> dict:
    """Forward reactor design chain for the gas fermentation route.

    Identical in structure to design_reactor() except S_f (dissolved H2 feed
    concentration, g/L) is fixed externally by Henry's law at the pre-
    saturation dissolver, so achievable titer X* is solved forward rather
    than feed concentration S0 being solved backward.  Framework §4, §5.

    Parameters
    ----------
    mu_max : h⁻¹
        Autotrophic H2-oxidising maximum growth rate (Framework §9.1).
    Yxs : g biomass / g H2
        Biomass yield on H2 (Framework §9.1).
    S_f : g/L
        Dissolved H2 feed concentration, fixed by Henry's law at the
        droplet contactors (0.0051 g/L at 4 atm per Framework §4a).  Caller
        computes this from operating conditions and passes it in.
    epsilon : 0–1
        H2 conversion extent (Framework §9.2).
    D_margin : fraction
        Fraction of mu_max used as dilution-rate setpoint (Framework §9.2).
    adjusted_fermenter_output_MT_yr : MT/yr
        From required_fermenter_output().
    V_max : m³
        Maximum single-vessel volume.

    Returns
    -------
    dict
        X_star     g/L   — achievable titer = Yxs × S_f × ε (Framework §4)
        S_f        g/L   — dissolved H2 feed concentration (echoed back)
        S_star     g/L   — residual dissolved H2 = S_f × (1 − ε)
        D, tau, Q, V_total, N_capacity, N_total — same as design_reactor()
    """
    # Forward direction: X* is solved from S_f (Framework §4)
    X_star = Yxs * S_f * epsilon                         # g/L
    S_star = S_f * (1.0 - epsilon)                       # g/L residual dissolved H2

    D   = D_margin * mu_max                               # h⁻¹
    tau = 1.0 / D                                         # h

    Q = (adjusted_fermenter_output_MT_yr * 1e6
         / effective_operating_hours()
         / X_star
         / 1000.0)                                        # m³/h

    V_total    = Q * tau / _V_WF                         # m³
    N_capacity = ceil(V_total / V_max)
    N_total    = N_capacity + 1

    return dict(
        X_star=X_star, S_f=S_f, S_star=S_star,
        D=D, tau=tau, Q=Q,
        V_total=V_total, N_capacity=N_capacity, N_total=N_total,
    )


# ---------------------------------------------------------------------------
# CHNO stoichiometry — Roels' method + atom balances (liquid routes only)
# ---------------------------------------------------------------------------

def compute_O2_CO2_H2O_coefficients(
    substrate_formula: str,
    biomass_formula: str,
    Yxs: float,
) -> dict[str, float]:
    """Stoichiometric coefficients per mol substrate for O2, CO2, H2O, NH3.

    Uses Roels' degree-of-reduction method for O2 (Framework §9.5), then
    closes CO2, NH3, and H2O via C, N, and H atom balances.  All inputs
    exist elsewhere in the registry; nothing new is sourced here.
    Framework §9.5 "compute, don't assert."

    Applies to the three liquid-substrate routes only.  See module-level
    scope note for why gas fermentation requires separate treatment.

    The biomass stoichiometric coefficient is set by Yxs directly in the
    BioSTEAM Reaction object (Framework §5); it is NOT returned here.

    Parameters
    ----------
    substrate_formula : str
        Molecular formula of the carbon substrate, e.g. 'C6H12O6'.
    biomass_formula : str
        Empirical biomass formula, e.g. 'C4.09H7.13O1.89N0.76'.
    Yxs : float
        Biomass yield in g biomass / g substrate (Framework §9.1).

    Returns
    -------
    dict[str, float]
        All values positive (mol per mol substrate); caller applies signs
        when writing the BioSTEAM Reaction string:
          'O2'  — mol O2  consumed per mol substrate
          'CO2' — mol CO2 produced per mol substrate
          'NH3' — mol NH3 consumed per mol substrate
          'H2O' — mol H2O produced per mol substrate

    Derivation (per C-mol substrate, Roels — Framework §9.5)
    ---------------------------------------------------------
        γ = 4 + h − 2o − 3n
        O2  = (γ_S − Yxs_Cmol × γ_X) / 4
        CO2 = 1 − Yxs_Cmol                        (C balance)
        NH3 = Yxs_Cmol × n_X − n_S                (N balance)
        H2O = (h_S + 3×NH3 − Yxs_Cmol × h_X) / 2 (H balance)
    Multiply by n_C_substrate → per mol substrate.
    """
    S = _parse_formula(substrate_formula)
    X = _parse_formula(biomass_formula)

    n_C_S = S.get('C', 0.0)
    n_C_X = X.get('C', 0.0)

    if n_C_S == 0:
        raise ValueError(
            f'Substrate formula {substrate_formula!r} contains no carbon.  '
            'Use this function only for liquid-substrate routes (fructose, '
            'acetate, formate).  See module-level scope note for gas fermentation.'
        )

    # Per-C-mol atomic ratios
    hS = S.get('H', 0.0) / n_C_S
    oS = S.get('O', 0.0) / n_C_S
    nS = S.get('N', 0.0) / n_C_S

    hX = X.get('H', 0.0) / n_C_X
    oX = X.get('O', 0.0) / n_C_X
    nX = X.get('N', 0.0) / n_C_X

    # Convert Yxs (g/g) → Yxs_Cmol (C-mol biomass / C-mol substrate)
    MW_S = _formula_mw(S)
    MW_X = _formula_mw(X)
    Yxs_Cmol = Yxs * (MW_S / n_C_S) / (MW_X / n_C_X)

    # Degree of reduction per C-mol (Roels) — Framework §9.5
    gamma_S = 4.0 + hS - 2.0*oS - 3.0*nS
    gamma_X = 4.0 + hX - 2.0*oX - 3.0*nX

    # Stoichiometric coefficients per C-mol substrate
    O2_c  = (gamma_S - Yxs_Cmol * gamma_X) / 4.0
    CO2_c = 1.0 - Yxs_Cmol
    NH3_c = Yxs_Cmol * nX - nS
    H2O_c = (hS + 3.0*NH3_c - Yxs_Cmol * hX) / 2.0

    # Scale to per mol substrate
    return {
        'O2':  O2_c  * n_C_S,
        'CO2': CO2_c * n_C_S,
        'NH3': NH3_c * n_C_S,
        'H2O': H2O_c * n_C_S,
    }


# ---------------------------------------------------------------------------
# Mass-basis growth reaction builder — liquid-substrate routes
# ---------------------------------------------------------------------------

def build_growth_reaction(
    substrate_id: str,
    substrate_formula: str,
    Yxs: float,
    epsilon: float,
    nutrient_coefficient: float,
) -> bst.Reaction:
    """Assemble the mass-basis core growth reaction for a liquid-substrate route.

    Converts the molar output of compute_O2_CO2_H2O_coefficients() to mass
    basis (g per g substrate) and returns a bst.Reaction ready for use in
    ExtentBasedBioreactor.  All coefficient arithmetic is done here once so
    that the three liquid route models do not duplicate it.

    Requires bst.settings.set_thermo() to have been called (MW lookups hit
    the chemicals registry).  Gas fermentation stoichiometry is handled
    separately by PerfusionBioreactor — see module-level scope note.

    Parameters
    ----------
    substrate_id : str
        BioSTEAM chemical ID of the carbon source (e.g. 'Fructose').
    substrate_formula : str
        Molecular formula of the carbon source (e.g. 'C6H12O6').
    Yxs : float
        Biomass yield on substrate, g biomass / g substrate (§9.1).
    epsilon : float
        Substrate conversion extent (§9.2).
    nutrient_coefficient : float
        g Nutrients per g biomass, from build_nutrients_properties() (§9.3).

    Returns
    -------
    bst.Reaction
        Growth reaction: Substrate + Nutrients + NH3 + O2 →
            CNecatorBiomass + CO2 + H2O
        basis='wt', X=epsilon, reactant=substrate_id.
    """
    # Biomass formula from chemicals registry — single source of truth (chemicals.py)
    biomass_formula = bst.settings.chemicals['CNecatorBiomass'].formula

    # Molar coefficients from Roels' degree-of-reduction method (mol/mol substrate)
    molar = compute_O2_CO2_H2O_coefficients(substrate_formula, biomass_formula, Yxs)

    # Convert mol/mol substrate → g/g substrate using MW from chemicals registry
    chems = bst.settings.chemicals
    MW_S  = chems[substrate_id].MW

    def _to_wt(chem_id: str, mol_coeff: float) -> float:
        return mol_coeff * chems[chem_id].MW / MW_S

    O2_wt  = _to_wt('O2',  molar['O2'])
    NH3_wt = _to_wt('NH3', molar['NH3'])
    CO2_wt = _to_wt('CO2', molar['CO2'])
    H2O_wt = _to_wt('H2O', molar['H2O'])

    # Nutrients coefficient: g Nutrients / g substrate = (g/g biomass) × (g biomass / g substrate)
    N_wt = nutrient_coefficient * Yxs

    rxn_str = (
        f'{substrate_id} + {N_wt:.6f} Nutrients + {NH3_wt:.6f} NH3'
        f' + {O2_wt:.6f} O2'
        f' -> {Yxs:.6f} CNecatorBiomass + {CO2_wt:.6f} CO2 + {H2O_wt:.6f} H2O'
    )
    return bst.Reaction(rxn_str, reactant=substrate_id, X=epsilon, basis='wt')


# ---------------------------------------------------------------------------
# Autotrophic stoichiometry — gas fermentation route (§9.5a)
# ---------------------------------------------------------------------------

# Literature molar coefficients per mol C4.09H7.13O1.89N0.76 biomass.
# Source: representative knallgas stoichiometry for C. necator (Framework §9.5a).
# These are module-level constants so the model builder can import them directly
# when constructing PerfusionBioreactor (which takes molar coefficients as args).
GAS_FERM_N_H2  = 21.36   # mol H2  consumed per mol biomass
GAS_FERM_N_O2  =  6.21   # mol O2  consumed per mol biomass
GAS_FERM_N_CO2 =  4.09   # mol CO2 consumed per mol biomass
GAS_FERM_N_NH3 =  0.76   # mol NH3 consumed per mol biomass
GAS_FERM_N_H2O = 18.70   # mol H2O produced per mol biomass


def build_autotrophic_growth_reaction(
    epsilon: float,
    nutrient_coefficient: float,
) -> bst.Reaction:
    """Mass-basis growth reaction for the gas fermentation route.

    Uses the literature molar equation directly (Framework §9.5a) rather than
    Roels' degree-of-reduction method, which does not apply to lithoautotrophic
    growth (H2 electron donor, no carbon; CO2 consumed not produced).

    Primary use: pre-saturation split-fraction calculation in the gas
    fermentation model builder.  PerfusionBioreactor takes the module-level
    GAS_FERM_N_* molar coefficients as constructor arguments and does its own
    internal mass balance — it does not consume this bst.Reaction directly.

    Reaction basis: per g H2 consumed (the cost-driving feedstock, §9.4).
    CO2 appears on the *reactant* side (consumed as carbon source).

    Parameters
    ----------
    epsilon : float
        H2 conversion extent (Framework §9.2).
    nutrient_coefficient : float
        g Nutrients per g biomass, from build_nutrients_properties() (§9.3).

    Returns
    -------
    bst.Reaction
        basis='wt', reactant='H2', X=epsilon:
        H2 + O2 + CO2 + NH3 + Nutrients → CNecatorBiomass + H2O
    """
    chems = bst.settings.chemicals

    MW_H2      = chems['H2'].MW
    MW_O2      = chems['O2'].MW
    MW_CO2     = chems['CO2'].MW
    MW_NH3     = chems['NH3'].MW
    MW_H2O     = chems['H2O'].MW
    MW_biomass = chems['CNecatorBiomass'].MW

    # Mass consumed/produced per mol biomass
    g_H2_per_mol  = GAS_FERM_N_H2  * MW_H2
    g_O2_per_mol  = GAS_FERM_N_O2  * MW_O2
    g_CO2_per_mol = GAS_FERM_N_CO2 * MW_CO2
    g_NH3_per_mol = GAS_FERM_N_NH3 * MW_NH3
    g_H2O_per_mol = GAS_FERM_N_H2O * MW_H2O

    # Convert to per-g-H2 basis (wt reactant = H2) — Framework §9.5a
    Yxs_H2 = MW_biomass / g_H2_per_mol   # 2.26 g CDW / g H2 — Framework §9.1
    O2_wt  = g_O2_per_mol  / g_H2_per_mol
    CO2_wt = g_CO2_per_mol / g_H2_per_mol
    NH3_wt = g_NH3_per_mol / g_H2_per_mol
    H2O_wt = g_H2O_per_mol / g_H2_per_mol

    # Nutrients: g per g H2 = (g Nutrients/g biomass) × (g biomass/g H2)
    N_wt = nutrient_coefficient * Yxs_H2

    rxn_str = (
        f'H2 + {O2_wt:.6f} O2 + {CO2_wt:.6f} CO2'
        f' + {NH3_wt:.6f} NH3 + {N_wt:.6f} Nutrients'
        f' -> {Yxs_H2:.6f} CNecatorBiomass + {H2O_wt:.6f} H2O'
    )
    return bst.Reaction(rxn_str, reactant='H2', X=epsilon, basis='wt')


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_formula(formula: str) -> dict[str, float]:
    """Parse a molecular formula string into an element → atom-count dict.

    Supports non-integer subscripts (e.g. 'C4.09H7.13O1.89N0.76').
    Only CHNO elements are extracted; others are silently ignored.
    """
    chno = {'C', 'H', 'O', 'N'}
    atoms: dict[str, float] = {}
    for match in _FORMULA_RE.finditer(formula):
        element = match.group(1)
        if element not in chno:
            continue
        count_str = match.group(2)
        count = float(count_str) if count_str else 1.0
        atoms[element] = atoms.get(element, 0.0) + count
    return atoms


def _formula_mw(atoms: dict[str, float]) -> float:
    """MW (g/mol) from an element-count dict using standard CHNO atomic weights."""
    return sum(atoms.get(e, 0.0) * w for e, w in _ATOMIC_WEIGHTS.items())
