"""Sanity-check: compare actual BioSTEAM stream flows to LCA OP_FLOW_SPECS coverage.

Run from project root:
    python lca/stream_balance_check.py

Produces stdout-only report; writes nothing to disk.  Safe to re-run.

Report per route
----------------
1. SYSTEM BOUNDARY — FEED STREAMS
   Every stream in system.feeds (excluding recycle_water) with non-zero
   component flows and the OP_FLOW_SPECS row that covers each.

2. BIOREACTOR GAS VENTS (outs[0])
   Non-zero components from each bioreactor's gas vent and coverage.

3. SPRAY DRYER VAPOR (D101.outs[0])
   Evaporated water and any other non-zero vapor components.

4. LIQUID EFFLUENTS
   RCY101.outs[1] (discharge) and WWT102.outs[1] (sludge), component-by-component.

5. PRODUCT STREAM
   CNecatorBiomass and H2O flow from the ST104 outlet (not a system emission).

6. OP_FLOW_SPECS EVALUATED
   Every row in OP_FLOW_SPECS for this route evaluated against the simulated system.

7. COVERAGE CHECK
   Any non-zero system-boundary flow with no corresponding OP_FLOW_SPECS row.

Framework §8 — lca_config.py / lca_export.py.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import biosteam as bst

from common.lca_config import OP_FLOW_SPECS
from common.lca_export import _apply_conversion, _evaluate_accessor
from common.nutrients import build_nutrients_properties
from common.parameters import ECONOMICS, NUTRIENTS_RECIPE, get
from models.fructose_model import build_fructose_system
from models.gas_fermentation_model import build_gas_fermentation_system

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 2012 CEPCI — matches lca_config._CEPCI_LCA_BASE; used for cost-row conversions.
_CEPCI_LCA_BASE: float = 584.6

# Flows below this threshold (kg/hr) are treated as zero for reporting purposes.
_FLOW_THRESHOLD: float = 1e-6

# Stricter threshold for liquid effluent components (trace dissolved species).
_LIQUID_THRESHOLD: float = 1e-9

# Per-route units with a gas vent at outs[0].
# AeratedBioreactor subclasses (ExtentBasedBioreactor, SeedBioreactor) have
# outs[0] = gas vent.  PerfusionBioreactor R101 in gas ferm is a closed vessel
# with no gas vent — Framework §4a.  lca_config._BIOREACTOR_VENT_UNITS mirror.
_BIOREACTOR_VENT_UNITS: dict[str, list[str]] = {
    'fructose':         ['R101', 'SR101', 'SR102', 'SR103'],
    'gas_fermentation': ['SR101', 'SR102', 'SR103'],
}

_ROUTES: dict[str, object] = {
    'fructose':         build_fructose_system,
    'gas_fermentation': build_gas_fermentation_system,
}

_COL_FLOW = 14   # right-justified width for kg/hr values


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    """Right-justified kg/hr value with 4 decimal places."""
    return f'{v:>{_COL_FLOW}.4f}'


def _hr(width: int = 78) -> str:
    return '-' * width


# ---------------------------------------------------------------------------
# Coverage-map builders
# ---------------------------------------------------------------------------

def _feed_coverage(
    route: str,
    unit_map: dict[str, bst.Unit],
) -> dict[tuple[str, str], str]:
    """Map (stream_id, component) → row label for all tracked feed-stream flows.

    Dispatches on accessor type:
      feed_stream   — reads directly from stream_map[sid]
      h2o_feed_sum  — reads from stream_map[sid].imass['H2O'] for each sid
      unit_in_sum   — reads from unit.ins[idx]; resolves to the inlet stream ID
      cost_sum      — same resolution as unit_in_sum (Nutrients feed)
    """
    covered: dict[tuple[str, str], str] = {}
    for spec in OP_FLOW_SPECS[route]:
        label = spec['material']
        acc   = spec['accessor']
        t     = acc[0]

        if t == 'feed_stream':
            sid, comp = acc[1], acc[2]
            covered[(sid, comp)] = label

        elif t == 'h2o_feed_sum':
            for sid in acc[1]:
                covered[(sid, 'H2O')] = label

        elif t == 'unit_in_sum':
            # acc[1] = [(unit_id, in_idx, component), ...]
            for uid, idx, comp in acc[1]:
                if uid in unit_map:
                    s = unit_map[uid].ins[idx]
                    if s.ID:
                        covered[(s.ID, comp)] = label

        elif t == 'cost_sum':
            # acc[1] = [(unit_id, in_idx, component), ...]
            for uid, idx, comp in acc[1]:
                if uid in unit_map:
                    s = unit_map[uid].ins[idx]
                    if s.ID:
                        covered[(s.ID, comp)] = label

    return covered


def _vent_coverage(route: str) -> dict[tuple[str, str], str]:
    """Map (unit_id, component) → row label for bioreactor gas vent flows.

    Reads gas_out_sum accessor rows.  D101 (spray dryer) is intentionally
    excluded here — handled separately in _dryer_coverage so the dryer-vapor
    section can report its own coverage.
    """
    covered: dict[tuple[str, str], str] = {}
    for spec in OP_FLOW_SPECS[route]:
        acc = spec['accessor']
        if acc[0] == 'gas_out_sum':
            unit_ids, comp = acc[1], acc[2]
            for uid in unit_ids:
                if uid != 'D101':
                    covered[(uid, comp)] = spec['material']
    return covered


def _dryer_coverage(route: str) -> dict[tuple[str, str], str]:
    """Map ('D101', component) → row label for spray dryer vapor flows.

    D101 appears in gas_out_sum rows (e.g. the H2O air emissions row in liquid
    routes combines bioreactor vents + D101.outs[0]).  It may also appear via
    a dryer_vapor accessor (not currently used but handled for completeness).
    """
    covered: dict[tuple[str, str], str] = {}
    for spec in OP_FLOW_SPECS[route]:
        acc = spec['accessor']
        t   = acc[0]
        if t == 'gas_out_sum':
            unit_ids, comp = acc[1], acc[2]
            if 'D101' in unit_ids:
                covered[('D101', comp)] = spec['material']
        elif t == 'dryer_vapor':
            comp = acc[1]
            covered[('D101', comp)] = spec['material']
    return covered


def _liquid_coverage(
    route: str,
    nutrients_mass_fracs: dict[str, float],    # noqa: ARG001 — reserved for future unlump labels
) -> dict[tuple[str, int, str], str]:
    """Map (unit_id, out_idx, component) → row label for liquid effluent flows.

    Handles all accessor types that read from liquid effluent outlets:
      discharge           — RCY101.outs[1], one component per row
      unit_out_sum        — combines multiple (uid, idx) pairs into one row
      multi_out_unlump    — combines multiple (uid, idx) pairs then unlumps
                            via nutrients mass fraction; all 7 salt rows cover
                            the same (uid, idx, 'Nutrients') key — first match wins
      unit_out            — single outlet, single component (legacy, not in active specs)
      unit_out_unlump     — single outlet Nutrients unlump (legacy, not in active specs)
    """
    covered: dict[tuple[str, int, str], str] = {}
    for spec in OP_FLOW_SPECS[route]:
        label = spec['material']
        acc   = spec['accessor']
        t     = acc[0]

        if t == 'discharge':
            comp = acc[1]
            covered[('RCY101', 1, comp)] = label

        elif t == 'unit_out_sum':
            pairs, comp = acc[1], acc[2]
            for uid, idx in pairs:
                covered[(uid, idx, comp)] = label

        elif t == 'multi_out_unlump':
            pairs, nutrient_key = acc[1], acc[2]
            for uid, idx in pairs:
                key = (uid, idx, 'Nutrients')
                if key not in covered:
                    # All 7 salt rows share this key; record a combined label.
                    covered[key] = 'Nutrients -> unlumped to 7 salts [outs]'

        elif t == 'unit_out':
            uid, idx, comp = acc[1], acc[2], acc[3]
            covered[(uid, idx, comp)] = label

        elif t == 'unit_out_unlump':
            uid, idx, _nutrient_key = acc[1], acc[2], acc[3]
            key = (uid, idx, 'Nutrients')
            if key not in covered:
                covered[key] = 'Nutrients -> unlumped to 7 salts [outs]'

    return covered


# ---------------------------------------------------------------------------
# Per-route check
# ---------------------------------------------------------------------------

def _check_route(route: str, builder) -> None:
    """Run and print the full balance check for one route."""
    params = get(route)

    with bst.Flowsheet(route):
        system, _ = builder(params, ECONOMICS)
        system.simulate()

        unit_map:   dict[str, bst.Unit]   = {u.ID: u for u in system.units}
        stream_map: dict[str, bst.Stream] = {s.ID: s for s in system.streams if s.ID}

        composite_price, _, nutrients_mass_fracs = build_nutrients_properties(
            NUTRIENTS_RECIPE.concentrations,
            NUTRIENTS_RECIPE.prices,
            NUTRIENTS_RECIPE.achieved_titer,
        )
        cepci_ratio = _CEPCI_LCA_BASE / ECONOMICS.CEPCI

        print(f"\n{'='*70}")
        print(f"  {route.upper().replace('_', ' ')}")
        print(f"{'='*70}")

        # Accumulate all untracked non-zero boundary flows for section 7.
        untracked: list[tuple[str, str, float]] = []   # (location, component, kg/hr)

        # -------------------------------------------------------------------
        # 1. Feed streams
        # -------------------------------------------------------------------
        fc = _feed_coverage(route, unit_map)

        print("\nSYSTEM BOUNDARY — FEED STREAMS")
        print(f"  {'Stream':<24} {'Component':<22} {'kg/hr':>{_COL_FLOW}}  Tracked by row")
        print("  " + _hr(76))

        for stream in sorted(system.feeds, key=lambda s: s.ID or ''):
            if stream.ID == 'recycle_water':
                # Internal WWT recycle tear stream — not a purchased feed.
                # Framework §9.2: recycle_water is supplied by RCY101.outs[0].
                continue
            for comp in stream.chemicals.IDs:
                flow = stream.imass[comp]
                if flow < _FLOW_THRESHOLD:
                    continue
                key   = (stream.ID or '', comp)
                label = fc.get(key, '*** UNTRACKED ***')
                print(f"  {stream.ID or '(anon)':<24} {comp:<22} {_fmt(flow)}  {label}")
                if label == '*** UNTRACKED ***':
                    untracked.append((f'feed:{stream.ID}', comp, flow))

        # -------------------------------------------------------------------
        # 2. Bioreactor gas vents (outs[0])
        # -------------------------------------------------------------------
        vc = _vent_coverage(route)

        print("\nBIOREACTOR GAS VENTS (outs[0])")
        print(f"  {'Unit':<10} {'Component':<22} {'kg/hr':>{_COL_FLOW}}  Tracked by row")
        print("  " + _hr(76))

        for uid in _BIOREACTOR_VENT_UNITS[route]:
            if uid not in unit_map:
                print(f"  {uid:<10} (unit not found in system)")
                continue
            vent = unit_map[uid].outs[0]
            any_printed = False
            for comp in vent.chemicals.IDs:
                flow = vent.imass[comp]
                if flow < _FLOW_THRESHOLD:
                    continue
                any_printed = True
                key   = (uid, comp)
                label = vc.get(key, '*** UNTRACKED ***')
                print(f"  {uid:<10} {comp:<22} {_fmt(flow)}  {label}")
                if label == '*** UNTRACKED ***':
                    untracked.append((f'{uid}.outs[0]', comp, flow))
            if not any_printed:
                print(f"  {uid:<10} (no non-zero vent components)")

        # -------------------------------------------------------------------
        # 3. Spray dryer vapor (D101.outs[0])
        # -------------------------------------------------------------------
        dc = _dryer_coverage(route)

        print("\nSPRAY DRYER VAPOR (D101.outs[0])")
        print(f"  {'Unit':<10} {'Component':<22} {'kg/hr':>{_COL_FLOW}}  Tracked by row")
        print("  " + _hr(76))

        d101 = unit_map.get('D101')
        if d101 is None:
            print("  D101 not found in system.")
        else:
            vapor = d101.outs[0]
            any_printed = False
            for comp in vapor.chemicals.IDs:
                flow = vapor.imass[comp]
                if flow < _FLOW_THRESHOLD:
                    continue
                any_printed = True
                key   = ('D101', comp)
                label = dc.get(key, '*** UNTRACKED ***')
                print(f"  {'D101':<10} {comp:<22} {_fmt(flow)}  {label}")
                if label == '*** UNTRACKED ***':
                    untracked.append(('D101.outs[0]', comp, flow))
            if not any_printed:
                print("  D101      (no non-zero vapor components)")

        # -------------------------------------------------------------------
        # 4. Liquid effluents
        # -------------------------------------------------------------------
        lc = _liquid_coverage(route, nutrients_mass_fracs)

        print("\nLIQUID EFFLUENTS")
        for uid, idx, section_label in [
            ('RCY101', 1, 'RCY101.outs[1] - discharge'),
            ('WWT102', 1, 'WWT102.outs[1] - sludge'),
        ]:
            print(f"  {section_label}")
            print(f"    {'Component':<22} {'kg/hr':>{_COL_FLOW}}  Tracked by row")
            print("    " + _hr(70))

            if uid not in unit_map:
                print(f"    (unit {uid} not found in system)")
                print()
                continue

            outlet = unit_map[uid].outs[idx]
            any_printed = False
            for comp in outlet.chemicals.IDs:
                flow = outlet.imass[comp]
                if flow < _LIQUID_THRESHOLD:
                    continue
                any_printed = True
                key   = (uid, idx, comp)
                label = lc.get(key, '*** UNTRACKED ***')
                print(f"    {comp:<22} {_fmt(flow)}  {label}")
                if label == '*** UNTRACKED ***':
                    untracked.append((f'{uid}.outs[{idx}]', comp, flow))

            if not any_printed:
                print("    (no non-zero components)")
            print()

        # -------------------------------------------------------------------
        # 5. Product stream
        # -------------------------------------------------------------------
        product = max(
            (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
            key=lambda s: s.imass['CNecatorBiomass'],
        )
        biomass_kgh = product.imass['CNecatorBiomass']
        h2o_kgh     = product.imass['H2O']
        total_kgh   = biomass_kgh + h2o_kgh
        moisture_pct = (h2o_kgh / total_kgh * 100.0) if total_kgh > 0.0 else 0.0

        print("PRODUCT STREAM (not a system emission — ST104 outlet)")
        print(f"  CNecatorBiomass  {_fmt(biomass_kgh)} kg/hr")
        print(f"  H2O              {_fmt(h2o_kgh)} kg/hr  ({moisture_pct:.1f}% moisture)")

        # -------------------------------------------------------------------
        # 6. OP_FLOW_SPECS evaluated
        # -------------------------------------------------------------------
        print("\nOP_FLOW_SPECS EVALUATED")
        print(f"  {'Section':<7} {'Row label':<44} {'Units':<14} {'Value':>{_COL_FLOW}}")
        print("  " + _hr(82))

        for spec in OP_FLOW_SPECS[route]:
            raw   = _evaluate_accessor(
                spec['accessor'], unit_map, stream_map, ECONOMICS,
                composite_price, nutrients_mass_fracs,
            )
            value = _apply_conversion(
                raw, spec['accessor'][0], spec['units'], cepci_ratio,
            )
            print(
                f"  {spec['section']:<7} {spec['material']:<44}"
                f" {spec['units']:<14} {value:{_COL_FLOW}.4f}"
            )

        # -------------------------------------------------------------------
        # 7. Coverage check
        # -------------------------------------------------------------------
        print("\nCOVERAGE CHECK — untracked non-zero system-boundary flows")
        if not untracked:
            print("  None  (ok)")
        else:
            print(f"  {'Location':<32} {'Component':<22} {'kg/hr':>{_COL_FLOW}}")
            print("  " + _hr(72))
            for loc, comp, flow in untracked:
                print(f"  {loc:<32} {comp:<22} {_fmt(flow)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    for route, builder in _ROUTES.items():
        _check_route(route, builder)
    print()
    print('=' * 70)
    print('  CHECK COMPLETE')
    print('=' * 70)
