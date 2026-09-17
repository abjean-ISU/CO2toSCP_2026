"""Single source of truth for all sourced/chosen numeric parameters: RouteParams, NutrientsRecipe, and EconomicBasis, per Framework §9 registry."""

from __future__ import annotations
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Per-route kinetic and design parameters
# ---------------------------------------------------------------------------

@dataclass
class RouteParams:
    """Per-route parameters consumed by common/kinetics.py and route model builders.

    All fields required — no defaults — to prevent silent omissions at call sites.
    Values are populated from Framework §9.1, §9.2, §9.4; see _ROUTE_PARAMS below.
    """
    mu_max: float                # h⁻¹ — maximum specific growth rate (Framework §9.1)
    Yxs: float                   # g biomass / g substrate (Framework §9.1)
    max_titer: float             # g/L — literature ceiling titer (Framework §9.1)
    epsilon: float               # 0–1, substrate conversion extent (Framework §9.2)
    D_margin: float              # fraction of mu_max used as dilution rate setpoint (Framework §9.2)
    target_titer_fraction: float # 0–1, X* = fraction × max_titer (Framework §9.2)
    feedstock_price: float       # $/kg (Framework §9.4)
    S_star_max: float | None     # g/L — inhibition ceiling on residual substrate in CSTR.
                                 # None = no known threshold for this route (no constraint applied).
                                 # Framework §9.1 S* validation reference rows.
                                 # Used by design_reactor() inhibition branch (Framework §5).


# ---------------------------------------------------------------------------
# Shared nutrients recipe — processed by common/nutrients.py
# ---------------------------------------------------------------------------

@dataclass
class NutrientsRecipe:
    """Raw recipe dict pair consumed by common/nutrients.py.

    nutrients.py derives composite MW, composite price, stoichiometric
    coefficient, and mass fractions from these two dicts.  No derived values
    are stored here — compute, don't assert. (Framework §9.3)

    Keys in both dicts must match; nutrients.py validates alignment.
    """
    concentrations: dict[str, float]  # component_name -> g/L in fermentation media
    prices: dict[str, float]          # component_name -> $/kg
    achieved_titer: float             # g/L CDW at which the recipe was reported (Framework §9.3)


# ---------------------------------------------------------------------------
# Shared economic basis — identical across all four routes
# ---------------------------------------------------------------------------

@dataclass
class EconomicBasis:
    """Shared financing/cost parameters consumed by common/economics.py → build_tea.

    Identical for all four routes so that four MSPs are directly comparable.
    Values populated from Framework §9.4; see _ECONOMICS below.
    """
    dollar_year: int                      # reference year for CEPCI escalation
    CEPCI: float                          # plant cost index for dollar_year (Framework §9.4)
    IRR: float                            # internal rate of return, fraction/yr (Framework §9.4)
    duration: tuple[int, int]             # (start_year, end_year) — 20-yr plant life (Framework §9.4)
    depreciation: str                     # BioSTEAM depreciation schedule name (Framework §9.4)
    income_tax: float                     # fraction (Framework §9.4)
    contingency_fee_factor: float         # multiplier on Σ(C_P × f_BM) to reach FCI;
                                          # covers contingency (15%) + contractor fees (3%) = 1.18
                                          # Turton et al. (7th ed.) Table 16.1 (Framework §9.4).
    WC_over_FCI: float                    # fraction of FCI held as working capital; TCI = FCI*(1 + WC_over_FCI) (Framework §9.4)
    construction_schedule: tuple[float, ...]  # fractions of FCI spent per pre-startup year, must sum to 1 (Framework §9.4)
    labor_cost: float                     # $/yr (Framework §9.4)
    fringe_benefits: float                # fraction of labor (Framework §9.4)
    supplies: float                       # fraction of labor (Framework §9.4)
    property_tax: float                   # fraction of FCI (Framework §9.4)
    property_insurance: float             # fraction of FCI (Framework §9.4)
    maintenance: float                    # fraction of FCI (Framework §9.4)
    administration: float                 # fraction of FCI (Framework §9.4)
    electricity_price: float              # $/kWh (Framework §9.4)
    steam_price: float                    # $/GJ (Framework §9.4)
    cooling_water_price: float            # $/m³ (Framework §9.4)
    chilled_water_price: float            # $/GJ — Seider et al. Table 8.3 (Framework §9.4)
    water_price: float                    # $/m³ process water — Seider et al. Table 8.3 (Framework §9.4)
    ammonia_price: float                  # $/kg NH3 co-reactant, shared all routes (Framework §9.4)
    wwt_organic_removal_cost: float       # $/kg organic removed — Seider et al. (Framework §9.4)


# ---------------------------------------------------------------------------
# Universal module-level constants
# ---------------------------------------------------------------------------

ROUTES: tuple[str, ...] = ('fructose', 'acetate', 'formate', 'gas_fermentation')
# Canonical route ordering used by run_models.py and sensitivity_analysis.py.

THETA_O2: float = 0.5
# Dissolved-O2 setpoint fraction — Framework §9.2: kept at BioSTEAM default deliberately;
# revisit only if a route shows O2-limitation symptoms (AeratedBioreactor feasibility failure).

RESTART_FREQUENCY_PER_LINE: float = 2.0
# Contamination-driven restarts/yr per production line — Framework §9.2:
# 6-month campaigns (Cauldron/Stansfield, AgFunderNews March 2024).

CENTRIFUGE_RECOVERY: float = 0.95
# Fraction of biomass recovered by centrifugation — Framework §9.2, engineering judgment.
# SprayDryer modeled as moisture removal only; dryer solids recovery = 100% (Framework §9.2).

CENTRIFUGE_CAKE_MOISTURE: float = 0.75
# Fraction of water in centrifuge cake (wt/wt) — Framework §9.2, engineering judgment.
# Representative of scroll/disc-stack centrifuge on bacterial biomass; implemented via
# bst.SolidsCentrifuge(moisture_content=0.75).

SPRAY_DRYER_MOISTURE: float = 0.05
# Final product moisture fraction (wt/wt) — Framework §9.2, Ugalde & Castrillo (2002).
# Industry standard for microbial SCP powder; implemented via
# bst.SprayDryer(moisture_content=0.05).

PRODUCTION_TARGET_MT_YR: float = 25_000.0
# Annual production target in MT/yr of final packaged SCP — Framework §9.2.
# Applied to final product (post-centrifuge, post-dryer); upstream steps are sized
# backwards via required_fermenter_output().

T_STERILIZATION_K: float = 407.15
# Continuous media sterilization temperature — Framework §9.2.
# 134 °C: standard for continuous heat sterilization of liquid fermentation media
# (Doran 2012, §12.3; EN 285). Applied to mixed liquid feed before the bioreactor;
# implemented via bst.HXutility(T=407.15, heat_only=True).
# Heat recovery not modeled — conservative TEA assumption.

STERILIZATION_HOLD_TAU_MIN: float = 2.44
# Continuous sterilization hold time at T_STERILIZATION_K (134 °C) — Framework §9.2.
# Stanbury, Whitaker & Hall (2017) Principles of Fermentation Technology (3rd ed.),
# §Sterilization. Implemented via HoldPipe (HP101 / SHP101).

T_FERMENTATION_K: float = 303.15
# Fermentation operating temperature — Framework §9.2.
# 30 °C: optimal growth temperature for C. necator (Boy et al. 2021; Yu & Lu 2019).
# Passed to ExtentBasedBioreactor and PerfusionBioreactor as T=T_FERMENTATION_K.

WWT_ORGANIC_REMOVAL: float = 0.99
# Fraction of non-water organics removed by wastewater treatment — Framework §9.2.
# 99 % BOD removal is consistent with well-operated activated sludge / aerobic digestion
# (Metcalf & Eddy, Wastewater Engineering, 5th ed., Table 10-1). Implemented via WWT102
# (_SludgeSettler): 99% of each non-H2O component routes to sludge; 1% passes through.

WWT_SLUDGE_MOISTURE: float = 0.80
# Moisture fraction of the WWT102 sludge output (wt H2O / wt total) — Framework §9.2.
# 80 % moisture (20 % dry solids) is characteristic of centrifuge-dewatered or belt-
# filter-press sludge cake (Metcalf & Eddy, Wastewater Engineering, 5th ed., Table 22-10).
# Enforced in _SludgeSettler._run(): water_to_sludge = (0.80/0.20) × dry_sludge_mass.
# At dilute fermentation flows the water lost to sludge is <1.1% of inlet water —
# negligible effect on the recycle water balance. Implemented via common/wastewater.py.

WWT_WATER_RECYCLE_FRACTION: float = 0.75
# Fraction of WWT-treated water recycled back to the process feed — Framework §9.2.
# The remaining 25% is discharged as treated effluent.  A fraction < 1 is required to
# close the water mass balance: aerobic fermentation produces net H2O (stoichiometric
# product of C. necator metabolism), so 100% recycle would cause unbounded accumulation.
# 0.75 makes the recycle loop a contraction mapping (gain = 0.75 < 1 → converges).
# Implemented via RCY101 (bst.Splitter) downstream of WWT102.

MIX_TANK_TAU: float = 1.0
# Residence time for bst.MixTank M101 (feed mixer) in the three liquid-substrate routes
# (fructose, acetate, formate) — Framework §9.2.  Standard hold-up time for continuous-feed
# mixing of g/L-concentration mineral salts media (Doran, Bioprocess Engineering Principles,
# 2nd ed.).  NOT used for gas fermentation M101 (modeled as bst.Mixer, zero capital —
# see gas_fermentation_model.py) or WWT101 in any route (WWT101 is also bst.Mixer —
# see common/wastewater.py).

STORAGE_TANK_TAU: float = 168.0
# Residence time for bst.StorageTank units (feedstock + product storage) — Framework §9.2.
# 7 days of buffer inventory — standard continuous-plant practice.

INOCULUM_RATIO: float = 0.05
# Fraction of next-stage working volume used as seed inoculum — Framework §9.2.
# Engineering judgment (user decision 2025-08-05).  Applied to all three modeled
# seed stages; unmodeled 20 L seed fermenter is below the modeled scope.

SEED_BATCH_DURATION_H: float = 72.0
# Total duration of one 3-stage seed batch — Framework §9.2.
# 3 stages × 24 h/stage: each stage grows from INOCULUM_RATIO × V_work_next (5 % inoculum)
# to working density.  For fructose mu_max = 0.22 h⁻¹, growth time alone is
# ln(1/INOCULUM_RATIO) / (D_margin × mu_max) = ln(20) / (0.80 × 0.22) ≈ 17 h;
# 24 h/stage adds a ~7 h margin for lag phase (Doran, Bioprocess Engineering
# Principles, 2nd ed., §14.4).  Governs N_seed_trains — the number of concurrent
# seed preparations needed to cover N_total × RESTARTS_PER_YEAR restart events/yr:
#   N_seed_trains = ceil(N_total × RESTARTS_PER_YEAR × SEED_BATCH_DURATION_H / op_hours)
# For gas fermentation (N_total ≈ 493): N_seed_trains ≈ 9.
# For liquid routes (N_total ≈ 6–39): N_seed_trains = 1.
# Engineering judgment — user-confirmed 2026-08-07.

NH3_NUTRIENTS_EXCESS: float = 0.05
# Fractional supplement above stoichiometric applied to both NH3 and mineral
# Nutrients feeds — Framework §9.2.  Applied in all three liquid-substrate route
# model builders and common/seed_train.py.
# Basis: continuous fermenters are operated with a small excess of N-source and
# mineral nutrients to ensure growth is never substrate-limited by co-reactants.
# 5 % is standard practice for mineral-salt media in continuous culture
# (Doran, Bioprocess Engineering Principles, 2nd ed., §12).
# Note on NH3 VLE: at fermentation pH 6–7, dissolved nitrogen exists primarily as
# NH4⁺ (pKa 9.25) and does not volatilize; however BioSTEAM's equilibrium model
# treats the species as free NH3 and routes residual NH3 to the reactor gas vent.
# The supplement therefore has limited effect on the liquid NH3 balance; the
# _run_vent floor in common/reactors.py provides the primary numerical fix for
# near-zero effluent NH3.  The Nutrients supplement does fully resolve the
# Nutrients effluent (phase='l', non-volatile) — the intended benefit.

DC_Q_MAX_M3S: float = 0.577
# Maximum liquid throughput per droplet column (DC101/DC102), m³/s — Framework §4a.
# Baseline liquid holdup ≈ 0.2%: V_column = π*(5m)²*4m = 314.2 m³;
# V_liquid = 0.002 × 314.2 = 0.628 m³; τ = 0.628/0.577 = 1.09 s.
# SA range: lo=0.0577 (0.02% holdup), hi=11.5 (4% holdup) — user-confirmed 2026-09-01.


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

_ROUTE_PARAMS: dict[str, RouteParams] = {
    'fructose': RouteParams(
        mu_max=0.22,                 # h⁻¹  — Boy et al. (2021) AMB Express
        Yxs=0.32,                    # g/g  — Boy et al. (2021)
        max_titer=32.0,              # g/L  — Nygaard et al. (2021) Heliyon
        epsilon=0.9,                 #      — Framework §9.2, engineering judgment
        D_margin=0.8,                #      — Framework §9.2, bioprocesstools.com
        target_titer_fraction=0.75,  #      — Framework §9.2, engineering judgment
        feedstock_price=1.16,        # $/kg — selinawamucii.com
        S_star_max=None,             # non-inhibitory up to 50 g/L (Boy 2021/Nygaard 2021)
    ),
    'acetate': RouteParams(
        mu_max=0.15,                 # h⁻¹  — Garcia-Gonzalez & de Wever (2018) Appl. Sci.
        Yxs=0.45,                    # g/g  — Garcia-Gonzalez & de Wever (2018)
        max_titer=15.0,              # g/L  — Garcia-Gonzalez & de Wever (2018)
        epsilon=0.9,                 #      — Framework §9.2, engineering judgment
        D_margin=0.8,                #      — Framework §9.2, bioprocesstools.com
        target_titer_fraction=0.75,  #      — Framework §9.2, engineering judgment
        feedstock_price=0.65,        # $/kg — Crandall et al. (2023) Acc. Chem. Res.
        S_star_max=3.0,              # g/L  — Garcia-Gonzalez & de Wever (2018) §9.1; not binding
    ),
    'formate': RouteParams(
        mu_max=0.18,                 # h⁻¹  — Grunwald et al. (2015) Microb. Biotechnol.
        Yxs=0.06,                    # g/g  — Claassens et al. (2020) Metab. Eng.
        max_titer=10.5,              # g/L  — Grunwald et al. (2015)
        epsilon=0.9,                 #      — Framework §9.2, engineering judgment
        D_margin=0.8,                #      — Framework §9.2, bioprocesstools.com
        target_titer_fraction=0.75,  #      — Framework §9.2, engineering judgment
        feedstock_price=0.35,        # $/kg — Jouny et al. (2018) Ind. Eng. Chem. Res.
        S_star_max=3.0,              # g/L  — Grunwald et al. (2015) §9.1; binding (S_star_titer ~14.5 g/L)
    ),
    'gas_fermentation': RouteParams(
        mu_max=0.12,                 # h⁻¹     — Yu & Lu (2019) Biochem. Eng. J.
        Yxs=2.26,                    # g CDW/g H2 — derived from molar equation (§9.5a):
                                     #   MW_biomass / (n_H2 × MW_H2) = 97.20/43.06 = 2.26
                                     #   supersedes Yu & Lu (2019) value of 1.56
        max_titer=7.0,               # g/L     — Yu & Lu (2019); not used by perfusion model
        epsilon=0.99,                #         — near-complete H2 conversion (user decision;
                                     #   bacteria fully converts dissolved H2 — §9.2)
        D_margin=0.8,                #         — Framework §9.2, bioprocesstools.com
        target_titer_fraction=0.75,  #         — Framework §9.2; not used by perfusion model
        feedstock_price=4.83,        # $/kg H2 — Peterson et al. (2019) DOE Record: H2 from PEM electrolysis
        S_star_max=None,             # design_reactor() not called; Henry's law fixes S_f
    ),
}

_ECONOMICS: EconomicBasis = EconomicBasis(
    dollar_year=2025,
    CEPCI=809.3,                        # 2025 average — §9.4
    IRR=0.10,                           # §9.4
    duration=(2025, 2045),              # 20-yr plant life — §9.4
    depreciation='MACRS7',              # §9.4 (Framework doc has typo 'MARCS7')
    income_tax=0.35,                    # 35 % combined federal+state — §9.4
    contingency_fee_factor=1.18,        # Turton (7th ed.) Table 16.1 — §9.4
    WC_over_FCI=0.176,                  # Seider et al. §9.4
    construction_schedule=(0.40, 0.60), # Huang et al. (2016) §9.4
    labor_cost=3_600_000.0,             # $/yr — Turton §9.4
    fringe_benefits=0.0,                # loaded into labor_cost — §9.4
    supplies=0.0,                       # loaded into labor_cost — §9.4
    property_tax=0.01,                  # fraction of FCI — Turton §9.4
    property_insurance=0.01,            # Turton §9.4
    maintenance=0.10,                   # Turton §9.4
    administration=0.05,                # Turton §9.4
    electricity_price=0.032,            # $/kWh — DOE Wind §9.4
    steam_price=13.0,                   # $/GJ — Turton §9.4
    cooling_water_price=0.015,          # $/m³ — Turton §9.4
    chilled_water_price=5.0,            # $/GJ — Seider et al. Table 8.3 §9.4
    water_price=0.27,                   # $/m³ — Seider et al. Table 8.3 §9.4
    ammonia_price=0.50,                 # $/kg NH3 — BusinessAnalytiq §9.4
    wwt_organic_removal_cost=0.33,      # $/kg organic removed — Seider et al. §9.4
)

ECONOMICS: EconomicBasis = _ECONOMICS   # public singleton for callers

_NUTRIENTS_RECIPE: NutrientsRecipe = NutrientsRecipe(
    concentrations={           # g/L — Yu & Munasinghe (2018) Fermentation 4(3):63
        'Na2HPO4.2H2O':         2.5,
        'KH2PO4':                2.4,
        'AmmoniumSulfate':       2.0,   # (NH4)2SO4 — source uses ammonium sulfate, not NH4Cl
        'MgSO4.7H2O':            0.5,
        'NaHCO3':                0.5,
        'FerricAmmoniumCitrate': 0.1,
        'TraceMetals':           0.0014,  # H3BO3/CoCl2/ZnSO4/MnCl2/Na2MoO4/NiCl2/CuSO4 combined
    },
    prices={                   # $/kg — Sigma-Aldrich list × 0.01 (industrial bulk discount) — §9.3
        'Na2HPO4.2H2O':          2.10,
        'KH2PO4':                 1.70,
        'AmmoniumSulfate':        1.50,  # (NH4)2SO4 — §9.3
        'MgSO4.7H2O':             1.70,
        'NaHCO3':                 1.00,
        'FerricAmmoniumCitrate':  5.00,
        'TraceMetals':           60.00,
    },
    achieved_titer=18.0,  # g/L CDW — Yu & Munasinghe (2018), same paper as recipe — Framework §9.3
)

NUTRIENTS_RECIPE: NutrientsRecipe = _NUTRIENTS_RECIPE  # public singleton for callers


# ---------------------------------------------------------------------------
# Accessor
# ---------------------------------------------------------------------------

def get(route: str) -> RouteParams:
    """Return per-route kinetic and design parameters.

    Calling pattern per Spec §run_models.py: ``params = parameters.get(route)``.
    Raises NotImplementedError until _ROUTE_PARAMS is populated from Framework §9.
    """
    if route not in _ROUTE_PARAMS:
        raise NotImplementedError(
            f"Route '{route}' not yet registered in _ROUTE_PARAMS. "
            "Populate from Framework §9 before calling."
        )
    return _ROUTE_PARAMS[route]
