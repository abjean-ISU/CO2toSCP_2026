"""
lca_tornado.py
==============
Grouped horizontal bar tornado plot for SCP LCA sensitivity analysis.
Four routes per sensitivity variable; symlog x-axis; sorted ascending by
max |Δ GWP| across routes so the most impactful variable sits at the top.

Route colours match the SCP TEA conventions (Okabe-Ito palette).
Shade encodes perturbation direction — matching the TEA individual tornado style:
  dark shade + solid fill = low perturbation (extends left)
  light shade + '//' hatch = high perturbation (extends right)

Usage:  python lca_tornado.py
Output: LCA_tornado.png (200 dpi) written to the same directory.
Requirements: pip install pandas openpyxl matplotlib numpy
"""

import colorsys
import numpy as np
import os

import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

import pathlib
_HERE        = pathlib.Path(__file__).parent
TORNADO_XLSX = str(_HERE / 'SCPLCA_TornadoPlotResults.xlsx')
OUTPUT_DIR   = str(_HERE)
DPI          = 200

# Route colours — Okabe-Ito palette, matching SCP TEA _ROUTE_COLORS
ROUTE_COLORS = {
    'Fructose':         '#E69F00',  # orange
    'Acetic Acid':      '#56B4E9',  # sky blue
    'Formic Acid':      '#009E73',  # bluish green
    'Gas Fermentation': '#CC79A7',  # reddish purple
}
# Display names matching TEA _ROUTE_DISPLAY
ROUTE_DISPLAY = {
    'Fructose':         'Fructose',
    'Acetic Acid':      'Acetic Acid',
    'Formic Acid':      'Formic Acid',
    'Gas Fermentation': 'Gas Fermentation',
}
ROUTE_ORDER    = ['Fructose', 'Acetic Acid', 'Formic Acid', 'Gas Fermentation']

# Per-route dark/light shades — fixed HLS lightness targets, matching TEA _plot_tornado.
# Varying only L (not H or S) keeps both shades as the same recognisable colour.
# Fixed targets guarantee a wide perceptual gap for every base colour:
#   dark  = L × 0.5  (min 0.15) → low perturbation,  solid fill
#   light = L + 0.32 (max 0.84) → high perturbation, '//' hatch
def _shades(hex_color):
    r, g, b = mcolors.to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    dark  = colorsys.hls_to_rgb(h, max(l * 0.5, 0.15), s)
    light = colorsys.hls_to_rgb(h, min(l + 0.32, 0.84), s)
    return dark, light

ROUTE_DARK  = {route: _shades(ROUTE_COLORS[route])[0] for route in ROUTE_ORDER}
ROUTE_LIGHT = {route: _shades(ROUTE_COLORS[route])[1] for route in ROUTE_ORDER}
BASELINE_COLOR = '#333333'

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


def symlog(x):
    """Symmetric log transform: sign(x) * log10(|x| + 1)."""
    return np.sign(x) * np.log10(np.abs(x) + 1)


# --------------------------------------------------------------------------
# Load and prepare data
# --------------------------------------------------------------------------
df = pd.read_excel(TORNADO_XLSX, sheet_name='Sheet2', header=0)
df.columns = df.columns.str.strip()

df['delta_low']  = df['Low GWP'].astype(float)  - df['Baseline GWP'].astype(float)
df['delta_high'] = df['High GWP'].astype(float) - df['Baseline GWP'].astype(float)
# Express as % of each route's own baseline GWP
df['pct_low']    = df['delta_low']  / df['Baseline GWP'].astype(float) * 100
df['pct_high']   = df['delta_high'] / df['Baseline GWP'].astype(float) * 100
df['max_abs']    = df[['pct_low', 'pct_high']].abs().max(axis=1)

# Sort ascending by max |delta| across routes; largest ends at top (barh).
# Capital Goods is pinned to the bottom regardless of its impact magnitude.
var_max   = df.groupby('Variable')['max_abs'].max()
var_order = var_max.sort_values(ascending=True).index.tolist()
_BOTTOM_PIN = 'Capital Goods'
if _BOTTOM_PIN in var_order:
    var_order.remove(_BOTTOM_PIN)
    var_order.insert(0, _BOTTOM_PIN)

n_vars   = len(var_order)
n_routes = len(ROUTE_ORDER)
bar_h    = 0.22   # center-to-center spacing between adjacent bars in a cluster
bar_w    = 0.17   # actual bar width (narrower than spacing → small gap between bars)
y_sp     = 1.5   # vertical spacing between variable clusters
y_base   = [i * y_sp for i in range(n_vars)]
offsets  = [(j - (n_routes - 1) / 2.0) * bar_h for j in range(n_routes)]

# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, max(6, n_vars * y_sp * 0.65)))

for i, var in enumerate(var_order):
    var_df = df[df['Variable'] == var]
    for j, route in enumerate(ROUTE_ORDER):
        row = var_df[var_df['System'] == route]
        if row.empty:
            continue
        row   = row.iloc[0]
        yp = y_base[i] + offsets[j]

        d_lo = row['pct_low']
        d_hi = row['pct_high']

        if pd.notna(d_hi) and abs(d_hi) > 0.1:
            ax.barh(yp, d_hi, bar_w,
                    left=0, color=ROUTE_LIGHT[route], hatch='//',
                    edgecolor='black', linewidth=0.5, zorder=3)

        if pd.notna(d_lo) and abs(d_lo) > 0.1:
            ax.barh(yp, d_lo, bar_w,
                    left=0, color=ROUTE_DARK[route], hatch='',
                    edgecolor='black', linewidth=0.5, zorder=3)

# Baseline reference line
ax.axvline(0, color=BASELINE_COLOR, linewidth=1.5, linestyle='--', alpha=0.8, zorder=4)

# --------------------------------------------------------------------------
# Axes
# --------------------------------------------------------------------------
ax.set_yticks(y_base)
ax.set_yticklabels(var_order)

ax.xaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f'{x:+.0f}%' if x != 0 else '0')
)
ax.tick_params(axis='x', labelsize=12)

all_abs = pd.concat([df['pct_low'].dropna(), df['pct_high'].dropna()]).abs()
xmax    = all_abs.max() * 1.3
ax.set_xlim(-xmax, xmax)

ax.set_xlabel('Δ GWP (% of baseline)', fontsize=13)

ax.xaxis.grid(True, color='#CCCCCC', linestyle='--', linewidth=0.5, alpha=0.7, zorder=0)
ax.set_axisbelow(True)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# --------------------------------------------------------------------------
# Legend: route colour patches + shade/direction convention patches.
# Route patches use the base colour (most recognisable).
# Direction patches use neutral grey to show shade + hatch convention,
# matching the TEA individual tornado style.
# --------------------------------------------------------------------------
legend_handles = []
for route in ROUTE_ORDER:
    base_gwp = df.loc[df['System'] == route, 'Baseline GWP'].iloc[0]
    legend_handles.append(
        mpatches.Patch(
            facecolor=ROUTE_COLORS[route],
            edgecolor='#444444', linewidth=0.8,
            label=f"{ROUTE_DISPLAY[route]}  (baseline {base_gwp:.1f} kg CO₂-eq / kg SCP)",
        )
    )
# Hatch convention — light shade + hatch for high, dark shade for low
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
# Matplotlib fills legend columns top-to-bottom before moving to the next column.
# Reorder handles so the visual result is:
#   col 0: Fructose,  Formate,           Higher perturbation
#   col 1: Acetate,   Gas Fermentation,  Lower perturbation
# giving a 2×2 route block with the perturbation pair centred below.
lh = legend_handles  # [Fructose, Acetate, Formate, GasFerm, Higher, Lower]
legend_handles_ordered = [lh[0], lh[2], lh[4], lh[1], lh[3], lh[5]]
ax.legend(handles=legend_handles_ordered, fontsize=11, loc='upper center',
          bbox_to_anchor=(0.5, -0.18), ncol=2,
          frameon=True, framealpha=0.95, edgecolor='#cccccc')

# --------------------------------------------------------------------------
# Save
# --------------------------------------------------------------------------
plt.tight_layout()
fname = os.path.join(OUTPUT_DIR, 'LCA_tornado.png')
plt.savefig(fname, dpi=DPI, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved: {fname}')
