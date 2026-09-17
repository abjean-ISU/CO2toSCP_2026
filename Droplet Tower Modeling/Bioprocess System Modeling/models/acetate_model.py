"""Acetate-route SCP flowsheet builder.

Public function
---------------
build_acetate_system(params, economics) -> tuple[bst.System, dict[str, float]]

Flowsheet
---------
Production train — four fresh feed streams → feedstock storage → mixing →
sterilization → fermentation → recovery → product storage → WWT → recycle:

  acetate_feed   → ST101 (StorageTank) ─┐
  nutrients_feed → ST102 (StorageTank) ─┤
  nh3_feed       → ST103 (StorageTank) ─┤→ M101  (MixTank)
  water_feed     ────────────────────────┘
  recycle_water  ──────────────────────────→ M101
    → HX101 (steam heater, 134 °C)
    → HP101 (hold pipe, 2.44 min — Stanbury et al. 2017)
    → HX102 (cooling water, 30 °C)
    → R101  (ExtentBasedBioreactor)
    → C101  (SolidsCentrifuge)
    → D101  (SprayDryer)
    → ST104 (StorageTank — dried SCP product)
    → WWT101 (wastewater Mixer — centrifuge effluent + seed wastes)
    → WWT102 (Splitter — 99 % organics → sludge; 100 % H2O → treated water)
    → RCY101 (Splitter — 75 % treated water → recycle_water; 25 % → discharge)
    → recycle_water (back to M101)

Seed media sterilization track — aggregated feed → storage → sterilization →
split to each stage (Framework §6, §9.2):

  seed_substrate_feed → ST201 (StorageTank) ─┐
  seed_nutrients_feed → ST202 (StorageTank) ─┤
  seed_nh3_feed       → ST203 (StorageTank) ─┤→ SM101 (MixTank)
  seed_water_feed     ────────────────────────┘
    → SHX101 (steam heater, 134 °C)
    → SHP101 (hold pipe, 2.44 min — Stanbury et al. 2017)
    → SHX102 (cooling water, 30 °C)
    → SSP101 (Splitter) outs[0] → SR103 (~95 % of pooled seed flow)
                        outs[1] → SSP102 (Splitter) outs[0] → SR101 (~0.24 %)
                                                    outs[1] → SR102 (~4.75 %)

water_feed provides the primary process-water makeup at the designed Q × 1000
volumetric throughput.  recycle_water supplements it: at steady state the WWT
recycle returns a small additional flow that slightly overshoots the design
volume, which is acceptable for a first-pass TEA.  The 75 % recycle fraction
(WWT_WATER_RECYCLE_FRACTION) keeps the loop a contraction mapping
(gain = 0.75 < 1 → converges).

No .simulate(), TEA build, or export calls — those are run_models.py's job.
(Framework §10 / Spec §models/{route}_model.py)

Sterilization (Framework §9.2)
-------------------------------
HX101 heats the combined liquid feed to T_STERILIZATION_K (134 °C) using steam.
HX102 cools the sterilized stream back to T_FERMENTATION_K (30 °C) using cooling water.
Heat recovery between the two streams is NOT modeled — conservative first-pass TEA.

Feed streams (all priced)
--------------------------
acetate_feed   : AceticAcid at S0 g/L, Q m³/h      → price = feedstock_price
nutrients_feed : Nutrients stoichiometric for X*    → price = composite_price
nh3_feed       : NH3 stoichiometric for growth      → price = ammonia_price
water_feed     : Makeup water (balance to Q × 1000) → price = water_price/1000 ($/kg)
recycle_water  : WWT recycle (75 % of treated H2O)  → price = 0.0

Units
-----
ST101  — bst.StorageTank        : acetate feedstock storage (7 days — Framework §9.2)
ST102  — bst.StorageTank        : nutrients feedstock storage (7 days — Framework §9.2)
ST103  — bst.StorageTank        : ammonia feedstock storage (7 days — Framework §9.2)
M101   — bst.MixTank            : combines feeds + recycle (1 h tau — Framework §9.2)
HX101  — bst.HXutility         : steam heater to 134 °C (sterilization)
HX102  — bst.HXutility         : cooling-water cooler to 30 °C (fermentation T)
R101   — ExtentBasedBioreactor  : continuous aerated chemostat, epsilon conversion
C101   — bst.SolidsCentrifuge   : 95 % biomass recovery, 75 % cake moisture
D101   — bst.SprayDryer         : moisture removal to 5 % final moisture
ST104  — bst.StorageTank        : dried SCP product storage (7 days — Framework §9.2)
ST201  — bst.StorageTank        : seed acetate storage (7 days — Framework §9.2)
ST202  — bst.StorageTank        : seed nutrients storage (7 days — Framework §9.2)
ST203  — bst.StorageTank        : seed ammonia storage (7 days — Framework §9.2)
SM101  — bst.MixTank            : seed media mixer — pools all 3 stages' feeds (τ=1 h)
SHX101 — bst.HXutility         : seed media heater to 134 °C (sterilization)
SHX102 — bst.HXutility         : seed media cooler to 30 °C (fermentation T)
SSP101 — bst.Splitter           : splits sterilized seed media to SR103 (outs[0]) and SSP102 (outs[1])
SSP102 — bst.Splitter           : splits remainder to SR101 (outs[0]) and SR102 (outs[1])
SR101  — SeedBioreactor         : Stage-1 seed fermenter (~34 L working volume), single sterilized inlet
SR102  — SeedBioreactor         : Stage-2 seed fermenter (~650 L working volume), single sterilized inlet
SR103  — SeedBioreactor         : Stage-3 seed fermenter (~13 m³, directly inoculates R101), single sterilized inlet
WWT101 — bst.Mixer              : combines centrifuge effluent + seed wastes (inline, zero capital)
WWT102 — bst.Splitter           : 99 % organics → sludge; 100 % H2O → treated water
RCY101 — bst.Splitter           : 75 % H2O → recycle_water; 25 % → discharge
"""

from __future__ import annotations

import biosteam as bst

from common.chemicals import build_chemicals
from common.economics import EconomicBasis, configure_utility_prices
from common.kinetics import (
    build_growth_reaction,
    compute_O2_CO2_H2O_coefficients,
    design_reactor,
    required_fermenter_output,
)
from common.nutrients import build_nutrients_properties
from common.parameters import (
    CENTRIFUGE_CAKE_MOISTURE,
    CENTRIFUGE_RECOVERY,
    MIX_TANK_TAU,
    NH3_NUTRIENTS_EXCESS,
    NUTRIENTS_RECIPE,
    PRODUCTION_TARGET_MT_YR,
    SPRAY_DRYER_MOISTURE,
    STERILIZATION_HOLD_TAU_MIN,
    STORAGE_TANK_TAU,
    T_FERMENTATION_K,
    T_STERILIZATION_K,
    WWT_ORGANIC_REMOVAL,
    WWT_WATER_RECYCLE_FRACTION,
    RouteParams,
)
from common.reactors import ExtentBasedBioreactor, SeedBioreactor
from common.seed_train import build_seed_train
from common.sterilization import HoldPipe
from common.wastewater import build_wastewater_treatment


def build_acetate_system(
    params: RouteParams,
    economics: EconomicBasis,
) -> tuple[bst.System, dict[str, float]]:
    """Build and return the acetate-route BioSTEAM system.

    Does NOT call system.simulate(), build a TEA, or export results.
    All numeric parameters originate from Framework §9 registry entries.

    bst.System uses __slots__ and cannot hold arbitrary attributes, so
    nutrients_mass_fractions is returned as a second element of the tuple
    rather than attached to the system object.  Caller passes it directly to
    common.export.export_results() — Framework §8.

    Parameters
    ----------
    params : RouteParams
        Per-route kinetics and design parameters from common.parameters.get('acetate').
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
    configure_utility_prices(economics)     # Framework §9.4 — must precede simulate()

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
    # 4. Reactor design chain — liquid-substrate (Framework §5)
    # ------------------------------------------------------------------
    d = design_reactor(
        mu_max=params.mu_max,
        Yxs=params.Yxs,
        max_titer=params.max_titer,
        epsilon=params.epsilon,
        D_margin=params.D_margin,
        target_titer_fraction=params.target_titer_fraction,
        adjusted_fermenter_output_MT_yr=adjusted_output_MT_yr,
        S_star_max=params.S_star_max,
    )
    Q      = d['Q']       # m³/h — volumetric throughput
    S0     = d['S0']      # g/L  — acetate (acetic acid) feed concentration
    X_star = d['X_star']  # g/L  — target biomass titer

    # ------------------------------------------------------------------
    # 5. Stoichiometric coefficients (mass basis)
    #    compute_O2_CO2_H2O_coefficients called here for NH3 feed sizing;
    #    build_growth_reaction calls it internally too (compute, don't assert).
    # ------------------------------------------------------------------
    biomass_formula = chems['CNecatorBiomass'].formula
    molar = compute_O2_CO2_H2O_coefficients(
        substrate_formula='C2H4O2',     # Acetic acid — Framework §7
        biomass_formula=biomass_formula,
        Yxs=params.Yxs,
    )
    MW_AceticAcid = chems['AceticAcid'].MW
    MW_NH3        = chems['NH3'].MW
    nh3_wt = molar['NH3'] * MW_NH3 / MW_AceticAcid   # g NH3 / g AceticAcid (mass basis)

    growth_rxn = build_growth_reaction(
        substrate_id='AceticAcid',
        substrate_formula='C2H4O2',
        Yxs=params.Yxs,
        epsilon=params.epsilon,
        nutrient_coefficient=nutrient_coeff,
    )

    # ------------------------------------------------------------------
    # 5a. Working volume per production vessel — used to size seed train stages.
    #     V_total / N_capacity = vessel volume per unit; × V_wf = working volume.
    #     V_wf = 0.8 — AeratedBioreactor default confirmed in common/kinetics.py (_V_WF).
    # ------------------------------------------------------------------
    _V_WF_PROD = 0.8
    V_work_prod = d['V_total'] / d['N_capacity'] * _V_WF_PROD   # m³

    # ------------------------------------------------------------------
    # 6. Feed stream mass flows
    #    Unit conversion: Q [m³/h] × concentration [g/L] → kg/h
    #    (1000 L/m³ and 1000 g/kg cancel exactly — Framework §5 note)
    # ------------------------------------------------------------------
    acetate_kgh   = Q * S0                               # kg/h
    nutrients_kgh = nutrient_coeff * X_star * Q          # kg/h — stoichiometric for X*
    nh3_kgh       = nh3_wt * S0 * params.epsilon * Q     # kg/h — stoichiometric for growth

    # Recycle correction: the WWT recycle returns a small fraction of residual
    # substrate back to M101, which the bioreactor also converts — consuming
    # proportionally more NH3 and Nutrients than the fresh-feed sizing provides.
    # Correction factor derived from the steady-state recycle mass balance;
    # no new parameters — all three inputs are already in the model (Framework §9.2).
    #   recycle_substrate_fraction = WWT_WATER_RECYCLE_FRACTION
    #                                × (1 − WWT_ORGANIC_REMOVAL)
    #                                × (1 − epsilon)
    #                              = 0.75 × 0.01 × 0.10 = 0.00075
    _recycle_sub_frac = (WWT_WATER_RECYCLE_FRACTION
                         * (1.0 - WWT_ORGANIC_REMOVAL)
                         * (1.0 - params.epsilon))
    _recycle_correction = 1.0 / (1.0 - _recycle_sub_frac)
    nutrients_kgh *= _recycle_correction
    nh3_kgh       *= _recycle_correction

    # 5 % supplement above stoichiometric for co-reactants — Framework §9.2.
    # Ensures growth is never N- or mineral-limited; standard practice for
    # continuous culture on mineral-salt media (Doran 2012, §12).
    nutrients_kgh *= (1.0 + NH3_NUTRIENTS_EXCESS)
    nh3_kgh       *= (1.0 + NH3_NUTRIENTS_EXCESS)

    # Total water needed to bring M101 output to Q × 1000 kg/h:
    water_kgh     = Q * 1000.0  # kg/h — Q is the water throughput (m³/h); solutes are additional mass

    # ------------------------------------------------------------------
    # 7. Analytical steady-state water split (Framework §9.2)
    #
    # At steady state, with total water to M101 = water_kgh (constant):
    #   recycle = WWT_WATER_RECYCLE_FRACTION × (water_kgh + W_rxn − W_product)
    #   makeup  = water_kgh − recycle
    #
    # W_rxn  : water produced by the growth reaction per hour
    #           = molar['H2O'] mol H2O / mol AceticAcid × (MW_H2O / MW_AceticAcid)
    #             × acetate_kgh × epsilon
    # W_product: water retained in the dried SCP product
    #           = (biomass out of centrifuge) × moisture_ratio
    #
    # Setting water_feed = makeup and seeding recycle_water = R* gives the
    # BioSTEAM recycle loop a near-converged starting point, minimising
    # iterations.  Convergence is guaranteed: the loop gain equals
    # WWT_WATER_RECYCLE_FRACTION = 0.75 < 1 (contraction mapping).
    # ------------------------------------------------------------------
    MW_H2O         = chems['H2O'].MW                                  # g/mol
    h2o_mass_coeff = molar['H2O'] * MW_H2O / MW_AceticAcid           # kg H2O / kg AceticAcid consumed
    W_rxn          = h2o_mass_coeff * acetate_kgh * params.epsilon    # kg/h H2O from reaction

    biomass_after_centrifuge = (acetate_kgh * params.epsilon
                                * params.Yxs * CENTRIFUGE_RECOVERY)   # kg/h
    W_product = (biomass_after_centrifuge
                 * SPRAY_DRYER_MOISTURE / (1.0 - SPRAY_DRYER_MOISTURE))  # kg/h H2O in dried SCP

    f = WWT_WATER_RECYCLE_FRACTION                                # 0.75
    recycle_ss_kgh = f * (water_kgh + W_rxn - W_product)         # kg/h steady-state recycle
    makeup_kgh     = max(0.0, water_kgh - recycle_ss_kgh)        # kg/h fresh-water makeup

    # ------------------------------------------------------------------
    # 8. Feed streams
    # ------------------------------------------------------------------
    acetate_feed = bst.Stream(
        'acetate_feed',
        AceticAcid=acetate_kgh,
        units='kg/hr',
        price=params.feedstock_price,          # $/kg — Framework §9.4
    )
    nutrients_feed = bst.Stream(
        'nutrients_feed',
        Nutrients=nutrients_kgh,
        units='kg/hr',
        price=composite_price,                 # $/kg — computed in nutrients.py
    )
    nh3_feed = bst.Stream(
        'nh3_feed',
        NH3=nh3_kgh,
        units='kg/hr',
        price=economics.ammonia_price,         # $/kg — Framework §9.4
    )
    # Fresh water makeup — covers the small portion of process-water demand
    # not supplied by the WWT recycle.  Flow is pre-computed analytically so
    # the bioreactor runs at the designed Q × 1000 throughput.
    water_feed = bst.Stream(
        'water_feed',
        H2O=makeup_kgh,
        units='kg/hr',
        price=economics.water_price / 1000.0,  # $/m³ ÷ 1000 kg/m³ → $/kg — Framework §9.4
    )

    # Recycle water tear stream — pre-created so it can be wired into M101.ins
    # before RCY101 is constructed.  RCY101.outs[0] is assigned this same object
    # inside build_wastewater_treatment(), completing the recycle topology.
    # Seeded at R* (analytical steady state) for fast BioSTEAM convergence.
    # price = 0: no purchase cost; stream is supplied by the WWT recycle loop.
    recycle_water = bst.Stream(
        'recycle_water',
        H2O=recycle_ss_kgh,
        units='kg/hr',
        price=0.0,
    )

    # ------------------------------------------------------------------
    # 8a. Feedstock storage tanks (Framework §9.2: STORAGE_TANK_TAU = 168 h = 7 days)
    # ------------------------------------------------------------------
    acetate_storage   = bst.StorageTank('ST101', ins=acetate_feed,   tau=STORAGE_TANK_TAU)
    nutrients_storage = bst.StorageTank('ST102', ins=nutrients_feed, tau=STORAGE_TANK_TAU)
    nh3_storage       = bst.StorageTank('ST103', ins=nh3_feed,       tau=STORAGE_TANK_TAU)

    # ------------------------------------------------------------------
    # 9. Unit operations
    # ------------------------------------------------------------------

    # M101 — mix feedstock storage outlets + water feeds before sterilization
    #   Changed from bst.Mixer to bst.MixTank to capture capital cost — Framework §9.2
    feed_mixer = bst.MixTank(
        'M101',
        ins=[acetate_storage-0, nutrients_storage-0, nh3_storage-0,
             water_feed, recycle_water],
        tau=MIX_TANK_TAU,   # 1 h — Framework §9.2
    )

    # HX101 — steam heater to sterilization temperature (134 °C)
    #   heat_only=True: ensures BioSTEAM selects a steam utility agent
    #   Framework §9.2: continuous heat sterilization standard practice
    sterilizer_heater = bst.HXutility(
        'HX101',
        ins=feed_mixer-0,
        T=T_STERILIZATION_K,
        heat_only=True,
    )

    # HP101 — hold pipe: 2.44 min at 134 °C (Stanbury et al. 2017 §Sterilization)
    #   Capital excluded: < 0.01 % FCI at design flows — Framework §9.2
    hold_pipe = HoldPipe('HP101', ins=sterilizer_heater-0,
                         tau_min=STERILIZATION_HOLD_TAU_MIN)

    # HX102 — cooling-water cooler back to fermentation temperature (30 °C)
    #   cool_only=True: ensures BioSTEAM selects a cooling-water utility agent
    #   Heat recovery between HX101 and HX102 not modeled — conservative (Framework §9.2)
    sterilizer_cooler = bst.HXutility(
        'HX102',
        ins=hold_pipe-0,
        T=T_FERMENTATION_K,
        cool_only=True,
    )

    # R101 — continuous aerated chemostat (Framework §5)
    #   T=T_FERMENTATION_K: BioSTEAM computes metabolic heat removal duty at 30 °C
    bioreactor = ExtentBasedBioreactor(
        'R101',
        ins=sterilizer_cooler-0,
        reactions=growth_rxn,
        mu_max=params.mu_max,
        D_margin=params.D_margin,
        T=T_FERMENTATION_K,               # 30 °C — Framework §9.2
    )

    # C101 — solids centrifuge
    #   AeratedBioreactor outlet convention (confirmed from installed source):
    #     outs[0] = gas vent (CO2, off-gas)   ← do NOT connect this to centrifuge
    #     outs[1] = liquid effluent (biomass, residual substrate, water) ← correct inlet
    #   outs[0]: cake (solids-rich, 75 % moisture) → dryer
    #   outs[1]: liquid effluent → wastewater treatment
    centrifuge = bst.SolidsCentrifuge(
        'C101',
        ins=bioreactor-1,
        split={'CNecatorBiomass': CENTRIFUGE_RECOVERY},
        moisture_content=CENTRIFUGE_CAKE_MOISTURE,    # 0.75 — Framework §9.2
        solids=['CNecatorBiomass'],
    )

    # D101 — spray dryer
    #   outs[0]: evaporated water (vapor) → atmospheric emission (not WWT feed)
    #   outs[1]: dried SCP product (5 % moisture) → product storage
    spray_dryer = bst.SprayDryer(
        'D101',
        ins=centrifuge-0,
        moisture_content=SPRAY_DRYER_MOISTURE,        # 0.05 — Framework §9.2
    )

    # ST104 — product storage tank (Framework §9.2: STORAGE_TANK_TAU = 168 h = 7 days)
    #   Receives dried SCP from spray_dryer-1; final product exits as ST104-0.
    #   CNecatorBiomass is a solid; bst.StorageTank sizes from F_vol_out.
    product_storage = bst.StorageTank(
        'ST104',
        ins=spray_dryer-1,      # dried SCP product (5% moisture)
        tau=STORAGE_TANK_TAU,
    )

    # ------------------------------------------------------------------
    # 9a. Seed train — 3 stages (SR101 → SR102 → SR103 → production)
    #     Provides inoculum for N_total × RESTARTS_PER_YEAR restart events/yr.
    #     Outlets (liquid effluent) routed to WWT — Framework §6.
    # ------------------------------------------------------------------
    seed_units, seed_wastes = build_seed_train(
        reactions=growth_rxn,
        N_prod_total=d['N_total'],
        V_work_prod=V_work_prod,
        S0=S0,
        X_star=X_star,
        nutrient_coeff=nutrient_coeff,
        nh3_wt=nh3_wt,
        epsilon=params.epsilon,
        feedstock_price=params.feedstock_price,
        feedstock_id='AceticAcid',
        composite_price=composite_price,
        economics=economics,
    )

    # WWT101 + WWT102 + RCY101 — wastewater treatment and water recycle
    #   centrifuge-1 : liquid effluent (residual acetate, water, trace biomass)
    #   seed_wastes  : liquid effluents from SR101, SR102, SR103 (outs[1])
    #   recycle_water : wired into M101 above; RCY101.outs[0] set to this stream
    #   spray_dryer-0 (vapor) is NOT sent to WWT — it is a direct atmospheric emission.
    #   Framework §9.2, §9.4
    wwt_units = build_wastewater_treatment(
        wastewater_streams=[centrifuge-1, *seed_wastes],
        economics=economics,
        recycle_water=recycle_water,
    )

    # ------------------------------------------------------------------
    # 10. System — recycle loop closed on recycle_water
    #    BioSTEAM iterates the full path until recycle_water converges.
    #    Convergence guaranteed: recycle fraction = 0.75 < 1 (Framework §9.2).
    # ------------------------------------------------------------------
    system = bst.System(
        'acetate_system',
        path=[acetate_storage, nutrients_storage, nh3_storage,
              feed_mixer, sterilizer_heater, hold_pipe, sterilizer_cooler,
              bioreactor, centrifuge, spray_dryer,
              product_storage,
              *seed_units,         # SR101, SR102, SR103 — Framework §6
              *wwt_units],
        recycle=recycle_water,
    )

    return system, nutrients_mass_fractions
