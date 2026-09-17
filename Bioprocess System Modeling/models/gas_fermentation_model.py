"""Gas fermentation route SCP flowsheet builder.

Public function
---------------
build_gas_fermentation_system(params, economics) -> tuple[bst.System, dict[str, float]]

Flowsheet
---------
Liquid media preparation — nutrients + NH3 + water → mixing → UF sterilization →
pressurisation → split to two droplet columns → recombine → fermentation → recovery:

  nutrients_feed → ST102 (StorageTank) ─┐
  nh3_feed       → ST103 (StorageTank) ─┤→ M101 (Mixer)
  water_feed     ────────────────────────┤
  recycle_water  ──────────────────────→ ┘
    → UF101 (UltrafiltrationSterilizer — Guo et al. 2014)
    → P101  (Pump, 4 atm)
    → SP101 (Splitter: f → DC101 liquid in; (1-f) → DC102 liquid in)

  h2_feed     → CP101 (IsentropicCompressor) → HX101 (HXutility) → DC101 (DropletColumn, H2 dissolved) ─┐
  co2_o2_feed → CP102 (IsentropicCompressor) → HX102 (HXutility) → DC102 (DropletColumn, O2+CO2)        ─┤→ MX101 (Mixer)
    → R101  (PerfusionBioreactor, autotrophic C. necator)
    → C101  (SolidsCentrifuge)
    → D101  (SprayDryer)
    → ST104 (StorageTank — dried SCP product)
    → WWT101 (wastewater Mixer)
    → WWT102 (Splitter — 99% organics → sludge; 100% H2O → treated water)
    → RCY101 (Splitter — 75 % treated water → recycle_water; 25 % → discharge)
    → recycle_water (back to M101)

Seed media sterilization track:
  seed_substrate_feed → ST201 ─┐  (fructose — heterotrophic seed culture, user-confirmed 2026-08-07)
  seed_nutrients_feed → ST202 ─┤→ SM101 → SHX101 → SHX102 → SSP101/SSP102
  seed_nh3_feed       → ST203 ─┘     → SR101 / SR102 / SR103

Key differences from liquid-substrate routes (Framework §4a)
-------------------------------------------------------------
1. UF membrane sterilization (UF101) replaces heat sterilization (HX101/HX102) used in the
   three liquid routes and seed train. Costed from Guo, Englehardt & Wu (2014) Water Sci.
   Technol. WST-EM13819R1 Table 1 / §2.5. O&M added to FOC via SCPTEA._FOC pickup.
2. Water recycle at 75 % (WWT_WATER_RECYCLE_FRACTION) — same as liquid-substrate routes.
   Gas fermentation produces net H2O (GAS_FERM_N_H2O = 18.70 mol/mol biomass), but at
   75 % recycle the 25 % purge prevents unbounded accumulation — the loop is a
   contraction mapping (gain = 0.75 < 1).  recycle_water is wired from RCY101.outs[0]
   back to M101 (identical pattern to fructose/acetate/formate routes).
3. Substrate (H2) is a dissolved gas, not a liquid feedstock.  Henry's law at 4 atm
   fixes the achievable dissolved H2 concentration: S_f_H2 = 0.0051 g/L.  X* is
   solved forward from S_f (not backward from a target titer).
4. Pre-saturation requires two separate droplet columns (DC101 for H2; DC102 for
   CO2+O2) to prevent H2/O2 contact in the gas phase (explosion hazard, Framework §4a).
5. PerfusionBioreactor replaces ExtentBasedBioreactor.  Perfusion decouples HRT from
   SRT, achieving ~25x higher cell density than a simple CSTR — but the total liquid
   throughput Q is the same.  This reduces vessel count (capital) without reducing
   water cost (operational).  The resulting economics illustrate the inherent mass-
   transfer limitation of gas-phase H2 fermentation.
6. H2, CO2, and O2 are continuous gas feeds (assumed on-site generation); no gas-
   phase storage tanks are modeled — a conservative FCI underestimate.

No .simulate(), TEA build, or export calls — those are run_models.py's job.
(Framework §10 / Spec §models/{route}_model.py)

Feed streams (all priced)
--------------------------
h2_feed      : H2 at h2_kgh kg/h                     → price = feedstock_price ($/kg H2)
co2_o2_feed  : CO2+O2 gas feed to DC102              → price = 0.0 (no registry entry)
nutrients_feed: Nutrients stoichiometric for X*      → price = composite_price
nh3_feed     : NH3 stoichiometric for growth         → price = ammonia_price
water_feed   : Fresh water makeup (balance to Q*1000) → price = water_price/1000 ($/kg)
recycle_water: WWT recycle (75 % of treated H2O)     → price = 0.0

Units
-----
ST102  — bst.StorageTank        : nutrients storage (7 days — Framework §9.2)
ST103  — bst.StorageTank        : ammonia storage (7 days — Framework §9.2)
M101   — bst.Mixer              : inline feed blender (no capital — feed is ~pure water at 0.004 g/L nutrients)
UF101  — UltrafiltrationSterilizer : UF membrane sterilizer (Guo et al. 2014, Framework §4a)
P101   — bst.Pump               : pressurises liquid feed to 4 atm (Framework §4a)
SP101  — bst.Splitter           : splits liquid to DC101 (H2) and DC102 (CO2+O2)
DC101  — DropletColumn          : closed H2 pre-saturation vessel, 4 atm (Framework §4a)
DC102  — DropletColumn          : closed CO2+O2 pre-saturation vessel, 4 atm (Framework §4a)
HX101  — bst.HXutility          : H2 gas aftercooler, ~250 °C → 30 °C (Framework §4a)
HX102  — bst.HXutility          : CO2/O2 gas aftercooler, ~200 °C → 30 °C (Framework §4a)
MX101  — bst.Mixer              : recombines H2-sat and O2/CO2-sat streams
R101   — PerfusionBioreactor    : autotrophic perfusion fermenter at 4 atm (Framework §4a)
C101   — bst.SolidsCentrifuge   : 95% biomass recovery, 75% cake moisture
D101   — bst.SprayDryer         : moisture removal to 5% final moisture
ST104  — bst.StorageTank        : dried SCP product storage (7 days — Framework §9.2)
ST201  — bst.StorageTank        : seed fructose storage (7 days — Framework §9.2; seed grown heterotrophically)
ST202  — bst.StorageTank        : seed nutrients storage (7 days — Framework §9.2)
ST203  — bst.StorageTank        : seed ammonia storage (7 days — Framework §9.2)
SM101  — bst.MixTank            : seed media mixer (tau=1 h)
SHX101 — bst.HXutility         : seed media heater to 134 °C (sterilization)
SHX102 — bst.HXutility         : seed media cooler to 30 °C (fermentation T)
SSP101 — bst.Splitter           : splits sterilized seed media to SR103 (outs[0]) and SSP102 (outs[1])
SSP102 — bst.Splitter           : splits remainder to SR101 (outs[0]) and SR102 (outs[1])
SR101  — SeedBioreactor         : Stage-1 seed fermenter (single sterilized inlet)
SR102  — SeedBioreactor         : Stage-2 seed fermenter (single sterilized inlet)
SR103  — SeedBioreactor         : Stage-3 seed fermenter (single sterilized inlet)
WWT101 — bst.Mixer              : combines centrifuge effluent + seed wastes (inline, zero capital)
WWT102 — bst.Splitter           : 99% organics → sludge; 100% H2O → treated water
RCY101 — bst.Splitter           : 75 % H2O → recycle_water; 25 % → discharge
"""

from __future__ import annotations
import math

import biosteam as bst

from common.chemicals import build_chemicals
from common.economics import EconomicBasis, configure_utility_prices
from common.sterilization import UltrafiltrationSterilizer
from common.kinetics import (
    GAS_FERM_N_CO2,
    GAS_FERM_N_H2,
    GAS_FERM_N_H2O,
    GAS_FERM_N_NH3,
    GAS_FERM_N_O2,
    build_autotrophic_growth_reaction,
    build_growth_reaction,
    compute_O2_CO2_H2O_coefficients,
    design_gas_fermentation_reactor,
    required_fermenter_output,
)
from common.nutrients import build_nutrients_properties
from common.operating_hours import effective_operating_hours
from common.parameters import (
    CENTRIFUGE_CAKE_MOISTURE,
    CENTRIFUGE_RECOVERY,
    DC_Q_MAX_M3S,
    NH3_NUTRIENTS_EXCESS,
    NUTRIENTS_RECIPE,
    PRODUCTION_TARGET_MT_YR,
    SPRAY_DRYER_MOISTURE,
    STORAGE_TANK_TAU,
    T_FERMENTATION_K,
    WWT_WATER_RECYCLE_FRACTION,
    RouteParams,
    get as get_route_params,
)
from common.seed_train import build_seed_train
from common.wastewater import build_wastewater_treatment
from perfusion_bioreactor.droplet_column import DropletColumn
from perfusion_bioreactor.unitwithauxiliary import PerfusionBioreactor


# ---------------------------------------------------------------------------
# Module-level constants — Framework §4a
# ---------------------------------------------------------------------------

_S_F_H2        = 0.0051  # g/L  — dissolved H2 at 4 atm (Henry's law, Framework §4a)
_S_F_O2        = 0.11    # g/L  — dissolved O2 at 4 atm (DC102 design target, Framework §4a)
_P_PRE_SAT_ATM = 4.0     # atm  — droplet column operating pressure (Framework §4a)
_P_GAS_FEED_ATM = 4.5   # atm  — gas feed delivery pressure; 0.5 atm above column
                          #        operating pressure to drive gas into pressurised liquid
                          #        (Framework §4a, user-confirmed 2026-08-12)
_ETA_GAS_COMP   = 0.70   # —    isentropic efficiency — BioSTEAM default for IsentropicCompressor
                          #        (Framework §4a, user-confirmed 2026-08-12)
_ETA           = 0.97    # —    cell-retention efficiency of perfusion centrifuge (Framework §4a)
_BLEED_FRAC    = 0.20    # —    bleed dilution rate as fraction of mu (Framework §4a)
_V_MAX_M3      = 355.0   # m³   — single vessel maximum volume (BioSTEAM default, Framework §5)
_V_WF          = 0.8     # —    working volume fraction (BioSTEAM ASTR default, Framework §5)


def build_gas_fermentation_system(
    params: RouteParams,
    economics: EconomicBasis,
) -> tuple[bst.System, dict[str, float]]:
    """Build and return the gas fermentation route BioSTEAM system.

    Does NOT call system.simulate(), build a TEA, or export results.
    All numeric parameters originate from Framework §9 registry entries.

    bst.System uses __slots__ and cannot hold arbitrary attributes, so
    nutrients_mass_fractions is returned as a second element of the tuple
    rather than attached to the system object.  Caller passes it directly to
    common.export.export_results() — Framework §8.

    Parameters
    ----------
    params : RouteParams
        Per-route kinetics and design parameters from common.parameters.get('gas_fermentation').
    economics : EconomicBasis
        Shared economic parameters from common.parameters.ECONOMICS.

    Returns
    -------
    system : bst.System
        Fully constructed (unsimulated) BioSTEAM system.
    nutrients_mass_fractions : dict[str, float]
        Component → mass fraction; passed to export_results() to unlump the
        Nutrients stream in the LCI stream table (Framework §8).
    """
    # ------------------------------------------------------------------
    # 1. Register chemicals — must precede any stream or unit construction
    # ------------------------------------------------------------------
    chems = build_chemicals()
    bst.settings.set_thermo(chems)
    configure_utility_prices(economics)        # Framework §9.4 — must precede simulate()

    # ------------------------------------------------------------------
    # 2. Nutrients derived properties
    # ------------------------------------------------------------------
    composite_price, nutrient_coeff, nutrients_mass_fractions = build_nutrients_properties(
        concentrations=NUTRIENTS_RECIPE.concentrations,
        prices=NUTRIENTS_RECIPE.prices,
        achieved_titer=NUTRIENTS_RECIPE.achieved_titer,
    )

    # ------------------------------------------------------------------
    # 3. Downstream recovery chain → required fermenter output
    #    Efficiencies: centrifuge=0.95, dryer=1.00 (Framework §9.2)
    # ------------------------------------------------------------------
    adjusted_output_MT_yr = required_fermenter_output(
        target_final_product_MT_yr=PRODUCTION_TARGET_MT_YR,
        downstream_efficiencies=[CENTRIFUGE_RECOVERY],  # dryer = 100%
    )

    # ------------------------------------------------------------------
    # 4. Reactor design chain — gas fermentation (Framework §4, §5)
    #    S_f_H2 fixed by Henry's law; X* solved forward (not backward).
    #    Q is extremely large because X* << X* of liquid routes — this is
    #    the intended finding: pre-saturation is inherently mass-transfer limited.
    # ------------------------------------------------------------------
    d = design_gas_fermentation_reactor(
        mu_max=params.mu_max,
        Yxs=params.Yxs,
        S_f=_S_F_H2,
        epsilon=params.epsilon,
        D_margin=params.D_margin,
        adjusted_fermenter_output_MT_yr=adjusted_output_MT_yr,
    )
    Q      = d['Q']       # m³/h — volumetric liquid throughput (extremely large)
    X_star = d['X_star']  # g/L  — CSTR-design achievable titer (low due to S_f limit)

    # ------------------------------------------------------------------
    # 5. Molecular weights and stoichiometric mass ratios
    #    GAS_FERM_N_* molar coefficients (mol/mol biomass) — Framework §9.5a
    # ------------------------------------------------------------------
    MW_H2      = chems['H2'].MW
    MW_O2      = chems['O2'].MW
    MW_CO2     = chems['CO2'].MW
    MW_NH3     = chems['NH3'].MW
    MW_H2O     = chems['H2O'].MW
    MW_biomass = chems['CNecatorBiomass'].MW

    g_H2_per_gCDW  = GAS_FERM_N_H2  * MW_H2  / MW_biomass   # g H2  per g CDW
    g_O2_per_gCDW  = GAS_FERM_N_O2  * MW_O2  / MW_biomass   # g O2  per g CDW
    g_NH3_per_gCDW = GAS_FERM_N_NH3 * MW_NH3 / MW_biomass   # g NH3 per g CDW

    # Y_mol: g CDW per mol H2 — from stoichiometric molar equation (Framework §9.5a)
    Y_mol = MW_biomass / GAS_FERM_N_H2                        # g CDW/mol H2

    # ------------------------------------------------------------------
    # 5a. Perfusion operating point and working volume
    # ------------------------------------------------------------------
    mu_op   = params.D_margin * params.mu_max                 # h⁻¹ — operating growth rate
    V_max_L = _V_MAX_M3 * _V_WF * 1000.0                     # L   — working volume per vessel

    # Specific H2 uptake rate (maintenance = 0, Framework §9.5a)
    Y_max = Y_mol / MW_H2                                     # g CDW/g H2 (= params.Yxs)
    q_s   = mu_op / Y_max                                     # g H2/g CDW/h

    # ------------------------------------------------------------------
    # 5b. Dissolved CO2 design concentration (compute, don't assert)
    #     Stoichiometric ratio: S_f_CO2/S_f_O2 = (n_CO2 * MW_CO2) / (n_O2 * MW_O2)
    #     Ensures CO2 and O2 dissolve in proportion to bacterial demand.
    # ------------------------------------------------------------------
    S_f_CO2 = (GAS_FERM_N_CO2 * MW_CO2) / (GAS_FERM_N_O2 * MW_O2) * _S_F_O2   # g/L

    # ------------------------------------------------------------------
    # 5c. DC101/DC102 liquid split fraction (compute, don't assert)
    #     Derived from stoichiometric H2/O2 parity at the R101 inlet:
    #       f * S_f_H2 / g_H2_per_gCDW = (1-f) * S_f_O2 / g_O2_per_gCDW
    #     Rearranged:
    #       f = (S_f_O2 * g_H2_per_gCDW)
    #           / (S_f_H2 * g_O2_per_gCDW + S_f_O2 * g_H2_per_gCDW)
    #     Framework §4a.  Note: neither gas fully satisfies the stoichiometry at
    #     4 atm; the ~8% shortfall (inherent to Henry's law limits at this pressure)
    #     is flagged by PerfusionBioreactor's feedstock sufficiency check.
    # ------------------------------------------------------------------
    f = (_S_F_O2 * g_H2_per_gCDW) / (
        _S_F_H2 * g_O2_per_gCDW + _S_F_O2 * g_H2_per_gCDW
    )    # fraction of Q routed through DC101 (H2 side)

    # ------------------------------------------------------------------
    # 5c-i. Correct Q for DC101/DC102 liquid split (Framework §4a)
    #     design_gas_fermentation_reactor uses S_f_H2 as the substrate entering
    #     R101, implicitly assuming all Q carries dissolved H2.  In the actual
    #     flowsheet, only fraction f of Q passes through DC101 and picks up H2;
    #     the remaining (1-f) passes through DC102 and carries only O2+CO2.
    #     After recombination in MX101, [H2]_inlet = f × S_f_H2 < S_f_H2.
    #
    #     Production per vessel = Yxs × D_total × S_f_inlet × epsilon × V_max.
    #     With N = Q / (D_total × V_max) vessels, total = Q × Yxs × S_f_inlet × epsilon.
    #     Setting this equal to the CSTR design production Q_design × X_star:
    #         Q_corrected × f × S_f_H2 = Q_design × S_f_H2  →  Q_corrected = Q_design / f
    #     This ensures each perfusion vessel receives D_perf of liquid and operates
    #     at its design cell density.  Framework §4a split geometry.
    #
    #     Q_design (CSTR basis) remains the reference for production-proportional
    #     quantities (nutrients, NH3); corrected Q drives water makeup and all vessel
    #     sizing.  The correction strengthens the inherent mass-transfer finding:
    #     total process liquid is ~1/f ≈ 1.20× larger than the CSTR estimate.
    # ------------------------------------------------------------------
    Q_design = Q              # m³/h — CSTR-basis, proportional to production target
    Q        = Q_design / f   # m³/h — corrected for DC split; total process liquid

    # ------------------------------------------------------------------
    # 5d. Pre-simulation N estimate for seed train sizing
    #     PerfusionBioreactor computes N internally during simulate(); this
    #     estimate uses perfusion kinetics to size seed vessels to the actual
    #     perfusion vessel count (not the much larger CSTR design N from d['N_total']).
    #     Method replicates PerfusionBioreactor._apply_production_target_scaling().
    # ------------------------------------------------------------------
    D_b_est    = _BLEED_FRAC * mu_op                          # h⁻¹ — bleed dilution rate
    D_perf_est = (mu_op - D_b_est) / (1.0 - _ETA)            # h⁻¹ — perfusion dilution rate

    # Effective H2 concentration at R101 inlet after MX101 mixing:
    # DC101 carries f*Q at S_f_H2; DC102 carries (1-f)*Q with no H2.
    # Combined: [H2] = f * S_f_H2.
    S_f_inlet = f * _S_F_H2                                   # g/L — H2 at R101 inlet

    # Estimated perfusion cell density (epsilon close to 1 → S_f - S ≈ S_f)
    X_perf_est = D_perf_est * S_f_inlet * params.epsilon / q_s    # g/L

    op_hours         = effective_operating_hours()
    CDW_per_vessel_h = mu_op * X_perf_est * V_max_L           # g CDW/h per vessel
    N_perf_capacity  = math.ceil(
        adjusted_output_MT_yr * 1e6 / op_hours / CDW_per_vessel_h
    )
    N_perf_total = N_perf_capacity + 1                         # +1 redundancy — Framework §5a

    V_work_prod = _V_MAX_M3 * _V_WF                           # m³ per production vessel

    # ------------------------------------------------------------------
    # 5e. NH3 mass ratio for feed sizing (g NH3 per g H2, mass basis)
    # ------------------------------------------------------------------
    nh3_wt = g_NH3_per_gCDW * params.Yxs                     # g NH3/g H2

    # ------------------------------------------------------------------
    # 6. Growth reaction for seed bioreactors
    #    PerfusionBioreactor handles its own internal mass balance via the
    #    GAS_FERM_N_* molar coefficients; autotrophic_rxn is used only in
    #    SR101/SR102/SR103 (SeedBioreactor extends AeratedBioreactor).
    #    CO2 appears as a reactant in autotrophic_rxn but AeratedBioreactor
    #    aerates only O2 — a known simplification acceptable for TEA sizing
    #    of small seed vessels (Framework §6).
    # ------------------------------------------------------------------
    autotrophic_rxn = build_autotrophic_growth_reaction(
        epsilon=params.epsilon,
        nutrient_coefficient=nutrient_coeff,
    )

    # ------------------------------------------------------------------
    # 7. Feed stream mass flows
    #    Gas feeds: mass flow = Q_liquid_through_column * dissolved_concentration
    #    (closed vessel — all gas dissolves into liquid outlet, Framework §4a)
    #    Unit note: Q [m³/h] * S_f [g/L] = Q * S_f [kg/h]  (1 g/L = 1 kg/m³)
    # ------------------------------------------------------------------
    h2_kgh  = f     * Q * _S_F_H2   # kg/h H2  dissolved in DC101
    o2_kgh  = (1-f) * Q * _S_F_O2   # kg/h O2  dissolved in DC102
    co2_kgh = (1-f) * Q * S_f_CO2   # kg/h CO2 dissolved in DC102

    # Liquid feed to M101 (nutrients + NH3 + water; H2 fed directly to DC101)
    nutrients_kgh = nutrient_coeff * X_star * Q_design * (1.0 + NH3_NUTRIENTS_EXCESS)         # kg/h — production-proportional
    nh3_kgh       = nh3_wt * _S_F_H2 * params.epsilon * Q_design * (1.0 + NH3_NUTRIENTS_EXCESS)  # kg/h — production-proportional
    # 5 % supplement above stoichiometric for co-reactants — Framework §9.2.
    # Ensures growth is never N- or mineral-limited; standard practice for
    # continuous culture on mineral-salt media (Doran 2012, §12).
    water_kgh     = Q * 1000.0  # kg/h — Q is the water throughput (m³/h); solutes are additional mass

    # ------------------------------------------------------------------
    # 7a. Analytical steady-state water recycle (Framework §9.2)
    #     Gas fermentation produces net H2O (GAS_FERM_N_H2O mol/mol biomass),
    #     but at 75 % recycle a 25 % purge prevents unbounded accumulation —
    #     the loop is a contraction mapping (gain = 0.75 < 1 → converges).
    #     Only 100 % recycle would be unstable.  Same logic as liquid-substrate
    #     routes (fructose/acetate/formate).
    #
    #     g_H2O_per_gCDW : g H2O produced per g CDW (stoichiometric, Framework §9.5a)
    #     W_rxn          : kg/h H2O generated by autotrophic growth
    #     W_product      : kg/h H2O retained in dried SCP product (5 % moisture)
    #     recycle_ss_kgh : kg/h recycle water at steady state (seed for convergence)
    #     makeup_kgh     : kg/h fresh water makeup (replaces full water_kgh in feed)
    # ------------------------------------------------------------------
    g_H2O_per_gCDW = GAS_FERM_N_H2O * MW_H2O / MW_biomass        # g H2O / g CDW produced
    W_rxn           = g_H2O_per_gCDW * X_star * Q_design          # kg/h H2O from reaction
    biomass_after_centrifuge = X_star * Q_design * CENTRIFUGE_RECOVERY   # kg/h CDW to dryer
    W_product       = (biomass_after_centrifuge
                       * SPRAY_DRYER_MOISTURE / (1.0 - SPRAY_DRYER_MOISTURE))  # kg/h in dried SCP
    recycle_ss_kgh  = WWT_WATER_RECYCLE_FRACTION * (water_kgh + W_rxn - W_product)  # kg/h
    makeup_kgh      = max(0.0, water_kgh - recycle_ss_kgh)         # kg/h fresh-water makeup

    # ------------------------------------------------------------------
    # 8. Feed streams
    # ------------------------------------------------------------------
    # H2 feed to DC101 — priced at feedstock_price (Framework §9.4)
    # phase='g': H2 is a permanent gas; required for IsentropicCompressor entropy
    # calculation (CP101 sets out.S = feed.S then solves T; liquid-phase S gives
    # zero isentropic work because thermosteam's liquid S is pressure-independent).
    h2_feed = bst.Stream(
        'h2_feed',
        H2=h2_kgh,
        units='kg/hr',
        phase='g',                             # gas phase — required for CP101 thermodynamics
        price=params.feedstock_price,          # $/kg H2 — Framework §9.4
    )
    # CO2+O2 feed to DC102 — no price in Framework §9 registry; set to 0.0
    # phase='g': CO2 and O2 are gases at ambient conditions (same rationale as h2_feed).
    co2_o2_feed = bst.Stream(
        'co2_o2_feed',
        CO2=co2_kgh, O2=o2_kgh,
        units='kg/hr',
        phase='g',                             # gas phase — required for CP102 thermodynamics
        price=0.0,                             # no registry entry for CO2/O2 — §9.4
    )

    # CP101 — H2 feed compressor: atmospheric → 4.5 atm (Framework §4a)
    #   Raises H2 from assumed-atmospheric generation exit pressure to 0.5 atm
    #   overpressure needed to drive dissolution into the 4 atm DC101 liquid.
    h2_compressor = bst.IsentropicCompressor(
        'CP101',
        ins=h2_feed,
        P=_P_GAS_FEED_ATM * 101325,    # atm → Pa
        eta=_ETA_GAS_COMP,             # Framework §4a
    )
    # CP102 — CO2/O2 feed compressor: atmospheric → 4.5 atm (Framework §4a)
    co2o2_compressor = bst.IsentropicCompressor(
        'CP102',
        ins=co2_o2_feed,
        P=_P_GAS_FEED_ATM * 101325,    # atm → Pa
        eta=_ETA_GAS_COMP,             # Framework §4a
    )

    # HX101 — H2 gas aftercooler: CP101 outlet (~250 °C) → 30 °C (Framework §4a)
    #   BioSTEAM assigns chilled water (target T < cooling water supply 32.2 °C).
    #   Same cool_only pattern as HX102 in fructose/liquid routes.
    h2_aftercooler = bst.HXutility(
        'HX101',
        ins=h2_compressor-0,
        T=T_FERMENTATION_K,    # 303.15 K — Framework §9.2
        cool_only=True,        # gas exits compressor hotter than cooling water supply
    )
    # HX102 — CO2/O2 gas aftercooler: CP102 outlet (~200 °C) → 30 °C (Framework §4a)
    co2o2_aftercooler = bst.HXutility(
        'HX102',
        ins=co2o2_compressor-0,
        T=T_FERMENTATION_K,    # 303.15 K — Framework §9.2
        cool_only=True,
    )

    nutrients_feed = bst.Stream(
        'nutrients_feed',
        Nutrients=nutrients_kgh,
        units='kg/hr',
        price=composite_price,                 # $/kg — computed from recipe — §9.3
    )
    nh3_feed = bst.Stream(
        'nh3_feed',
        NH3=nh3_kgh,
        units='kg/hr',
        price=economics.ammonia_price,         # $/kg — Framework §9.4
    )
    # Fresh water makeup — covers the portion of process-water demand not supplied
    # by the WWT recycle.  Flow pre-computed analytically so the bioreactor runs
    # at the designed Q × 1000 total throughput.
    water_feed = bst.Stream(
        'water_feed',
        H2O=makeup_kgh,
        units='kg/hr',
        price=economics.water_price / 1000.0,  # $/m³ ÷ 1000 kg/m³ → $/kg — §9.4
    )

    # Recycle water tear stream — pre-created so it can be wired into M101.ins
    # before RCY101 is constructed.  RCY101.outs[0] is assigned this same object
    # inside build_wastewater_treatment(), completing the recycle topology.
    # Seeded at the analytical steady-state value for fast BioSTEAM convergence.
    # price = 0: no purchase cost; stream is supplied by the WWT recycle loop.
    recycle_water = bst.Stream(
        'recycle_water',
        H2O=recycle_ss_kgh,
        units='kg/hr',
        price=0.0,
    )

    # ------------------------------------------------------------------
    # 8a. Feedstock storage tanks (Framework §9.2: STORAGE_TANK_TAU = 168 h = 7 days)
    #     H2, O2, CO2 are continuous gas feeds (on-site generation assumed);
    #     gas-phase storage vessels are not modeled — conservative FCI underestimate.
    # ------------------------------------------------------------------
    nutrients_storage = bst.StorageTank('ST102', ins=nutrients_feed, tau=STORAGE_TANK_TAU)
    nh3_storage       = bst.StorageTank('ST103', ins=nh3_feed,       tau=STORAGE_TANK_TAU)

    # ------------------------------------------------------------------
    # 9. Liquid media preparation and pressurisation
    # ------------------------------------------------------------------
    # M101 — nutrients + NH3 + water + recycle water; H2/O2/CO2 enter via droplet columns.
    # Modeled as inline blending (bst.Mixer, zero capital) rather than a stirred MixTank.
    # At gas fermentation's Q ≈ 357,000 m³/h and feed concentration of 0.004 g/L nutrients
    # (2103× more dilute than fructose), turbulent mixing of near-pure miscible water streams
    # is instantaneous — no residence time or vessel is required.  A MixTank at this Q would
    # auto-parallel into thousands of 30 m³ vessels (BioSTEAM MixTank V_max), which is not a
    # realistic plant design.  User-confirmed 2026-08-07.
    feed_mixer = bst.Mixer(
        'M101',
        ins=[nutrients_storage-0, nh3_storage-0, water_feed, recycle_water],
    )

    # UF101 — UF membrane sterilizer (replaces HX101/HX102 heat sterilization)
    #   Pass-through unit: media composition unchanged at TEA level.
    #   Capital/O&M from Guo, Englehardt & Wu (2014) Water Sci. Technol. WST-EM13819R1.
    #   Framework §4a: gas fermentation route only.
    sterilizer = UltrafiltrationSterilizer(
        'UF101',
        ins=feed_mixer-0,
        contingency_fee_factor=economics.contingency_fee_factor,   # Framework §9.4
    )

    # P101 — pump sterilized liquid to pre-saturation pressure (4 atm, Framework §4a)
    pump = bst.Pump(
        'P101',
        ins=sterilizer-0,
        P=_P_PRE_SAT_ATM * 101325,    # atm → Pa
    )

    # SP101 — split liquid between DC101 (H2) and DC102 (CO2+O2)
    #   outs[0] (fraction f)   → DC101 liquid inlet  (H2 side)
    #   outs[1] (fraction 1-f) → DC102 liquid inlet  (CO2+O2 side)
    liquid_splitter = bst.Splitter(
        'SP101',
        ins=pump-0,
        split=f,
    )

    # ------------------------------------------------------------------
    # 10. Droplet columns — pre-saturate liquid with dissolved gas (Framework §4a)
    #     Closed vessels: all gas dissolves into liquid outlet, no vent.
    #     DC101 and DC102 kept separate to prevent H2/O2 contact in gas phase
    #     (explosion hazard — Framework §4a).
    # ------------------------------------------------------------------
    droplet_col_h2 = DropletColumn(
        'DC101',
        ins=[liquid_splitter-0, h2_aftercooler-0],        # was h2_compressor-0
        dissolved_species={'H2': _S_F_H2},               # g/L design target
        q_max_m3s=DC_Q_MAX_M3S,                          # Framework §4a; SA-patchable
    )
    droplet_col_co2o2 = DropletColumn(
        'DC102',
        ins=[liquid_splitter-1, co2o2_aftercooler-0],     # was co2o2_compressor-0
        dissolved_species={'O2': _S_F_O2, 'CO2': S_f_CO2},   # g/L design targets
        q_max_m3s=DC_Q_MAX_M3S,                          # Framework §4a; SA-patchable
    )

    # MX101 — recombine H2-saturated and O2/CO2-saturated liquid streams
    pre_sat_mixer = bst.Mixer('MX101', ins=[droplet_col_h2-0, droplet_col_co2o2-0])

    # ------------------------------------------------------------------
    # 11. PerfusionBioreactor R101 — autotrophic C. necator cultivation
    #     Perfusion retains cells via internal centrifuge (eta=0.97), achieving
    #     ~25x higher CDW than a simple CSTR at the same S_f = 0.0051 g/L.
    #     This reduces vessel count (capital savings) but does not reduce the
    #     total liquid throughput Q — water cost dominates, illustrating the
    #     inherent mass-transfer limitation of gas-phase H2 fermentation.
    #     PerfusionBioreactor dynamically updates S_f from the MX101 outlet
    #     in _run() (effective S_f_inlet = f * _S_F_H2 after DC101/DC102 mixing).
    # ------------------------------------------------------------------
    bioreactor = PerfusionBioreactor(
        'R101',
        ins=pre_sat_mixer-0,
        V_max=V_max_L,                     # L — working volume per vessel
        mu=mu_op,                          # h⁻¹ — operating specific growth rate
        S_f=_S_F_H2,                      # g/L — initial H2 estimate (updated in _run)
        n_H2=GAS_FERM_N_H2,
        n_O2=GAS_FERM_N_O2,
        n_CO2=GAS_FERM_N_CO2,
        n_NH3=GAS_FERM_N_NH3,
        n_H2O=GAS_FERM_N_H2O,
        MW_biomass=MW_biomass,
        Y_mol=Y_mol,
        m_s_mol=0.0,                       # no maintenance — Framework §9.5a
        conversion=params.epsilon,         # 0.99 — Framework §9.2
        eta=_ETA,                          # 0.97 — Framework §4a
        bleed_fraction=_BLEED_FRAC,        # 0.20 — Framework §4a
        P_operating=_P_PRE_SAT_ATM,        # 4.0 atm — Framework §4a
        T_operating=T_FERMENTATION_K,      # 303.15 K — Framework §9.2
        target_annual_biomass_MT=adjusted_output_MT_yr,
        nutrient_coefficient=nutrient_coeff,
    )

    # ------------------------------------------------------------------
    # 12. Downstream recovery chain (centrifuge → dryer → product storage)
    #     PerfusionBioreactor outs[0] = harvest_slurry (liquid, biomass-enriched).
    #     C101 outs[0] = cake (75% moisture) → dryer
    #     C101 outs[1] = liquid effluent → WWT
    #     D101 outs[0] = evaporated water (vapor) → atmospheric emission (not WWT feed)
    #     D101 outs[1] = dried SCP product (5% moisture) → product storage
    # ------------------------------------------------------------------
    # LIMITATION: BioSTEAM SolidsCentrifuge sizes capital on solids loading rate (ton/hr).
    # At gas fermentation's harvest density of ~0.009 g/L, the correlation extrapolates to
    # near-zero capital (~$187K total) — physically meaningless at Q ≈ 357,000 m³/h.
    # A volumetric-throughput correction (e.g. ~5,246 units × $1M = $5.24B purchase cost at
    # 300 gpm/unit per Dolphin Centrifuge specs) would give FCI ≈ $28B and MSP ≈ $390/kg,
    # which more faithfully represents the separation bottleneck but depends on a single
    # vendor quote. Retained as-is; C101 capital is a known underestimate for this route.
    centrifuge = bst.SolidsCentrifuge(
        'C101',
        ins=bioreactor-0,
        split={'CNecatorBiomass': CENTRIFUGE_RECOVERY},
        moisture_content=CENTRIFUGE_CAKE_MOISTURE,    # 0.75 — Framework §9.2
        solids=['CNecatorBiomass'],
    )
    spray_dryer = bst.SprayDryer(
        'D101',
        ins=centrifuge-0,
        moisture_content=SPRAY_DRYER_MOISTURE,        # 0.05 — Framework §9.2
    )
    product_storage = bst.StorageTank(
        'ST104',
        ins=spray_dryer-1,
        tau=STORAGE_TANK_TAU,
    )

    # ------------------------------------------------------------------
    # 13. Seed train — 3 stages (SR101 → SR102 → SR103 → production)
    #     N_perf_total replaces d['N_total'] (CSTR design value) to size seed
    #     vessels for the actual perfusion vessel count — Framework §6.
    #
    #     Seed substrate: Fructose (not H2).  C. necator is grown heterotrophically
    #     on fructose for seed culture, then transitions to autotrophic H2-oxidation
    #     at production scale.  H2 is physically unsuitable for seed culture:
    #       (a) dissolved H2 at ambient pressure ≪ 0.001 g/L — too dilute to support
    #           meaningful growth (S_f = 0.0051 g/L requires 4 atm pressurization);
    #       (b) SeedBioreactor (AeratedBioreactor) is not a pressure vessel.
    #     User-confirmed 2026-08-07; fructose params imported from _ROUTE_PARAMS.
    # ------------------------------------------------------------------
    fructose_rp = get_route_params('fructose')

    # Fructose-basis seed media design: S0 from design_reactor step 3 formula
    # (same derivation as fructose production route — Framework §5 step 3)
    X_star_seed = fructose_rp.target_titer_fraction * fructose_rp.max_titer  # g/L
    S0_seed     = X_star_seed / (fructose_rp.Yxs * fructose_rp.epsilon)       # g/L

    # NH3 mass ratio for fructose seed (g NH3 / g Fructose)
    biomass_formula = chems['CNecatorBiomass'].formula   # same as fructose route uses
    molar_seed  = compute_O2_CO2_H2O_coefficients(
        'C6H12O6', biomass_formula, fructose_rp.Yxs
    )
    nh3_wt_seed = molar_seed['NH3'] * chems['NH3'].MW / chems['Fructose'].MW

    # Fructose growth reaction for seed bioreactors
    seed_rxn = build_growth_reaction(
        substrate_id='Fructose',
        substrate_formula='C6H12O6',
        Yxs=fructose_rp.Yxs,
        epsilon=fructose_rp.epsilon,
        nutrient_coefficient=nutrient_coeff,
    )

    seed_units, seed_wastes = build_seed_train(
        reactions=seed_rxn,
        N_prod_total=N_perf_total,
        V_work_prod=V_work_prod,
        S0=S0_seed,
        X_star=X_star_seed,
        nutrient_coeff=nutrient_coeff,
        nh3_wt=nh3_wt_seed,
        epsilon=fructose_rp.epsilon,
        feedstock_price=fructose_rp.feedstock_price,
        feedstock_id='Fructose',
        composite_price=composite_price,
        economics=economics,
    )

    # ------------------------------------------------------------------
    # 14. Wastewater treatment — 75 % water recycle (Framework §9.2)
    #     recycle_water (already wired into M101.ins) is passed here so
    #     build_wastewater_treatment() assigns it as RCY101.outs[0], closing
    #     the recycle topology.  Gas fermentation produces net H2O
    #     (GAS_FERM_N_H2O mol/mol biomass), but at 75 % recycle the 25 %
    #     purge prevents unbounded accumulation — same pattern as
    #     fructose/acetate/formate routes.
    # ------------------------------------------------------------------
    wwt_units = build_wastewater_treatment(
        # spray_dryer-0 (vapor) is NOT sent to WWT — direct atmospheric emission.
        wastewater_streams=[centrifuge-1, *seed_wastes],
        economics=economics,
        recycle_water=recycle_water,
    )

    # ------------------------------------------------------------------
    # 15. System — recycle loop closed on recycle_water
    #     BioSTEAM iterates the full path until recycle_water converges.
    #     Convergence guaranteed: recycle fraction = 0.75 < 1 (Framework §9.2).
    # ------------------------------------------------------------------
    system = bst.System(
        'gas_fermentation_system',
        path=[nutrients_storage, nh3_storage,
              feed_mixer, sterilizer,
              pump, liquid_splitter,
              h2_compressor, co2o2_compressor,
              h2_aftercooler, co2o2_aftercooler,      # Framework §4a
              droplet_col_h2, droplet_col_co2o2,
              pre_sat_mixer, bioreactor,
              centrifuge, spray_dryer, product_storage,
              *seed_units,
              *wwt_units],
        recycle=recycle_water,
    )

    return system, nutrients_mass_fractions
