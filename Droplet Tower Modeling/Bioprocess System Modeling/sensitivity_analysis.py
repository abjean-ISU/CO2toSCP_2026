"""One-at-a-time (OAT) sensitivity analysis: calls each route builder repeatedly
with perturbed parameters and records MSP swings for tornado diagrams.

Framework §11 — SA parameters per §9 registry (non-n/a SA ranges) plus
contingency_fee_factor (§9.4: ±35% Turton BM method accuracy, TCI uncertainty).

Outputs (all in outputs/):
    sensitivity_results.xlsx        — "OAT Results" + "Tornado Summary" sheets
    sensitivity_tornado_{route}.png — one per route (4 files for full run)

Usage:
    python sensitivity_analysis.py                      # all 4 routes
    from sensitivity_analysis import run_oat_sensitivity
    paths = run_oat_sensitivity(routes=['fructose'])    # subset
"""

from __future__ import annotations

import contextlib
import dataclasses
import pathlib
import typing
import warnings

import colorsys

import matplotlib
matplotlib.use('Agg')   # non-GUI backend — Framework §11 / plan spec
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import biosteam as bst
import pandas as pd

import common.parameters as _params
from common.parameters import ECONOMICS, get
from common.economics import build_tea
from models.fructose_model          import build_fructose_system
from models.acetate_model           import build_acetate_system
from models.formate_model           import build_formate_system
from models.gas_fermentation_model  import build_gas_fermentation_system

# Module-level references needed for multi-target patching (see _patch_attrs /
# _global_patches below).  The model modules are already loaded by the imports
# above; these aliases give us mutable module objects so we can patch the
# local bindings that were created by each module's own `from ... import X`.
import models.fructose_model          as _fructose_model
import models.acetate_model           as _acetate_model
import models.formate_model           as _formate_model
import models.gas_fermentation_model  as _gas_ferm_model
import common.chemicals               as _chemicals
import common.operating_hours         as _op_hours
import common.seed_train              as _seed_train
import common.wastewater              as _wastewater
from common.operating_hours import effective_operating_hours


# ---------------------------------------------------------------------------
# SA parameter registry — 12 parameters
# ---------------------------------------------------------------------------

class _SAParam(typing.NamedTuple):
    category:    str            # 'economics' | 'route' | 'global' | 'global_recipe_conc'
    field:       str            # EconomicBasis/RouteParams field name, or _params module attr
    label:       str            # tornado y-axis label
    lo:          float          # low absolute value, or low factor (if is_relative)
    hi:          float          # high absolute value, or high factor (if is_relative)
    is_relative: bool           # True → actual = base_value × lo/hi
    section:     str            # §9.x citation for audit trail
    skip_lo:     frozenset = frozenset()  # routes to skip the low perturbation
    skip_hi:     frozenset = frozenset()  # routes to skip the high perturbation


_SA_PARAMS: list[_SAParam] = [
    # §9.2 — design / kinetics
    # Justification: engineering judgment for range per §9.2 (ranges confirmed in plan)
    # gas_fermentation base ε = 0.99; lo=0.80 is so far below base it is not
    # a useful perturbation point — skip lo, run only hi=0.95 for that route.
    _SAParam('route',            'epsilon',                   'Substrate conversion (ε)',        0.80,  0.95,  False, '§9.2',
             skip_lo=frozenset({'gas_fermentation'})),
    _SAParam('route',            'D_margin',                  'Dilution rate (fraction of μmax)', 0.70,  0.85,  False, '§9.2'),
    _SAParam('route',            'target_titer_fraction',     'Target titer (fraction of max)',   0.60,  0.90,  False, '§9.2'),
    _SAParam('global',           'CENTRIFUGE_RECOVERY',       'Centrifuge recovery (% biomass)',  0.90,  0.98,  False, '§9.2'),
    _SAParam('global',           'RESTART_FREQUENCY_PER_LINE','Restart frequency (per line/yr)', 1.0,   4.0,   False, '§9.2'),
    # §9.3 — nutrients: ×0.50 → coeff ≈0.195 g/g; ×1.50 → coeff ≈0.584 g/g (§9.3 range 0.20–0.59 g/g)
    _SAParam('global_recipe_conc','NUTRIENTS_RECIPE',         'Nutrient recipe scaling (×base)', 0.50,  1.50,  True,  '§9.3'),
    # §9.4 — prices / economics
    # feedstock_price: ±50% per route (commodity market uncertainty)
    _SAParam('route',            'feedstock_price',           'Feedstock price ($/kg)',           0.50,  1.50,  True,  '§9.4'),
    # electricity_price: §9.4 $0.020 (DOE Wind PPA floor) – $0.087 (US industrial grid Apr 2026)
    _SAParam('economics',        'electricity_price',         'Electricity price ($/kWh)',       0.020, 0.087, False, '§9.4'),
    # contingency_fee_factor: Turton BM method accuracy ±35%; FCI scales linearly → TCI ±35%
    # Chart label is "Capital cost (TCI ±35%)" not "contingency_fee_factor" — plan spec
    _SAParam('economics',        'contingency_fee_factor',    'Capital cost (TCI ±35%)',         0.65,  1.35,  True,  '§9.4'),
    # §9.2 — water recycle fraction: 0.50–0.90 (engineering range; 75 % base keeps loop
    # a contraction mapping; lower → more fresh water; higher → accumulation risk)
    _SAParam('global',           'WWT_WATER_RECYCLE_FRACTION','Water recycle fraction',          0.50,  0.90,  False, '§9.2'),
    # §4a — BGAL liquid holdup: baseline 0.2% (Q_max=0.577 m³/s).
    # lo=0.0577 (0.02% holdup), hi=11.5 (4% holdup); gas fermentation route only.
    # Liquid routes (fructose/acetate/formate) have no droplet columns — skip entirely.
    _SAParam('global',           'DC_Q_MAX_M3S',              'BGAL liquid holdup',             0.0577, 11.5, False, '§4a',
             skip_lo=frozenset({'fructose', 'acetate', 'formate'}),
             skip_hi=frozenset({'fructose', 'acetate', 'formate'})),
]


# ---------------------------------------------------------------------------
# Builder registry (mirrors run_models.py exactly — Framework §10)
# ---------------------------------------------------------------------------

_BUILDERS: dict[str, object] = {
    'fructose':          build_fructose_system,
    'acetate':           build_acetate_system,
    'formate':           build_formate_system,
    'gas_fermentation':  build_gas_fermentation_system,
}

_ALL_ROUTES: list[str] = ['fructose', 'acetate', 'formate', 'gas_fermentation']

# Route base colors — Okabe-Ito colorblind-friendly palette (2008 Nature Methods).
# Defined here (not in additional_analyses) so that _plot_tornado can use them
# without a circular import; additional_analyses.py imports from here.
_ROUTE_COLORS: dict[str, str] = {
    'fructose':         '#E69F00',  # orange
    'acetate':          '#56B4E9',  # sky blue
    'formate':          '#009E73',  # bluish green
    'gas_fermentation': '#CC79A7',  # reddish purple
}

_OUTPUTS_DIR: pathlib.Path = pathlib.Path(__file__).parent / 'outputs'


# ---------------------------------------------------------------------------
# OPEX extraction — shared with additional_analyses.py (Framework §11)
# ---------------------------------------------------------------------------

_COST_CATEGORIES_ORDER: list[str] = [
    'Feedstock',
    'Ammonia',
    'Nutrients',
    'Electricity',
    'Other utilities',
    'Waste disposal',
    'Labor',
    'Maintenance',
    'Other FOC',
    'Capital charge',
]


def _identify_stream_category(stream: bst.Stream) -> str | None:
    """Return cost category for a feed stream, or None if not a costed feed.

    Checked in order:
    1. nutrients_feed → Nutrients
    2. Ammonia content → Ammonia
    3. Fructose, AceticAcid, FormicAcid, or H2 → Feedstock
    4. Any remaining positive-cost stream → labeled by stream.ID
    Returns None for zero-cost or negative-cost streams.
    """
    if stream.cost <= 0.0:
        return None
    if stream.ID == 'nutrients_feed':
        return 'Nutrients'
    try:
        if stream.imass['NH3'] > 0.0:
            return 'Ammonia'
    except Exception:
        pass
    for chem in ('Fructose', 'AceticAcid', 'FormicAcid', 'H2'):
        try:
            if stream.imass[chem] > 0.0:
                return 'Feedstock'
        except Exception:
            pass
    return stream.ID   # remaining positive-cost feeds labeled by ID


def _extract_opex_breakdown(system, tea, msp: float) -> dict:
    """Extract OPEX cost components from a simulated system.

    Returns a flat dict with keys '{category} ($/kg)' and '{category} ($MM/yr)'
    for each category in _COST_CATEGORIES_ORDER.  Capital charge is the MSP
    residual after all other costs, capturing depreciation + tax + required
    return.  Sums exactly to MSP × prod_kg_yr.

    Called inside the bst.Flowsheet context in _run_single_with_design so that
    stream and tea objects are live.  Framework §11.
    """
    op_hours = effective_operating_hours()  # reads patched _op_hours.CONTAMINATION_RESTART_H

    product = max(
        (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
        key=lambda s: s.imass['CNecatorBiomass'],
    )
    prod_kg_yr = product.F_mass * op_hours   # kg/yr (includes 5% spray-dryer moisture — matches MSP basis)
    if prod_kg_yr <= 0.0:
        return {}

    cats: dict[str, float] = {c: 0.0 for c in _COST_CATEGORIES_ORDER}

    # Feed streams
    for stream in system.feeds:
        cat = _identify_stream_category(stream)
        if cat is None:
            continue
        cost_yr = stream.cost * op_hours   # $/yr
        if cat in cats:
            cats[cat] += cost_yr
        else:
            cats['Feedstock'] += cost_yr   # unlabeled feeds → feedstock

    # Electricity
    cats['Electricity'] = system.power_utility.cost * op_hours

    # Other utilities (heat agents: steam, cooling water)
    heat_cost_yr = 0.0
    for hu in system.heat_utilities:
        if hu.cost > 0.0:
            heat_cost_yr += hu.cost * op_hours
    cats['Other utilities'] = heat_cost_yr

    # Waste disposal — negative-priced product streams (WWT sludge)
    waste_cost_yr = 0.0
    for stream in system.products:
        if stream.cost < 0.0:
            waste_cost_yr += abs(stream.cost) * op_hours
    cats['Waste disposal'] = waste_cost_yr

    # Fixed operating costs
    cats['Labor']       = tea.labor_cost                    # $/yr
    cats['Maintenance'] = tea.maintenance * tea.FCI         # $/yr
    cats['Other FOC']   = (tea.property_tax + tea.property_insurance
                           + tea.administration) * tea.FCI  # $/yr

    # Capital charge — residual so sum = MSP exactly
    msp_per_yr   = msp * prod_kg_yr
    all_other_yr = sum(cats[c] for c in _COST_CATEGORIES_ORDER if c != 'Capital charge')
    cats['Capital charge'] = msp_per_yr - all_other_yr

    result: dict = {}
    for cat in _COST_CATEGORIES_ORDER:
        val_yr = cats[cat]
        result[f'{cat} ($/kg)']    = round(val_yr / prod_kg_yr, 4)
        result[f'{cat} ($MM/yr)']  = round(val_yr / 1e6, 3)
    return result


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _patch_attrs(patches: list[tuple]):
    """Temporarily apply multiple (module, attr, value) patches; restore all on exit.

    Replaces the single-target _patch_global approach.  Needed because model
    files and common/* modules bind global parameters via `from X import Y`,
    creating local names that are frozen at import time.  Patching only
    _params.CENTRIFUGE_RECOVERY (etc.) has no effect on those local bindings —
    every module that imported the name directly must be patched separately.

    Framework §11 / plan spec perturbation logic.
    """
    originals = [(mod, attr, getattr(mod, attr)) for mod, attr, _ in patches]
    for mod, attr, val in patches:
        setattr(mod, attr, val)
    try:
        yield
    finally:
        for mod, attr, orig in originals:
            setattr(mod, attr, orig)


def _global_patches(field: str, val) -> list[tuple]:
    """Return the list of (module, attr, value) patches for a 'global' SA field.

    CENTRIFUGE_RECOVERY — imported directly in all 4 model modules → patch each.

    RESTART_FREQUENCY_PER_LINE — never imported by model builders; the live
    constant is CONTAMINATION_RESTART_H in common/operating_hours.py (used by
    effective_operating_hours()) and re-bound in common/seed_train.py.
    Patch both, deriving CONTAMINATION_RESTART_H = val × RESTART_DURATION_H.

    NUTRIENTS_RECIPE — imported in all 4 model modules and in common/chemicals.py
    (used inside build_chemicals()).  Patch each.

    WWT_WATER_RECYCLE_FRACTION — imported in all 4 model modules (used to compute
    the recycle-water seed flow at build time) and in common/wastewater.py (used
    as split fraction inside build_wastewater_treatment() at call time).  Patch each.
    """
    _ALL_MODELS = [_fructose_model, _acetate_model, _formate_model, _gas_ferm_model]

    if field == 'CENTRIFUGE_RECOVERY':
        return (
            [(_params, field, val)]
            + [(m, field, val) for m in _ALL_MODELS]
        )

    if field == 'RESTART_FREQUENCY_PER_LINE':
        # val is restarts/yr; CONTAMINATION_RESTART_H = val × RESTART_DURATION_H
        contamination_h = val * _op_hours.RESTART_DURATION_H
        return [
            (_params,      'RESTART_FREQUENCY_PER_LINE', val),
            (_op_hours,    'CONTAMINATION_RESTART_H',    contamination_h),
            (_seed_train,  'CONTAMINATION_RESTART_H',    contamination_h),
        ]

    if field == 'WWT_WATER_RECYCLE_FRACTION':
        return (
            [(_params, field, val), (_wastewater, field, val)]
            + [(m, field, val) for m in _ALL_MODELS]
        )

    if field == 'DC_Q_MAX_M3S':
        # _params holds the registry value; _gas_ferm_model holds the local binding
        # frozen at import time by `from common.parameters import DC_Q_MAX_M3S`.
        # Same pattern as CENTRIFUGE_RECOVERY and WWT_WATER_RECYCLE_FRACTION.
        return [
            (_params,         'DC_Q_MAX_M3S', val),
            (_gas_ferm_model, 'DC_Q_MAX_M3S', val),
        ]

    raise ValueError(f'No patch targets defined for global field {field!r}')


def _run_single(route: str, params, economics, run_id: int) -> float:
    """Build + simulate + TEA + solve_price for one (route, params, economics).

    run_id gives each invocation a unique Flowsheet name to avoid stream/unit
    ID collisions — same pattern as the bst.Flowsheet(route) context in
    run_models.py (Framework §10).  CostWarnings suppressed; irrelevant to
    tornado comparisons.
    """
    flowsheet_id = f'_sa_{route}_{run_id}'
    with bst.Flowsheet(flowsheet_id):
        builder = _BUILDERS[route]
        system, _ = builder(params, economics)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            system.simulate()
        tea = build_tea(system, economics)
        product = max(
            (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
            key=lambda s: s.imass['CNecatorBiomass'],
        )
        return tea.solve_price(product)


def _extract_design_vars(system, tea) -> dict:
    """Extract key design scalars from a simulated system + TEA.

    Captures op_hours (the mechanism behind restart-frequency sensitivity),
    FCI, reactor vessel count, volumetric throughput, seed train count, and
    (gas fermentation only) parallel droplet column counts for DC101/DC102.
    All values derived from the live simulation state — never asserted.
    """
    r101  = next((u for u in system.units if u.ID == 'R101'),  None)
    sr101 = next((u for u in system.units if u.ID == 'SR101'), None)
    dc101 = next((u for u in system.units if u.ID == 'DC101'), None)
    dc102 = next((u for u in system.units if u.ID == 'DC102'), None)

    # ExtentBasedBioreactor (liquid routes) stores vessel count as N_reactors;
    # PerfusionBioreactor (gas fermentation) stores it as N.
    n_reactors = getattr(r101, 'N_reactors', None)
    if n_reactors is None:
        n_reactors = getattr(r101, 'N', None)
    if n_reactors is not None:
        n_reactors = int(n_reactors)
    n_seed_trains = int(getattr(sr101, 'N_seed_trains', 0) or 0) or None

    q_m3h = None
    if r101 is not None:
        try:
            q_m3h = round(float(sum(s.F_vol for s in r101.ins)), 1)
        except Exception:
            pass

    # Droplet column parallel counts — None for liquid routes (no DC units).
    # design_results populated during simulate(); 'Number of columns' set in _design().
    n_dc101 = (int(dc101.design_results['Number of columns']) if dc101 is not None else None)
    n_dc102 = (int(dc102.design_results['Number of columns']) if dc102 is not None else None)

    return {
        'op_hours (h/yr)':          round(effective_operating_hours()),
        'FCI ($MM)':                round(tea.FCI / 1e6, 1),
        'N_reactors':               n_reactors,
        'N_seed_trains':            n_seed_trains,
        'Q (m³/h)':                 q_m3h,
        'N_DC101 (H2 columns)':     n_dc101,
        'N_DC102 (CO2/O2 columns)': n_dc102,
    }


def _run_single_with_design(
    route: str, params, economics, run_id: int,
) -> tuple[float, dict, dict]:
    """Like _run_single but also returns design-variable and OPEX-breakdown dicts.

    Used by the OAT loop to populate extra columns in OAT Results.
    Returns (msp, design, opex) where:
      design — op_hours, FCI, N_reactors, N_seed_trains, Q
      opex   — per-category $/kg and $MM/yr (Feedstock, Ammonia, ..., Capital charge)
    All extraction happens inside the Flowsheet context while objects are live.
    """
    flowsheet_id = f'_sa_{route}_{run_id}'
    with bst.Flowsheet(flowsheet_id):
        system, _ = _BUILDERS[route](params, economics)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            system.simulate()
        tea = build_tea(system, economics)
        product = max(
            (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
            key=lambda s: s.imass['CNecatorBiomass'],
        )
        msp    = tea.solve_price(product)
        design = _extract_design_vars(system, tea)
        opex   = _extract_opex_breakdown(system, tea, msp)
    return msp, design, opex


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def _export_sa_excel(
    records: list[dict],
    routes: list[str],
    base_designs: dict[str, dict] | None = None,
    base_opex_by_route: dict[str, dict] | None = None,
) -> pathlib.Path:
    """Write sensitivity_results.xlsx with three sheets.

    OAT Results      — one row per (parameter × direction × route); includes
                       design variables (op_hours, FCI, N_reactors, etc.)
                       captured during each perturbed simulation.
    Tornado Summary  — one row per parameter, sorted descending by max |swing|
                       across all routes and directions.
    Base Case Design — one row per route: base-case MSP + design variables.
                       Shows the "control" state that each OAT row deviates from.
    Framework §11.
    """
    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUTS_DIR / 'sensitivity_results.xlsx'

    df = pd.DataFrame(records)

    # Build Tornado Summary
    ts_rows: list[dict] = []
    for param in _SA_PARAMS:
        row: dict = {
            'Label':    param.label,
            'Category': param.category,
            'Section':  param.section,
        }
        for route in routes:
            sub = df[(df['Route'] == route) & (df['Parameter'] == param.field)]
            lo_series = sub.loc[sub['Direction'] == 'low',  'MSP swing ($/kg)'].values
            hi_series = sub.loc[sub['Direction'] == 'high', 'MSP swing ($/kg)'].values
            lo_swing = float(lo_series[0]) if len(lo_series) else float('nan')
            hi_swing = float(hi_series[0]) if len(hi_series) else float('nan')
            row[f'{route}_lo']    = lo_swing
            row[f'{route}_hi']    = hi_swing
            row[f'{route}_range'] = abs(hi_swing - lo_swing)
        ts_rows.append(row)

    ts_df = pd.DataFrame(ts_rows)

    # Sort descending by max absolute swing across all routes and directions
    swing_cols = [c for c in ts_df.columns if c.endswith('_lo') or c.endswith('_hi')]
    ts_df['_sort_key'] = ts_df[swing_cols].abs().max(axis=1)
    ts_df = ts_df.sort_values('_sort_key', ascending=False).drop(columns='_sort_key')

    # Base Case Design sheet — one row per route
    bc_rows = []
    for route in routes:
        row_bc: dict = {'Route': route}
        # Pull base MSP from any OAT record for this route
        route_rows = df[df['Route'] == route]
        if len(route_rows):
            row_bc['Base MSP ($/kg)'] = round(float(route_rows['Base MSP ($/kg)'].iloc[0]), 4)
        if base_designs and route in base_designs:
            row_bc.update(base_designs[route])
        if base_opex_by_route and route in base_opex_by_route:
            row_bc.update(base_opex_by_route[route])
        bc_rows.append(row_bc)
    bc_df = pd.DataFrame(bc_rows)

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='OAT Results', index=False)
        ts_df.to_excel(writer, sheet_name='Tornado Summary', index=False)
        bc_df.to_excel(writer, sheet_name='Base Case Design', index=False)

    return out_path


# ---------------------------------------------------------------------------
# Tornado plots
# ---------------------------------------------------------------------------

def _plot_tornado(records: list[dict], route: str, base_msp: float) -> pathlib.Path:
    """Write outputs/sensitivity_tornado_{route}.png.

    Y-axis: parameter labels sorted by |swing_hi − swing_lo| ascending so the
    largest-impact parameter appears at the top of the chart (barh plots bottom→top).
    X-axis: MSP swing ($/kg SCP), zero-centered.  Framework §11 / plan spec.
    """
    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUTS_DIR / f'sensitivity_tornado_{route}.png'

    route_records = [r for r in records if r['Route'] == route]
    df = pd.DataFrame(route_records)

    # Collect (swing_lo, swing_hi) per parameter label
    data: dict[str, tuple[float, float]] = {}
    for param in _SA_PARAMS:
        # Omit parameters that don't apply to this route at all
        if route in param.skip_lo and route in param.skip_hi:
            continue
        sub = df[df['Parameter'] == param.field]
        lo_row = sub[sub['Direction'] == 'low']
        hi_row = sub[sub['Direction'] == 'high']
        lo_swing = float(lo_row['MSP swing ($/kg)'].values[0]) if len(lo_row) else 0.0
        hi_swing = float(hi_row['MSP swing ($/kg)'].values[0]) if len(hi_row) else 0.0
        data[param.label] = (lo_swing, hi_swing)

    # Sort ascending by |swing_hi − swing_lo| → largest impact ends at top (highest y)
    sorted_labels = sorted(data.keys(), key=lambda lbl: abs(data[lbl][1] - data[lbl][0]))

    n_params = len(sorted_labels)

    plt.rcParams.update({
        'font.family':      'sans-serif',
        'font.size':        14,
        'axes.titlesize':   15,
        'axes.labelsize':   14,
        'xtick.labelsize':  12,
        'ytick.labelsize':  13,
        'figure.facecolor': 'white',
        'axes.facecolor':   'white',
        'hatch.linewidth':  1.5,
    })

    fig, ax = plt.subplots(figsize=(12, max(8, n_params * 0.6)))

    y = list(range(n_params))
    swing_lo = [data[lbl][0] for lbl in sorted_labels]
    swing_hi = [data[lbl][1] for lbl in sorted_labels]

    # Route colour with dark/light shades — Framework §11.
    # Fixed HLS lightness targets keep H and S constant so both shades read as
    # the same colour family.  L = 0.22 (dark) and L = base + 0.32 (light, capped
    # at 0.84) guarantee a wide perceptual gap regardless of the base colour's L.
    r, g, b = mcolors.to_rgb(_ROUTE_COLORS.get(route, '#888888'))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    dark_color  = colorsys.hls_to_rgb(h, max(l * 0.5, 0.15), s)
    light_color = colorsys.hls_to_rgb(h, min(l + 0.32, 0.84), s)
    ax.barh(y, swing_lo, color=dark_color,  label='Low perturbation',
            hatch='', edgecolor='black', linewidth=0.4)
    ax.barh(y, swing_hi, color=light_color, label='High perturbation',
            hatch='//', edgecolor='black', linewidth=0.4)

    ax.set_yticks(y)
    ax.set_yticklabels(sorted_labels, fontsize=13)
    ax.axvline(0, color='k', lw=0.8)
    ax.set_xlabel('MSP swing ($/kg SCP)', fontsize=14)
    ax.legend(loc='upper right', fontsize=11)
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    return out_path


# ---------------------------------------------------------------------------
# Plot-only helper (no simulations)
# ---------------------------------------------------------------------------

def replot_tornados(
    excel_path: pathlib.Path | None = None,
    routes: list[str] | None = None,
) -> dict[str, pathlib.Path]:
    """Regenerate tornado PNGs from an existing sensitivity_results.xlsx.

    Reads the 'OAT Results' sheet; no simulations are run.  Useful when only
    plot styling changes (e.g. removing titles) without re-running all runs.
    """
    if excel_path is None:
        excel_path = _OUTPUTS_DIR / 'sensitivity_results.xlsx'
    if routes is None:
        routes = _ALL_ROUTES

    df = pd.read_excel(excel_path, sheet_name='OAT Results')
    records = df.to_dict('records')

    output_paths: dict[str, pathlib.Path] = {}
    for route in routes:
        route_rows = df[df['Route'] == route]
        if route_rows.empty:
            continue
        base_msp = float(route_rows['Base MSP ($/kg)'].iloc[0])
        png_path = _plot_tornado(records, route, base_msp)
        output_paths[f'tornado_{route}'] = png_path
        print(f'[{route}] Tornado -> {png_path}')

    return output_paths


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_oat_sensitivity(
    routes: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, pathlib.Path]:
    """Run OAT sensitivity analysis for the specified routes.

    Simulation count for all 4 routes:
        4 base runs + 11 params × 2 dirs × 4 routes
        − 1 (gas_ferm ε lo skip)
        − 6 (DC_Q_MAX_M3S lo+hi skipped for fructose/acetate/formate)
        = 81 OAT runs + 4 base = 85 total.

    Parameters
    ----------
    routes : list[str] | None
        Route names to include. Defaults to all four routes.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    dict
        Keys: 'excel', and 'tornado_{route}' for each route.
        Values: pathlib.Path objects for output files.
    """
    if routes is None:
        routes = _ALL_ROUTES

    run_id: int = 0
    records: list[dict] = []
    base_msps: dict[str, float] = {}
    base_designs: dict[str, dict] = {}
    base_opex_by_route: dict[str, dict] = {}

    # --- Base runs (one per route) ---
    for route in routes:
        if verbose:
            print(f'[{route}] Base run...')
        run_id += 1
        base_msp, design, base_opex = _run_single_with_design(route, get(route), ECONOMICS, run_id)
        base_msps[route] = base_msp
        base_designs[route] = design
        base_opex_by_route[route] = base_opex
        if verbose:
            print(f'[{route}] Base MSP = ${base_msp:.2f}/kg')

    # --- OAT perturbations ---
    for param in _SA_PARAMS:
        for direction, lo_or_hi in [('low', param.lo), ('high', param.hi)]:
            for route in routes:
                # Skip directions flagged as inapplicable for this route
                if direction == 'low' and route in param.skip_lo:
                    continue
                if direction == 'high' and route in param.skip_hi:
                    continue

                run_id += 1
                base_msp = base_msps[route]
                route_params_base = get(route)

                if param.category == 'economics':
                    base_val = getattr(ECONOMICS, param.field)
                    val = base_val * lo_or_hi if param.is_relative else lo_or_hi
                    perturbed_econ = dataclasses.replace(ECONOMICS, **{param.field: val})
                    msp, design, opex = _run_single_with_design(route, route_params_base, perturbed_econ, run_id)
                    base_param_val  = base_val
                    factor_display  = lo_or_hi if param.is_relative else None
                    pert_val_display = val

                elif param.category == 'route':
                    base_val = getattr(route_params_base, param.field)
                    val = base_val * lo_or_hi if param.is_relative else lo_or_hi
                    perturbed_route = dataclasses.replace(route_params_base,
                                                          **{param.field: val})
                    msp, design, opex = _run_single_with_design(route, perturbed_route, ECONOMICS, run_id)
                    base_param_val  = base_val
                    factor_display  = lo_or_hi if param.is_relative else None
                    pert_val_display = val

                elif param.category == 'global':
                    base_val = getattr(_params, param.field)
                    val = base_val * lo_or_hi if param.is_relative else lo_or_hi
                    with _patch_attrs(_global_patches(param.field, val)):
                        msp, design, opex = _run_single_with_design(route, route_params_base, ECONOMICS, run_id)
                    base_param_val  = base_val
                    factor_display  = lo_or_hi if param.is_relative else None
                    pert_val_display = val

                elif param.category == 'global_recipe_conc':
                    # No single scalar base — recipe is a dict of concentrations.
                    # Expose the factor; perturbed value is factor notation.
                    factor = lo_or_hi
                    perturbed_recipe = dataclasses.replace(
                        _params.NUTRIENTS_RECIPE,
                        concentrations={
                            k: v * factor
                            for k, v in _params.NUTRIENTS_RECIPE.concentrations.items()
                        },
                    )
                    _recipe_targets = [
                        _params, _fructose_model, _acetate_model,
                        _formate_model, _gas_ferm_model, _chemicals,
                    ]
                    patches = [(m, 'NUTRIENTS_RECIPE', perturbed_recipe)
                               for m in _recipe_targets]
                    with _patch_attrs(patches):
                        msp, design, opex = _run_single_with_design(route, route_params_base, ECONOMICS, run_id)
                    base_param_val  = None          # no single scalar for a recipe dict
                    factor_display  = factor
                    pert_val_display = f'×{factor}'

                else:
                    raise ValueError(f'Unknown SA category: {param.category!r}')

                # Correct direction label: use actual perturbation sign vs base value.
                # Handles cases where the base falls outside the nominal lo/hi range
                # (e.g. gas_ferm ε: base=0.99, hi slot=0.95 → 0.95 < base → label 'low').
                # Skip correction for recipe params (base_param_val is None there).
                if base_param_val is not None:
                    if pert_val_display < base_param_val:
                        effective_direction = 'low'
                    elif pert_val_display > base_param_val:
                        effective_direction = 'high'
                    else:
                        effective_direction = direction
                else:
                    effective_direction = direction

                swing = msp - base_msp
                swing_pct = (swing / base_msp * 100.0) if base_msp != 0.0 else float('nan')

                records.append({
                    'Route':                 route,
                    'Parameter':             param.field,
                    'Category':              param.category,
                    'Label':                 param.label,
                    'Section':               param.section,
                    'Direction':             effective_direction,
                    'Base param value':      base_param_val,   # actual base scalar (None for recipe)
                    'Perturbation factor':   factor_display,   # factor if relative, else None
                    'Perturbed value':       pert_val_display, # actual value applied
                    'Base MSP ($/kg)':       base_msp,
                    'Perturbed MSP ($/kg)':  msp,
                    'MSP swing ($/kg)':      swing,
                    'MSP swing (%)':         swing_pct,
                    **design,               # op_hours, FCI, N_reactors, N_seed_trains, Q
                    **opex,                 # Feedstock ($/kg), Feedstock ($MM/yr), ..., Capital charge ($MM/yr)
                })

                if verbose:
                    print(f'  [{route}] {param.label} {effective_direction}: '
                          f'MSP swing = {swing:+.3f} $/kg  ({swing_pct:+.1f}%)')

    # --- Export ---
    if verbose:
        print('\nExporting results...')

    excel_path = _export_sa_excel(records, routes, base_designs=base_designs,
                                  base_opex_by_route=base_opex_by_route)
    output_paths: dict[str, pathlib.Path] = {'excel': excel_path}

    for route in routes:
        png_path = _plot_tornado(records, route, base_msps[route])
        output_paths[f'tornado_{route}'] = png_path
        if verbose:
            print(f'[{route}] Tornado -> {png_path}')

    if verbose:
        print(f'Excel -> {excel_path}')

    return output_paths


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run full 4-route OAT sensitivity analysis (85 simulations)."""
    import sys
    # Windows cp1252 console can't encode Greek labels (ε etc.) — reconfigure to UTF-8
    if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    paths = run_oat_sensitivity()
    print('\nOutputs:')
    for key, path in sorted(paths.items()):
        print(f'  {key}: {path}')


if __name__ == '__main__':
    main()
