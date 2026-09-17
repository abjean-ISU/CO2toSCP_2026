"""Seed-train operating-hours accounting and system builder for all four SCP routes.

Public functions
---------------
seed_train_operating_hours(N_total) — total annual restart hours across
    all N_total parallel production lines.
build_seed_train(...)              — construct 3-stage BioSTEAM seed train
    with shared feed storage and sterilization track
    (ST201/ST202/ST203 → SM101 → SHX101 → SHP101 → SHX102 → SSP101/SSP102
     → SR101/SR102/SR103) for liquid-substrate routes.

Ordering dependency: must be called after common.kinetics.design_reactor()
or design_gas_fermentation_reactor() has produced N_total.  That function's
output is the only input here — Framework §6.

Framework §6 / Spec §common/seed_train.py.
"""

from __future__ import annotations
import math

import biosteam as bst

from common.economics import EconomicBasis
from common.operating_hours import CONTAMINATION_RESTART_H, RESTARTS_PER_YEAR, effective_operating_hours
from common.parameters import (
    INOCULUM_RATIO, MIX_TANK_TAU, NH3_NUTRIENTS_EXCESS, SEED_BATCH_DURATION_H,
    STERILIZATION_HOLD_TAU_MIN, STORAGE_TANK_TAU, T_FERMENTATION_K, T_STERILIZATION_K,
)
from common.reactors import SeedBioreactor
from common.sterilization import HoldPipe


def seed_train_operating_hours(N_total: int) -> float:
    """Total annual seed-train operating hours for N_total production lines.

    Each line — including the N+1 redundancy line, which is still subject to
    contamination risk — requires CONTAMINATION_RESTART_H hours of restart /
    reacclimation per year (Framework §6).

    CONTAMINATION_RESTART_H = RESTARTS_PER_YEAR × RESTART_DURATION_H
                             = 2 × 336 = 672 h/yr per line.

    The ×2 restarts/yr factor is already built into CONTAMINATION_RESTART_H;
    no additional multiplier is needed here — Framework §6 / Spec note.

    Parameters
    ----------
    N_total : int
        Total parallel production-line count including the N+1 redundancy
        vessel (output of design_reactor() or design_gas_fermentation_reactor()).

    Returns
    -------
    float
        Total annual seed-train operating hours across all lines (h/yr).
    """
    return float(N_total * CONTAMINATION_RESTART_H)


def build_seed_train(
    reactions: bst.Reaction,
    N_prod_total: int,
    V_work_prod: float,
    S0: float,
    X_star: float,
    nutrient_coeff: float,
    nh3_wt: float,
    epsilon: float,
    feedstock_price: float,
    feedstock_id: str,
    composite_price: float,
    economics: EconomicBasis,
) -> tuple[list[bst.Unit], list[bst.Stream]]:
    """Build 3-stage seed train with shared feed storage and sterilization.

    Topology (Framework §6, §9.2):

        seed_substrate_feed → ST201 (StorageTank) ─┐
        seed_nutrients_feed → ST202 (StorageTank) ─┤
        seed_nh3_feed       → ST203 (StorageTank) ─┤
        seed_water_feed     ──────────────────────→ SM101 (MixTank, τ=1 h)
          → SHX101 (HXutility, heat to 134 °C)
          → SHP101 (HoldPipe, 2.44 min — Stanbury et al. 2017 §Sterilization)
          → SHX102 (HXutility, cool to 30 °C)
          → SSP101 (Splitter, split = volumes[2] / sum(volumes))
              outs[0] → SR103  (~95 % of pooled seed flow)
              outs[1] → SSP102 (Splitter, split = volumes[0] / (volumes[0] + volumes[1]))
                            outs[0] → SR101  (~0.24 % of pooled seed flow)
                            outs[1] → SR102  (~4.75 % of pooled seed flow)

    Steady-state representation of periodic-batch seed vessels (Framework §6):

      Opex — effective continuous feed rate summed across all 3 stages:
          total_Q_seed = sum(volumes) / tau_seed   [m³/h]

      Capital — tau_seed = op_hours / (N_total × RESTARTS_PER_YEAR) makes
          BioSTEAM compute V_vessel = (Q × tau) / V_wf = V_work_i / V_wf,
          i.e. the correctly sized vessel for each stage.

      Split fractions derived from volumes (compute, don't assert — Framework §hard-rules):
          split_ssp101 = volumes[2] / sum(volumes)               # to SR103 (outs[0])
          split_ssp102 = volumes[0] / (volumes[0] + volumes[1])  # to SR101 (outs[0])

    Stage working volumes (INOCULUM_RATIO = 0.05, 3 stages):
      SR101: V_work_prod × 0.05³  (~34 L)
      SR102: V_work_prod × 0.05²  (~650 L)
      SR103: V_work_prod × 0.05¹  (~13 m³)

    Parameters
    ----------
    reactions : bst.Reaction
        Same growth reaction as R101 (force_reaction, X=epsilon).
    N_prod_total : int
        Total parallel production vessel count including N+1 spare (d['N_total']).
    V_work_prod : float
        Working volume per production vessel (m³) = d['V_total']/d['N_capacity'] × 0.8.
    S0 : float
        Substrate feed concentration (g/L = kg/m³) from design_reactor().
    X_star : float
        Target biomass titer (g/L = kg/m³) from design_reactor().
    nutrient_coeff : float
        g Nutrients per g biomass — from build_nutrients_properties().
    nh3_wt : float
        g NH3 per g substrate (mass ratio) — from stoichiometry in model builder.
    epsilon : float
        Substrate conversion extent (RouteParams.epsilon).
    feedstock_price : float
        $/kg substrate (RouteParams.feedstock_price).
    feedstock_id : str
        BioSTEAM chemical ID of the substrate (e.g. 'Fructose').
    composite_price : float
        $/kg Nutrients composite — from build_nutrients_properties().
    economics : EconomicBasis
        For ammonia_price and water_price.

    Returns
    -------
    units : list[bst.Unit]
        [ST201, ST202, ST203, SM101, SHX101, SHP101, SHX102, SSP101, SSP102,
         SR101, SR102, SR103] — append to fructose_system path after product_storage
        (Framework §6).
    waste_streams : list[bst.Stream]
        Liquid effluents from each stage (outs[1]) — pass to build_wastewater_treatment().
    """
    op_hours = effective_operating_hours()                          # h/yr

    # tau_seed: algebraic device so BioSTEAM computes V_vessel = V_work_i / V_wf
    # (derived: Q_seed_i × tau_seed = V_work_i — Framework §6)
    tau_seed = op_hours / (N_prod_total * RESTARTS_PER_YEAR)       # h ≈ 969 h

    # Three working volumes: stage 3 closest to production, stage 1 smallest.
    # V_work_i = V_work_prod × INOCULUM_RATIO^(4-stage_number)
    n_stages = 3
    volumes = [V_work_prod * INOCULUM_RATIO ** (n_stages - i + 1)
               for i in range(1, n_stages + 1)]
    # volumes[0] → SR101 (smallest, INOCULUM_RATIO³ × V_work_prod)
    # volumes[2] → SR103 (largest, INOCULUM_RATIO¹ × V_work_prod)

    # N_seed_trains: number of parallel physical seed train sets required to cover
    # concurrent restart events.  Each restart needs one complete 3-stage seed
    # batch (SEED_BATCH_DURATION_H); multiple restarts overlap when N_prod_total
    # is large — Framework §9.2.
    N_seed_trains = max(1, math.ceil(
        N_prod_total * RESTARTS_PER_YEAR * SEED_BATCH_DURATION_H / op_hours
    ))

    # Aggregated seed feed flows — sum across all 3 stages × N_seed_trains
    # (compute, don't hardcode)
    total_Q_seed  = sum(volumes) / tau_seed            # m³/h per concurrent seed train
    substrate_kgh = S0 * total_Q_seed
    nutrients_kgh = nutrient_coeff * X_star * total_Q_seed * (1.0 + NH3_NUTRIENTS_EXCESS)
    nh3_kgh       = nh3_wt * S0 * epsilon * total_Q_seed * (1.0 + NH3_NUTRIENTS_EXCESS)
    water_kgh     = total_Q_seed * 1000.0 - substrate_kgh - nutrients_kgh - nh3_kgh

    # Feed streams — sized to aggregate flow for ALL N_seed_trains concurrent trains
    seed_substrate_feed = bst.Stream('seed_substrate_feed',
                                     **{feedstock_id: substrate_kgh},
                                     units='kg/hr', price=feedstock_price)
    seed_nutrients_feed = bst.Stream('seed_nutrients_feed',
                                     Nutrients=nutrients_kgh,
                                     units='kg/hr', price=composite_price)
    seed_nh3_feed       = bst.Stream('seed_nh3_feed',
                                     NH3=nh3_kgh,
                                     units='kg/hr', price=economics.ammonia_price)
    seed_water_feed     = bst.Stream('seed_water_feed',
                                     H2O=water_kgh,
                                     units='kg/hr', price=economics.water_price / 1000.0)

    # Feedstock storage tanks — same tau as production-side ST101–ST103 (Framework §9.2)
    seed_substrate_storage = bst.StorageTank('ST201', ins=seed_substrate_feed, tau=STORAGE_TANK_TAU)
    seed_nutrients_storage = bst.StorageTank('ST202', ins=seed_nutrients_feed, tau=STORAGE_TANK_TAU)
    seed_nh3_storage       = bst.StorageTank('ST203', ins=seed_nh3_feed,       tau=STORAGE_TANK_TAU)

    # Shared sterilization track (Framework §9.2 — same T values as HX101/HX102)
    seed_mixer  = bst.MixTank('SM101',
                               ins=[seed_substrate_storage-0,
                                    seed_nutrients_storage-0,
                                    seed_nh3_storage-0,
                                    seed_water_feed],
                               tau=MIX_TANK_TAU)
    # Note: SM101/SHX101/SHX102 are modeled as single units sized for the aggregate
    # flow across all N_seed_trains concurrent seed preparations (correct opex);
    # capital scales sub-linearly with flow so the aggregate-basis cost is
    # conservative (slightly over-estimates per-unit cost vs. N_seed_trains
    # smaller parallel units).  Only the SR reactors are explicitly parallelized.
    seed_heater = bst.HXutility('SHX101', ins=seed_mixer-0,
                                 T=T_STERILIZATION_K, heat_only=True)
    seed_hold   = HoldPipe('SHP101', ins=seed_heater-0,
                            tau_min=STERILIZATION_HOLD_TAU_MIN)
    seed_cooler = bst.HXutility('SHX102', ins=seed_hold-0,
                                 T=T_FERMENTATION_K,  cool_only=True)

    # Splitters — fractions derived from volumes (compute, don't assert — Framework §hard-rules)
    V_total_seed = sum(volumes)
    split_ssp101 = volumes[2] / V_total_seed               # to SR103 (outs[0])
    split_ssp102 = volumes[0] / (volumes[0] + volumes[1])  # to SR101 (outs[0])

    seed_splitter_1 = bst.Splitter('SSP101', ins=seed_cooler-0,     split=split_ssp101)
    seed_splitter_2 = bst.Splitter('SSP102', ins=seed_splitter_1-1, split=split_ssp102)

    # Seed reactors — one sterilized inlet each
    #   SSP101-0 → SR103  (largest stage, ~95 %)
    #   SSP102-0 → SR101  (smallest stage, ~0.24 %)
    #   SSP102-1 → SR102  (middle stage,  ~4.75 %)
    inlets = [seed_splitter_2-0, seed_splitter_2-1, seed_splitter_1-0]  # stages 1, 2, 3

    sr_units: list[SeedBioreactor] = []
    for i, inlet in enumerate(inlets, start=1):
        sr = SeedBioreactor(
            f'SR1{i:02d}',
            ins=inlet,
            reactions=reactions,
            tau=tau_seed,
            T=T_FERMENTATION_K,
            N_seed_trains=N_seed_trains,   # Framework §9.2: parallel physical sets
        )
        sr_units.append(sr)

    units = [seed_substrate_storage, seed_nutrients_storage, seed_nh3_storage,
             seed_mixer, seed_heater, seed_hold, seed_cooler,
             seed_splitter_1, seed_splitter_2,
             *sr_units]
    waste_streams = [sr-1 for sr in sr_units]
    return units, waste_streams
