"""Additional analyses for the SCP TEA project.

Three post-sensitivity-analysis outputs:
  1. Cost breakdown — MSP decomposed into cost categories ($/kg SCP) per route.
  2. Cross-route tornado — grouped bar chart comparing OAT swing ranges per parameter.
  3. 2-D sensitivity — heatmaps for two dominant parameters simultaneously.

Framework §11 (additional analyses section); no existing working files are touched.

Outputs (all written to outputs/):
    cost_breakdown.png / cost_breakdown.xlsx
    cross_route_tornado.png
    2d_sa_gas_fermentation.png
    2d_sa_fructose.png / 2d_sa_acetate.png / 2d_sa_formate.png
    2d_sa_results.xlsx

Usage:
    python additional_analyses.py                # full run (89 simulations)
    from additional_analyses import run_cost_breakdown, ...
"""

from __future__ import annotations

import contextlib
import dataclasses
import pathlib
import warnings

import colorsys

import matplotlib
matplotlib.use('Agg')   # non-GUI backend
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import biosteam as bst
import numpy as np
import pandas as pd

import common.parameters as _params
from common.parameters import ECONOMICS, get
from common.economics import build_tea
from common.operating_hours import effective_operating_hours
# Re-use patching infrastructure from sensitivity_analysis — no duplication (Framework §11)
from sensitivity_analysis import (
    _patch_attrs, _BUILDERS, _ALL_ROUTES, _run_single,
    _COST_CATEGORIES_ORDER, _identify_stream_category, _ROUTE_COLORS,
)

_OUTPUTS_DIR  = pathlib.Path(__file__).parent / 'outputs'
_LIQUID_ROUTES = ['fructose', 'acetate', 'formate']

# Colorblind-friendly route styling — Okabe-Ito palette (2008 Nature Methods)
# Color + hatch + linestyle + marker: distinguishable under all CB conditions.
# _ROUTE_COLORS imported from sensitivity_analysis (canonical copy lives there).
_ROUTE_HATCHES = {
    'fructose':         '/',
    'acetate':          '\\',
    'formate':          'x',
    'gas_fermentation': 'o',
}
_ROUTE_LINE_STYLES = {
    'fructose':         '-',
    'acetate':          '--',
    'formate':          '-.',
    'gas_fermentation': ':',
}
_ROUTE_MARKERS = {
    'fructose':         'o',
    'acetate':          's',
    'formate':          '^',
    'gas_fermentation': 'D',
}
_ROUTE_DISPLAY = {
    'fructose':         'Fructose',
    'acetate':          'Acetic Acid',
    'formate':          'Formic Acid',
    'gas_fermentation': 'Gas Fermentation',
}


def _route_shades(hex_color: str) -> tuple:
    """Return (dark_rgb, light_rgb) for a base hex colour.

    Varies only HLS lightness — matching lca_tornado._shades convention:
      dark  = L × 0.5  (min 0.15) → low perturbation,  solid fill
      light = L + 0.32 (max 0.84) → high perturbation, '//' hatch
    Used by the cross-route tornado and the legend direction patches.
    """
    r, g, b = mcolors.to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # noqa: E741
    dark  = colorsys.hls_to_rgb(h, max(l * 0.5, 0.15), s)
    light = colorsys.hls_to_rgb(h, min(l + 0.32, 0.84), s)
    return dark, light


# Pre-computed dark/light shades for each route — matching lca_tornado.ROUTE_DARK/LIGHT.
_ROUTE_SHADE_DARK  = {r: _route_shades(c)[0] for r, c in _ROUTE_COLORS.items()}
_ROUTE_SHADE_LIGHT = {r: _route_shades(c)[1] for r, c in _ROUTE_COLORS.items()}


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

def _run_single_full(route: str, params, economics, run_id: int):
    """Build + simulate + TEA + solve_price; return (system, tea, msp).

    Like _run_single from sensitivity_analysis but returns the full objects for
    cost extraction.  Used only by run_cost_breakdown; all other analyses
    reuse the imported _run_single.  Framework §11.
    """
    with bst.Flowsheet(f'_aa_{route}_{run_id}'):
        system, _ = _BUILDERS[route](params, economics)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            system.simulate()
        tea = build_tea(system, economics)
        product = max(
            (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
            key=lambda s: s.imass['CNecatorBiomass'],
        )
        msp = tea.solve_price(product)
        return system, tea, msp


# ---------------------------------------------------------------------------
# Analysis 1 — cost breakdown
# ---------------------------------------------------------------------------

# _COST_CATEGORIES_ORDER and _identify_stream_category are imported from
# sensitivity_analysis (single implementation — Framework §11 / CLAUDE.md §shared-module)

# Cost-breakdown category hatches — retained for accessibility / print readability.
# Colors are no longer stored per-category; instead each route bar uses monochromatic
# shades of its route colour (light → dark across categories), computed below.
# Framework §11 (monochromatic cost-breakdown convention).
_CATEGORY_HATCHES = {
    'Feedstock':        '/',        # sparse forward diagonal
    'Ammonia':          '//',       # dense forward diagonal
    'Nutrients':        '\\',       # sparse backward diagonal
    'Electricity':      '\\\\',     # dense backward diagonal
    'Other utilities':  'x',        # diagonal cross
    'Waste disposal':   '+',        # straight cross
    'Labor':            '||',       # dense vertical
    'Maintenance':      '--',       # dense horizontal
    'Other FOC':        'o',        # circles
    'Capital charge':   '.',        # dots
}


def _make_shade_colors(
    base_hex: str, n: int,
) -> list[tuple[float, float, float]]:
    """Return *n* RGB tuples that vary only the HLS lightness of *base_hex*.

    Index 0 is the lightest shade (L = 0.88); index n − 1 is the darkest
    (L = 0.28).  Hue and saturation are held constant so the sequence reads
    as one coherent colour family.  Framework §11 (monochromatic cost-breakdown
    convention).
    """
    r, g, b = mcolors.to_rgb(base_hex)
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # noqa: E741  (l shadows built-in)
    l_hi, l_lo = 0.88, 0.28
    return [
        colorsys.hls_to_rgb(h, l_hi - i * (l_hi - l_lo) / max(n - 1, 1), s)
        for i in range(n)
    ]


def run_cost_breakdown(
    routes: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, pathlib.Path]:
    """Decompose MSP into cost categories ($/kg SCP) for each route.

    Decomposition sums exactly to MSP: feedstock + ammonia + nutrients +
    electricity + other utilities + waste disposal + labor + maintenance +
    other FOC + capital charge (residual).  Framework §11.

    Returns
    -------
    dict
        Keys: 'cost_breakdown_png', 'cost_breakdown_xlsx'.
        Values: pathlib.Path objects.
    """
    if routes is None:
        routes = _ALL_ROUTES

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    op_hours = effective_operating_hours()  # h/yr
    all_records: list[dict] = []
    breakdown_by_route: dict[str, dict[str, float]] = {}
    msp_by_route: dict[str, float] = {}

    run_id = 0
    for route in routes:
        if verbose:
            print(f'[cost_breakdown] {route}...')
        run_id += 1
        system, tea, msp = _run_single_full(route, get(route), ECONOMICS, run_id)
        msp_by_route[route] = msp

        # Product stream for production rate
        product = max(
            (s for s in system.products if s.imass['CNecatorBiomass'] > 0.0),
            key=lambda s: s.imass['CNecatorBiomass'],
        )
        prod_kg_yr = product.F_mass * op_hours   # kg/yr (F_mass is kg/h at steady state)

        cats: dict[str, float] = {c: 0.0 for c in _COST_CATEGORIES_ORDER}

        # Feed streams
        for stream in system.feeds:
            cat = _identify_stream_category(stream)
            if cat is None:
                continue
            cost_per_yr = stream.cost * op_hours  # $/yr
            if cat in cats:
                cats[cat] += cost_per_yr
            else:
                # Unlabeled feeds go to feedstock by default
                cats['Feedstock'] += cost_per_yr

        # Electricity
        cats['Electricity'] = system.power_utility.cost * op_hours   # $/yr

        # Other utilities — heat agents (steam, cooling water) grouped
        heat_cost_yr = 0.0
        for hu in system.heat_utilities:
            if hu.cost > 0.0:
                heat_cost_yr += hu.cost * op_hours
        cats['Other utilities'] = heat_cost_yr

        # Waste disposal — negative-priced product streams (WWT sludge has positive cost
        # to the process if wwt_organic_removal_cost > 0; it's a disposal cost)
        # The WWT sludge stream (negative-value product) is identified by negative stream.cost
        waste_cost_yr = 0.0
        for stream in system.products:
            if stream.cost < 0.0:
                # Negative product cost = disposal cost to the plant
                waste_cost_yr += abs(stream.cost) * op_hours
        cats['Waste disposal'] = waste_cost_yr

        # Fixed operating costs (labour, maintenance, other FOC)
        # tea.labor_cost is already $/yr
        cats['Labor']       = tea.labor_cost
        cats['Maintenance'] = tea.maintenance * tea.FCI
        cats['Other FOC']   = (tea.property_tax + tea.property_insurance
                               + tea.administration) * tea.FCI

        # Capital charge — residual so that sum = MSP exactly
        msp_per_yr = msp * prod_kg_yr
        all_other_yr = sum(cats[c] for c in _COST_CATEGORIES_ORDER if c != 'Capital charge')
        cats['Capital charge'] = msp_per_yr - all_other_yr

        breakdown_by_route[route] = cats

        # Build records for Excel
        for cat, cost_yr in cats.items():
            all_records.append({
                'Route':    route,
                'Category': cat,
                '$/yr':     cost_yr,
                '$/kg SCP': cost_yr / prod_kg_yr if prod_kg_yr > 0.0 else float('nan'),
                '% of MSP': (cost_yr / msp_per_yr * 100.0) if msp_per_yr > 0.0 else float('nan'),
            })

        if verbose:
            print(f'  MSP = ${msp:.2f}/kg,  prod = {prod_kg_yr/1e6:.2f} kt/yr')

    # --- Chart ---
    # Each route bar uses monochromatic shades of its route colour: lightest shade
    # for the first category (Feedstock) through to darkest for the last (Capital
    # charge).  _CATEGORY_HATCHES add a second encoding layer for accessibility
    # and print readability — Framework §11 (monochromatic cost-breakdown convention).
    n_cats = len(_COST_CATEGORIES_ORDER)
    # Pre-compute shade palettes so each category index maps to a fixed lightness level.
    route_shades: dict[str, list[tuple]] = {
        route: _make_shade_colors(_ROUTE_COLORS[route], n_cats)
        for route in routes
    }

    plt.rcParams.update({
        'font.family':      'sans-serif',
        'font.size':        17,
        'axes.titlesize':   18,
        'axes.labelsize':   17,
        'xtick.labelsize':  15,
        'ytick.labelsize':  16,
        'figure.facecolor': 'white',
        'axes.facecolor':   'white',
        'hatch.linewidth':  1.5,
    })

    fig, (ax, ax_pct) = plt.subplots(1, 2, figsize=(18, 7), facecolor='white')
    x = list(range(len(routes)))
    bar_width = 0.5
    bottoms_abs = [0.0] * len(routes)
    bottoms_pct = [0.0] * len(routes)

    for cat_idx, cat in enumerate(_COST_CATEGORIES_ORDER):
        vals_abs = [
            next(
                (r['$/kg SCP'] for r in all_records
                 if r['Route'] == route and r['Category'] == cat),
                0.0,
            )
            for route in routes
        ]
        vals_pct = [
            next(
                (r['% of MSP'] for r in all_records
                 if r['Route'] == route and r['Category'] == cat),
                0.0,
            )
            for route in routes
        ]
        hatch = _CATEGORY_HATCHES[cat]
        for j, (xi, val_abs, val_pct, route) in enumerate(zip(x, vals_abs, vals_pct, routes)):
            shade = route_shades[route][cat_idx]
            ax.bar(xi, val_abs, bar_width, bottom=bottoms_abs[j],
                   color=shade, hatch=hatch, edgecolor='black', linewidth=0.4)
            ax_pct.bar(xi, val_pct, bar_width, bottom=bottoms_pct[j],
                       color=shade, hatch=hatch, edgecolor='black', linewidth=0.4)
        bottoms_abs = [b + v for b, v in zip(bottoms_abs, vals_abs)]
        bottoms_pct = [b + v for b, v in zip(bottoms_pct, vals_pct)]

    # MSP label at the top of each absolute bar
    abs_max = max(bottoms_abs) if bottoms_abs else 1.0
    for xi, top, route in zip(x, bottoms_abs, routes):
        msp_val = msp_by_route[route]
        ax.text(xi, top + 0.02 * abs_max,
                f'${msp_val:.2f}/kg',
                ha='center', va='bottom', fontsize=14, fontweight='bold')

    # Legend: neutral grey-scale patches (light → dark) so the shade-to-category
    # mapping is clear independent of any specific route colour.
    grey_shades = _make_shade_colors('#808080', n_cats)
    legend_handles = [
        mpatches.Patch(
            facecolor=grey_shades[i],
            hatch=_CATEGORY_HATCHES[cat],
            edgecolor='black', linewidth=0.4,
            label=cat,
        )
        for i, cat in enumerate(_COST_CATEGORIES_ORDER)
    ]

    # Configure absolute cost axis
    ax.set_facecolor('white')
    ax.set_xticks(x)
    ax.set_xticklabels([_ROUTE_DISPLAY.get(r, r) for r in routes], rotation=15, ha='right', fontsize=15)
    ax.set_ylabel('$/kg SCP', fontsize=17)
    ax.set_title('Minimum Selling Price', fontsize=18)
    ax.set_ylim(0, abs_max * 1.12)   # headroom for MSP labels
    # Panel label outside the plot area, above the top-left corner
    ax.text(-0.07, 1.02, 'a)', transform=ax.transAxes,
            fontsize=17, fontweight='bold', va='bottom', ha='right')

    # Configure percentage axis
    ax_pct.set_facecolor('white')
    ax_pct.set_xticks(x)
    ax_pct.set_xticklabels([_ROUTE_DISPLAY.get(r, r) for r in routes], rotation=15, ha='right', fontsize=15)
    ax_pct.set_ylabel('% of MSP', fontsize=17)
    ax_pct.set_title('Cost Contribution (%)', fontsize=18)
    ax_pct.set_ylim(0, 100)
    ax_pct.text(-0.07, 1.02, 'b)', transform=ax_pct.transAxes,
                fontsize=17, fontweight='bold', va='bottom', ha='right')

    # Shared legend at the bottom, centred below both panels
    n_cols = min(n_cats, 5)   # wrap into rows of 5 so the legend stays compact
    fig.legend(handles=legend_handles, loc='upper center',
               bbox_to_anchor=(0.5, 0.0), ncol=n_cols, borderaxespad=0,
               handlelength=2.5, handleheight=1.8, fontsize=14)
    fig.tight_layout()
    png_path = _OUTPUTS_DIR / 'cost_breakdown.png'
    fig.savefig(png_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    # --- Excel ---
    xlsx_path = _OUTPUTS_DIR / 'cost_breakdown.xlsx'
    df = pd.DataFrame(all_records,
                      columns=['Route', 'Category', '$/yr', '$/kg SCP', '% of MSP'])
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Cost Breakdown', index=False)

    if verbose:
        print(f'  -> {png_path}')
        print(f'  -> {xlsx_path}')

    return {
        'cost_breakdown_png':  png_path,
        'cost_breakdown_xlsx': xlsx_path,
    }


# ---------------------------------------------------------------------------
# Analysis 2 — cross-route tornado
# ---------------------------------------------------------------------------

def plot_cross_route_tornado(
    excel_path: pathlib.Path | str | None = None,
    verbose: bool = True,
) -> dict[str, pathlib.Path]:
    """Single figure comparing all four routes' signed MSP swings per parameter.

    Reads the existing sensitivity_results.xlsx — no new simulations.
    Matches the LCA tornado style (lca_tornado.py):
      - Symmetric-log x-axis centred on 0 (Δ MSP = 0)
      - Dark shade + solid fill  = low perturbation  (left)
      - Light shade + '//' hatch = high perturbation (right)
      - Parameters sorted ascending by max |swing|; most impactful at top.
      - Legend includes base-case MSP per route + shade/direction patches.
    Framework §11.

    Parameters
    ----------
    excel_path : pathlib.Path | str | None
        Path to sensitivity_results.xlsx.  Defaults to outputs/sensitivity_results.xlsx.

    Returns
    -------
    dict
        Key: 'cross_route_tornado_png'.
    """
    if excel_path is None:
        excel_path = _OUTPUTS_DIR / 'sensitivity_results.xlsx'
    excel_path = pathlib.Path(excel_path)

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = pd.read_excel(excel_path, sheet_name='Tornado Summary')
    bc = pd.read_excel(excel_path, sheet_name='Base Case Design')

    # Signed swing columns written by _export_sa_excel: '{route}_lo' and '{route}_hi'
    lo_cols = [c for c in ts.columns if c.endswith('_lo')]
    hi_cols = [c for c in ts.columns if c.endswith('_hi')]
    routes_in_sheet = [c[:-3] for c in lo_cols]  # strip '_lo'

    # NaN swings (gas_fermentation ε lo was skipped) → 0
    ts[lo_cols + hi_cols] = ts[lo_cols + hi_cols].fillna(0.0)

    # Convert absolute swings to % of each route's base MSP
    for route in routes_in_sheet:
        bc_row = bc[bc['Route'] == route]
        base_msp = float(bc_row['Base MSP ($/kg)'].iloc[0]) if not bc_row.empty else 1.0
        ts[f'{route}_lo_pct'] = ts[f'{route}_lo'] / base_msp * 100
        ts[f'{route}_hi_pct'] = ts[f'{route}_hi'] / base_msp * 100

    lo_pct_cols = [f'{route}_lo_pct' for route in routes_in_sheet]
    hi_pct_cols = [f'{route}_hi_pct' for route in routes_in_sheet]

    # Sort ascending by max |% swing| across all routes and directions; most impactful at top (barh)
    all_swing_cols = lo_pct_cols + hi_pct_cols
    ts['_sort_key'] = ts[all_swing_cols].abs().max(axis=1)
    ts = ts.sort_values('_sort_key', ascending=True).drop(columns=['_sort_key']).reset_index(drop=True)

    labels = ts['Label'].tolist()
    n_params = len(labels)
    n_routes = len(routes_in_sheet)

    # Layout — matching lca_tornado spacing
    bar_h   = 0.22   # center-to-center spacing between adjacent bars in a cluster
    bar_w   = 0.17   # actual bar width (narrower than spacing → small gap between bars)
    y_sp    = 1.5
    y_base  = [i * y_sp for i in range(n_params)]
    offsets = [(j - (n_routes - 1) / 2.0) * bar_h for j in range(n_routes)]

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

    fig, ax = plt.subplots(figsize=(12, max(6, n_params * y_sp * 0.65)))

    for i, route in enumerate(routes_in_sheet):
        lo_col = f'{route}_lo_pct'
        hi_col = f'{route}_hi_pct'
        dark_color  = _ROUTE_SHADE_DARK.get(route,  (0.5, 0.5, 0.5))
        light_color = _ROUTE_SHADE_LIGHT.get(route, (0.8, 0.8, 0.8))
        for yb, lo_val, hi_val in zip(y_base, ts[lo_col].tolist(), ts[hi_col].tolist()):
            yp = yb + offsets[i]
            # High perturbation — light shade + '//' hatch; matching individual tornado style
            if abs(hi_val) > 1e-6:
                ax.barh(yp, hi_val, bar_w,
                        left=0, color=light_color, hatch='//',
                        edgecolor='black', linewidth=0.5, zorder=3)
            # Low perturbation — dark shade + solid fill; matching individual tornado style
            if abs(lo_val) > 1e-6:
                ax.barh(yp, lo_val, bar_w,
                        left=0, color=dark_color, hatch='',
                        edgecolor='black', linewidth=0.5, zorder=3)

    # Baseline reference line at Δ MSP = 0
    ax.axvline(0, color='#333333', linewidth=1.5, linestyle='--', alpha=0.8, zorder=4)

    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda x, _: f'{x:+.0f}%' if x != 0 else '0'
    ))
    ax.set_yticks(y_base)
    ax.set_yticklabels(labels)
    ax.set_xlabel('Δ MSP (% of base case)', fontsize=13)

    ax.xaxis.grid(True, color='#CCCCCC', linestyle='--', linewidth=0.5, alpha=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Legend — route patches (base colour + base MSP) + hatch/direction convention patches
    # Reverse order so legend top→bottom matches bar stacking top→bottom (gas ferm on top).
    legend_handles = []
    for route in reversed(routes_in_sheet):
        bc_row = bc[bc['Route'] == route]
        if not bc_row.empty and 'Base MSP ($/kg)' in bc_row.columns:
            base_msp = float(bc_row['Base MSP ($/kg)'].iloc[0])
            lbl = f"{_ROUTE_DISPLAY.get(route, route)}  (base ${base_msp:.2f}/kg SCP)"
        else:
            lbl = _ROUTE_DISPLAY.get(route, route)
        legend_handles.append(
            mpatches.Patch(
                facecolor=_ROUTE_COLORS.get(route, '#888888'),
                edgecolor='#444444', linewidth=0.8,
                label=lbl,
            )
        )
    # Hatch/direction convention — light shade + hatch for high, dark shade for low
    legend_handles.append(
        mpatches.Patch(facecolor='#bbbbbb', hatch='//',
                       edgecolor='#444444', linewidth=0.8,
                       label='Higher perturbation')
    )
    legend_handles.append(
        mpatches.Patch(facecolor='#555555', hatch='',
                       edgecolor='#444444', linewidth=0.8,
                       label='Lower perturbation')
    )
    ax.legend(handles=legend_handles, fontsize=14, loc='lower right',
              frameon=True, framealpha=0.95, edgecolor='#cccccc')

    plt.tight_layout()
    png_path = _OUTPUTS_DIR / 'cross_route_tornado.png'
    fig.savefig(png_path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    if verbose:
        print(f'[cross_route_tornado] -> {png_path}')

    return {'cross_route_tornado_png': png_path}


# ---------------------------------------------------------------------------
# Analysis 3 — 2D sensitivity
# ---------------------------------------------------------------------------

# Gas fermentation grid: electricity_price × contingency_fee_factor — Framework §11
_GAS_ELEC_GRID = [0.018, 0.030, 0.045, 0.065, 0.087]        # $/kWh (§9.4 SA range)
_GAS_CONT_GRID = [0.767, 0.964, 1.180, 1.389, 1.591]         # 1.18 × [0.65,0.817,1.0,1.177,1.35]

# Liquid-route grid: feedstock_price factor × epsilon — Framework §11
_LIQ_FP_FACTORS = [0.50, 0.75, 1.00, 1.25, 1.50]            # multipliers on base feedstock_price
_LIQ_EPS_VALS   = [0.80, 0.85, 0.90, 0.95]                   # absolute epsilon values


def _route_cmap(route: str) -> mcolors.LinearSegmentedColormap:
    """Build a single-hue LinearSegmentedColormap for *route*.

    Runs from a very light shade (L = 0.92, low MSP end) to a very dark shade
    (L = 0.20, high MSP end), varying only HLS lightness.  Consistent with the
    monochromatic shading convention used for the cost breakdown and individual
    tornado plots.  Framework §11.
    """
    base_hex = _ROUTE_COLORS.get(route, '#888888')
    r, g, b = mcolors.to_rgb(base_hex)
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # noqa: E741
    light = colorsys.hls_to_rgb(h, 0.92, s)
    dark  = colorsys.hls_to_rgb(h, 0.20, s)
    return mcolors.LinearSegmentedColormap.from_list(f'route_{route}', [light, dark])


def _annotate_heatmap(ax, data: list[list[float]], x_ticks, y_ticks,
                      base_xi: int, base_yi: int, fontsize: int = 11) -> None:
    """Annotate each heatmap cell with MSP value and highlight the base-case cell."""
    vmax = max(max(r) for r in data)
    for yi, row in enumerate(data):
        for xi, val in enumerate(row):
            ax.text(xi + 0.5, yi + 0.5, f'{val:.1f}',
                    ha='center', va='center', fontsize=fontsize,
                    color='white' if val > vmax * 0.7 else 'black')
    rect = plt.Rectangle((base_xi, base_yi), 1, 1,
                          linewidth=2.5, edgecolor='black', facecolor='none')
    ax.add_patch(rect)


def _draw_heatmap_on_ax(ax, fig, data: list[list[float]], x_vals, y_vals,
                        xlabel: str, ylabel: str,
                        base_xi: int, base_yi: int,
                        cmap: str | mcolors.Colormap = 'viridis_r',
                        title: str = '', label: str = '',
                        fontsize: int = 12, annot_fontsize: int = 11) -> None:
    """Draw a pcolormesh heatmap onto an existing axes *ax*."""
    arr = [[row[xi] for xi in range(len(x_vals))] for row in data]
    mesh = ax.pcolormesh(
        range(len(x_vals) + 1),
        range(len(y_vals) + 1),
        arr,
        cmap=cmap,
    )
    cb = fig.colorbar(mesh, ax=ax)
    cb.set_label('MSP ($/kg SCP)', fontsize=fontsize)
    cb.ax.tick_params(labelsize=fontsize - 1)
    ax.set_xticks([xi + 0.5 for xi in range(len(x_vals))])
    ax.set_xticklabels([f'{v:.3g}' for v in x_vals], rotation=30, ha='right',
                       fontsize=fontsize - 1)
    ax.set_yticks([yi + 0.5 for yi in range(len(y_vals))])
    ax.set_yticklabels([f'{v:.3g}' for v in y_vals], fontsize=fontsize - 1)
    ax.set_xlabel(xlabel, fontsize=fontsize)
    ax.set_ylabel(ylabel, fontsize=fontsize)
    if title:
        ax.set_title(title, fontsize=fontsize + 1)
    if label:
        ax.text(-0.07, 1.02, label, transform=ax.transAxes,
                fontsize=fontsize + 2, fontweight='bold', va='bottom', ha='right')
    _annotate_heatmap(ax, arr, x_vals, y_vals, base_xi, base_yi, fontsize=annot_fontsize)


def _save_heatmap(data: list[list[float]], x_vals, y_vals,
                  xlabel: str, ylabel: str,
                  base_xi: int, base_yi: int,
                  out_path: pathlib.Path,
                  cmap: str | mcolors.Colormap = 'viridis_r') -> None:
    """Render and save one pcolormesh heatmap as a standalone figure."""
    plt.rcParams.update({
        'font.family':      'sans-serif',
        'font.size':        14,
        'axes.titlesize':   15,
        'axes.labelsize':   14,
        'xtick.labelsize':  12,
        'ytick.labelsize':  13,
        'figure.facecolor': 'white',
        'axes.facecolor':   'white',
    })
    fig, ax = plt.subplots(figsize=(8, 6))
    _draw_heatmap_on_ax(ax, fig, data, x_vals, y_vals, xlabel, ylabel,
                        base_xi, base_yi, cmap=cmap, fontsize=13, annot_fontsize=11)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def run_2d_sensitivity(
    gas_routes: list[str] | None = None,
    liquid_routes: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, pathlib.Path]:
    """Heatmaps showing MSP across two dominant parameters simultaneously.

    Gas fermentation: electricity_price × contingency_fee_factor (25 runs).
    Liquid routes (fructose/acetate/formate): feedstock_price × epsilon (20 runs each).
    Total simulations: 25 + 60 = 85.  Framework §11.

    Parameters
    ----------
    gas_routes : list[str] | None
        Gas routes to run.  Defaults to ['gas_fermentation'].
    liquid_routes : list[str] | None
        Liquid routes to run.  Defaults to ['fructose', 'acetate', 'formate'].

    Returns
    -------
    dict
        Keys: '2d_sa_{route}_png' for each route, '2d_sa_xlsx'.
    """
    if gas_routes is None:
        gas_routes = ['gas_fermentation']
    if liquid_routes is None:
        liquid_routes = _LIQUID_ROUTES

    _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    output_paths: dict[str, pathlib.Path] = {}
    xlsx_sheets: dict[str, pd.DataFrame] = {}
    # Collect specs for combined 2×2 figure (built after all individual plots).
    _panel_specs: list[dict] = []
    run_id = 0

    # --- Gas fermentation: electricity_price × contingency_fee_factor ---
    for route in gas_routes:
        if verbose:
            print(f'[2d_sa] {route}: electricity_price × contingency_fee_factor '
                  f'({len(_GAS_ELEC_GRID)} × {len(_GAS_CONT_GRID)} = '
                  f'{len(_GAS_ELEC_GRID)*len(_GAS_CONT_GRID)} runs)')

        base_ep = ECONOMICS.electricity_price         # 0.032 $/kWh
        base_cf = ECONOMICS.contingency_fee_factor    # 1.18

        # One base-case full run to get TCI_base.
        # TCI scales exactly linearly with contingency_fee_factor (TCI = cf ×
        # installed_equipment_cost × (1 + WC_over_FCI)); installed equipment cost
        # is determined by process physics, independent of cf and electricity_price.
        # So TCI_i = TCI_base × (cf_i / base_cf).
        run_id += 1
        if verbose:
            print(f'  base run for TCI (run {run_id})...')
        _, base_tea, _ = _run_single_full(route, get(route), ECONOMICS, run_id)
        base_tci = base_tea.TCI  # $
        tci_grid_mm = [cf / base_cf * base_tci / 1e6 for cf in _GAS_CONT_GRID]  # $MM

        # grid[yi][xi] = MSP at (cont_grid[yi], elec_grid[xi])
        grid: list[list[float]] = []
        for cf in _GAS_CONT_GRID:
            row = []
            for ep in _GAS_ELEC_GRID:
                run_id += 1
                perturbed_econ = dataclasses.replace(
                    ECONOMICS, electricity_price=ep, contingency_fee_factor=cf,
                )
                msp = _run_single(route, get(route), perturbed_econ, run_id)
                row.append(msp)
                if verbose:
                    print(f'  ep={ep:.3f}, cf={cf:.3f} -> MSP=${msp:.2f}/kg')
            grid.append(row)

        # Base-case indices
        base_xi = min(range(len(_GAS_ELEC_GRID)),
                      key=lambda i: abs(_GAS_ELEC_GRID[i] - base_ep))
        base_yi = min(range(len(tci_grid_mm)),
                      key=lambda i: abs(tci_grid_mm[i] - base_tci / 1e6))

        png_path = _OUTPUTS_DIR / f'2d_sa_{route}.png'
        _save_heatmap(
            grid, _GAS_ELEC_GRID, tci_grid_mm,
            xlabel='Electricity price ($/kWh)',
            ylabel='TCI ($MM)',
            base_xi=base_xi, base_yi=base_yi,
            out_path=png_path,
            cmap=_route_cmap(route),
        )
        output_paths[f'2d_sa_{route}_png'] = png_path
        if verbose:
            print(f'  -> {png_path}')

        _panel_specs.append(dict(
            grid=grid, x_vals=_GAS_ELEC_GRID, y_vals=tci_grid_mm,
            xlabel='Electricity price ($/kWh)', ylabel='TCI ($MM)',
            base_xi=base_xi, base_yi=base_yi,
            cmap=_route_cmap(route),
            title=_ROUTE_DISPLAY.get(route, route),
        ))

        # Excel sheet: rows = TCI ($MM), cols = elec_price
        df = pd.DataFrame(
            grid,
            index=[f'TCI={t:.0f}MM' for t in tci_grid_mm],
            columns=[f'ep={ep:.3g}' for ep in _GAS_ELEC_GRID],
        )
        xlsx_sheets[route] = df

    # --- Liquid routes: feedstock_price × epsilon ---
    for route in liquid_routes:
        base_params = get(route)
        base_fp = base_params.feedstock_price
        base_ep = base_params.epsilon

        if verbose:
            print(f'[2d_sa] {route}: feedstock_price × epsilon '
                  f'({len(_LIQ_FP_FACTORS)} × {len(_LIQ_EPS_VALS)} = '
                  f'{len(_LIQ_FP_FACTORS)*len(_LIQ_EPS_VALS)} runs)')

        # grid[yi][xi] = MSP at (eps_vals[yi], fp_factors[xi])
        grid = []
        for ev in _LIQ_EPS_VALS:
            row = []
            for ff in _LIQ_FP_FACTORS:
                run_id += 1
                perturbed_route = dataclasses.replace(
                    base_params,
                    feedstock_price=base_fp * ff,
                    epsilon=ev,
                )
                msp = _run_single(route, perturbed_route, ECONOMICS, run_id)
                row.append(msp)
                if verbose:
                    print(f'  fp_factor={ff:.2f}, eps={ev:.2f} -> MSP=${msp:.2f}/kg')
            grid.append(row)

        fp_actual = [base_fp * ff for ff in _LIQ_FP_FACTORS]  # actual $/kg for each grid point

        # Base-case indices: fp_actual closest to base_fp, eps closest to base_ep
        base_xi = min(range(len(fp_actual)),
                      key=lambda i: abs(fp_actual[i] - base_fp))
        base_yi = min(range(len(_LIQ_EPS_VALS)),
                      key=lambda i: abs(_LIQ_EPS_VALS[i] - base_ep))

        png_path = _OUTPUTS_DIR / f'2d_sa_{route}.png'
        _save_heatmap(
            grid, fp_actual, _LIQ_EPS_VALS,
            xlabel='Feedstock price ($/kg)',
            ylabel='Substrate conversion (ε)',
            base_xi=base_xi, base_yi=base_yi,
            out_path=png_path,
            cmap=_route_cmap(route),
        )
        output_paths[f'2d_sa_{route}_png'] = png_path
        if verbose:
            print(f'  -> {png_path}')

        _panel_specs.append(dict(
            grid=grid, x_vals=fp_actual, y_vals=_LIQ_EPS_VALS,
            xlabel='Feedstock price ($/kg)', ylabel='Substrate conversion (ε)',
            base_xi=base_xi, base_yi=base_yi,
            cmap=_route_cmap(route),
            title=_ROUTE_DISPLAY.get(route, route),
        ))

        # Excel sheet: rows = epsilon, cols = feedstock_price factor
        df = pd.DataFrame(
            grid,
            index=[f'eps={ev:.2f}' for ev in _LIQ_EPS_VALS],
            columns=[f'fp_factor={ff:.2f}' for ff in _LIQ_FP_FACTORS],
        )
        xlsx_sheets[route] = df

    # --- Excel: one sheet per route ---
    xlsx_path = _OUTPUTS_DIR / '2d_sa_results.xlsx'
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        for sheet_name, df in xlsx_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name)
    output_paths['2d_sa_xlsx'] = xlsx_path
    if verbose:
        print(f'  -> {xlsx_path}')

    # --- Combined 2×2 figure (all four panels, labelled a–d) ---
    if len(_panel_specs) == 4:
        plt.rcParams.update({
            'font.family':      'sans-serif',
            'font.size':        18,
            'axes.titlesize':   20,
            'axes.labelsize':   18,
            'xtick.labelsize':  16,
            'ytick.labelsize':  17,
            'figure.facecolor': 'white',
            'axes.facecolor':   'white',
        })
        fig2, axes = plt.subplots(2, 2, figsize=(22, 16))
        panel_labels = ['a)', 'b)', 'c)', 'd)']
        ordered = _panel_specs[1:] + [_panel_specs[0]]  # fructose, acetate, formate, gas ferm
        for ax, spec, lbl in zip(axes.flat, ordered, panel_labels):
            _draw_heatmap_on_ax(
                ax, fig2,
                spec['grid'], spec['x_vals'], spec['y_vals'],
                spec['xlabel'], spec['ylabel'],
                spec['base_xi'], spec['base_yi'],
                cmap=spec['cmap'],
                title=spec['title'],
                label=lbl,
                fontsize=18, annot_fontsize=16,
            )
        fig2.tight_layout()
        combined_path = _OUTPUTS_DIR / '2d_sa_combined.png'
        fig2.savefig(combined_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig2)
        output_paths['2d_sa_combined_png'] = combined_path
        if verbose:
            print(f'  -> {combined_path}')

    return output_paths


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all three additional analyses.

    Full simulation count:
        cost_breakdown:      4 (one base run per route)
        cross_route_tornado: 0 (reads existing sensitivity_results.xlsx)
        2d_sa:              85 (25 gas + 20×3 liquid)
        Total: 89 simulations.
    """
    import sys
    # Windows cp1252 console can't encode Greek letters — reconfigure to UTF-8
    if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    paths: dict[str, pathlib.Path] = {}
    paths.update(run_cost_breakdown())
    paths.update(plot_cross_route_tornado())
    paths.update(run_2d_sensitivity())

    print('\nOutputs:')
    for key, path in sorted(paths.items()):
        print(f'  {key}: {path}')


if __name__ == '__main__':
    main()
