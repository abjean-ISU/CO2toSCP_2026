"""Shared wastewater-treatment (WWT) subsystem for all four SCP routes.

Public function
---------------
build_wastewater_treatment(wastewater_streams, economics, recycle_water)
    -> list[bst.Unit]

Design — three units
---------------------
  WWT101 — bst.Mixer
    Combines all wastewater streams (centrifuge effluent, spray-dryer condensate,
    and any other liquid waste streams passed in by the caller) into a single
    mixed wastewater feed.  Inline blending, zero capital — WWT101 is a pure
    stream combiner with no reaction or dissolution; zero capital, same as
    WWT102 (_SludgeSettler) and RCY101 (bst.Splitter).  Framework §9.2.

  WWT102 — _SludgeSettler (custom bst.Unit subclass; zero capital)
    Represents activated sludge / aerobic digestion with 99 % organic removal
    (WWT_ORGANIC_REMOVAL — Framework §9.2).  Mass balance:
      non-H2O → 99 % to sludge (outs[1]); 1 % to treated_water (outs[0])
      H2O     → water_to_sludge = WWT_SLUDGE_MOISTURE/(1−WWT_SLUDGE_MOISTURE)
                × dry_sludge_mass (= 4× dry mass at 80 % moisture);
                remainder to treated_water.
    At 80 % moisture, water lost to sludge is <1.1 % of the inlet water flow —
    negligible effect on the recycle water balance.  Framework §9.2.

    Sludge carries a negative price (wwt_organic_removal_cost $/kg).  BioSTEAM
    routes negative-priced product streams through system.sales (not
    material_cost), so the disposal cost does not appear in tea.VOC.  It is
    captured by solve_price() via total_production_cost = AOC - coproduct_sales:
    the negative sludge sales reduce coproduct_sales, which increases the
    effective production cost and therefore the MSP.

  RCY101 — bst.Splitter
    Splits the treated water: WWT_WATER_RECYCLE_FRACTION (75 %) to the process-
    feed recycle stream (outs[0] = recycle_water, pre-created by caller) and the
    remainder (25 %) to a treated-effluent discharge stream (outs[1]).

    The 75 % fraction is required to close the water mass balance: aerobic
    fermentation produces net H2O as a stoichiometric reaction product, so 100 %
    recycle causes unbounded accumulation.  A fraction < 1 makes the recycle loop
    a contraction mapping (gain = 0.75 < 1 → converges to a finite steady-state
    recycle flow).  Framework §9.2.

Recycle wiring (caller's responsibility)
-----------------------------------------
The caller must pre-create recycle_water (initialized with an estimated flow as
a convergence seed) and wire it as one inlet of the upstream feed mixer BEFORE
calling this function.  This function sets it as RCY101.outs[0].  The caller
closes the BioSTEAM recycle loop by passing the same stream to
bst.System(recycle=recycle_water):

    recycle_water = bst.Stream('recycle_water', H2O=seed_kgh)
    feed_mixer    = bst.Mixer('M101', ins=[..., recycle_water])
    ...
    wwt_units = build_wastewater_treatment([c101_eff, *seed_wastes], econ, recycle_water)
    system = bst.System('...', path=[..., *wwt_units], recycle=recycle_water)

Framework §9.2, §9.4 / Spec §common/wastewater.py.
"""

from __future__ import annotations

import biosteam as bst

from common.parameters import (
    EconomicBasis,
    WWT_ORGANIC_REMOVAL,
    WWT_SLUDGE_MOISTURE,
    WWT_WATER_RECYCLE_FRACTION,
)


# ---------------------------------------------------------------------------
# WWT102 implementation — moisture-constrained sludge settler
# ---------------------------------------------------------------------------

class _SludgeSettler(bst.Unit):
    """Activated-sludge WWT with 99% organic removal and moisture-controlled sludge.

    outs[0] = treated_water  (99% + sludge-moisture remainder pass-through)
    outs[1] = sludge         (99% of organics + sludge water; priced by caller)

    Parameters
    ----------
    organic_removal : float
        Fraction of each non-H2O component routed to sludge (WWT_ORGANIC_REMOVAL).
    sludge_moisture : float
        Target moisture of dewatered sludge, wt H2O / wt total (WWT_SLUDGE_MOISTURE).

    No _design or _cost overrides — zero capital, consistent with WWT101 (bst.Mixer)
    and RCY101 (bst.Splitter).  Framework §9.2.
    """

    _N_ins = 1
    _N_outs = 2   # outs[0] = treated_water, outs[1] = sludge

    def __init__(
        self,
        ID: str = '',
        ins: object = None,
        outs: object = (),
        *,
        organic_removal: float,
        sludge_moisture: float,
    ) -> None:
        super().__init__(ID, ins=ins, outs=outs)
        self.organic_removal = organic_removal
        self.sludge_moisture = sludge_moisture

    def _run(self) -> None:
        feed = self.ins[0]
        treated, sludge = self.outs

        # Step 1 — route organic_removal fraction of each non-H2O component to sludge.
        # Remaining (1 - organic_removal) fraction goes to treated water.
        dry_sludge_kg_hr: float = 0.0
        for c in bst.settings.chemicals:
            if c.ID == 'H2O':
                continue
            to_sludge = self.organic_removal * feed.imass[c.ID]
            sludge.imass[c.ID] = to_sludge
            treated.imass[c.ID] = feed.imass[c.ID] - to_sludge
            dry_sludge_kg_hr += to_sludge

        # Step 2 — water to sludge: sludge_moisture/(1−sludge_moisture) × dry mass.
        # At 80 % moisture → water_to_sludge = 4 × dry_sludge_mass (Framework §9.2).
        water_to_sludge = (
            self.sludge_moisture / (1.0 - self.sludge_moisture) * dry_sludge_kg_hr
        )
        # Guard: cannot remove more water than is available in the feed
        water_to_sludge = min(water_to_sludge, feed.imass['H2O'])
        sludge.imass['H2O'] = water_to_sludge
        treated.imass['H2O'] = feed.imass['H2O'] - water_to_sludge


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_wastewater_treatment(
    wastewater_streams: list[bst.Stream],
    economics: EconomicBasis,
    recycle_water: bst.Stream,
) -> list[bst.Unit]:
    """Build WWT101 (mixer), WWT102 (sludge settler), RCY101 (recycle splitter).

    Parameters
    ----------
    wastewater_streams : list[bst.Stream]
        All streams to be treated (e.g. centrifuge effluent, spray dryer
        condensate).  Do not include the recycle stream itself.
    economics : EconomicBasis
        Provides wwt_organic_removal_cost ($/kg organic removed — Framework §9.4).
    recycle_water : bst.Stream
        Pre-created stream wired into the upstream feed mixer.  This function
        sets it as RCY101.outs[0], completing the recycle topology.

    Returns
    -------
    list[bst.Unit]
        [WWT101, WWT102, RCY101] — append to the system path after the spray dryer.
    """
    # ------------------------------------------------------------------
    # WWT101 — inline combiner for all wastewater feeds (Framework §9.2)
    # Modeled as bst.Mixer (zero capital) — WWT101 combines centrifuge effluent,
    # dryer condensate, and seed wastes with no reaction or dissolution.
    # ------------------------------------------------------------------
    wwt_mixer = bst.Mixer(
        'WWT101',
        ins=wastewater_streams,
    )

    # ------------------------------------------------------------------
    # WWT102 — _SludgeSettler: 99% organic removal, 80% moisture sludge
    #   non-H2O → 99% to sludge (outs[1]), 1% to treated_water (outs[0])
    #   H2O     → 4× dry sludge mass to sludge; remainder to treated_water
    # ------------------------------------------------------------------
    wwt_settler = _SludgeSettler(
        'WWT102',
        ins=wwt_mixer - 0,
        organic_removal=WWT_ORGANIC_REMOVAL,
        sludge_moisture=WWT_SLUDGE_MOISTURE,
    )

    sludge = wwt_settler - 1
    # Negative price → WWT operating cost deducted from VOC by BioSTEAM (Framework §9.4).
    # wwt_organic_removal_cost is $/kg DRY organic removed (Seider et al.).  BioSTEAM
    # charges price × total_sludge_mass, so scale by (1 − moisture) so that:
    #   cost = [−c × (1−m)] × [dry_mass / (1−m)] = −c × dry_mass  ✓
    sludge.price = -economics.wwt_organic_removal_cost * (1.0 - WWT_SLUDGE_MOISTURE)
    # Negative price → disposal cost flows through system.sales in BioSTEAM, not
    # material_cost.  solve_price() captures it correctly via total_production_cost;
    # export.py adds it explicitly to the VOC total for display consistency.

    # ------------------------------------------------------------------
    # RCY101 — recycle fraction splitter
    #   outs[0] = recycle_water (75 %) → pre-created caller stream (M101 inlet)
    #   outs[1] = discharge      (25 %) → exits system, price = 0
    # ------------------------------------------------------------------
    rcy_splitter = bst.Splitter(
        'RCY101',
        ins=wwt_settler - 0,           # treated_water from WWT102
        outs=[recycle_water, 'discharge'],
        split=WWT_WATER_RECYCLE_FRACTION,   # 0.75 uniformly for all components
    )

    # discharge is clean treated water; no cost or revenue assigned
    rcy_splitter - 1   # discharge stream — price defaults to 0.0

    return [wwt_mixer, wwt_settler, rcy_splitter]
