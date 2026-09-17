"""
lca_kpi.py
==========
Grouped bar chart of SCP LCA KPI results across all four production routes.
Each impact category is auto-scaled independently (per-KPI multiplicity) so
that all categories fit on a single shared y-axis.  Negative values (e.g.
Water Consumption) are plotted as-is below the zero line.

Route colours match the SCP TEA conventions (Okabe-Ito palette).
Route hatches match the cross-route TEA tornado convention (line-only patterns).

Usage:  python lca_kpi.py
Output: LCA_KPI.png (200 dpi) written to the same directory.
Requirements: pip install pandas openpyxl matplotlib numpy
"""

import numpy as np
import os

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

import pathlib
_HERE      = pathlib.Path(__file__).parent
KPI_XLSX   = str(_HERE / 'SCPLCAResults_KPIs.xlsx')
OUTPUT_DIR = str(_HERE)
DPI        = 200

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
# Line-only hatches — same as TEA cross-route tornado
ROUTE_HATCHES = {
    'Fructose':         '//',
    'Acetic Acid':      '\\\\',
    'Formic Acid':      '||',
    'Gas Fermentation': '--',
}

ROUTE_ORDER = ['Fructose', 'Acetic Acid', 'Formic Acid', 'Gas Fermentation']

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

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
df = pd.read_excel(KPI_XLSX, sheet_name='Sheet1', header=0)
df.columns = df.columns.str.strip()

n_kpi    = len(df)
n_routes = len(ROUTE_ORDER)
bar_w    = 0.18
x        = np.arange(n_kpi)
offsets  = [(j - (n_routes - 1) / 2.0) * bar_w for j in range(n_routes)]

fig, ax = plt.subplots(figsize=(18, 8))
fig.patch.set_facecolor('white')

x_labels = []

for kpi_idx, row in df.iterrows():
    route_vals = {route: float(row[route]) for route in ROUTE_ORDER}

    # Per-KPI multiplicity: scale so the largest absolute value is ~1–10
    max_val = max(abs(v) for v in route_vals.values())
    if max_val == 0:
        exp = 0
    else:
        exp = -int(np.floor(np.log10(max_val)))
    mult = 10 ** exp

    if exp == 0:
        mult_str = ''
    elif exp > 0:
        mult_str = f' ($\\times 10^{{-{exp}}}$)'
    else:
        mult_str = f' ($\\times 10^{{{abs(exp)}}}$)'

    unit_str = str(row['Units']).strip()
    x_labels.append(f"{row['Impact Category']}\n{unit_str}{mult_str}")

    for j, route in enumerate(ROUTE_ORDER):
        ax.bar(
            x[kpi_idx] + offsets[j],
            route_vals[route] * mult,
            bar_w,
            color=ROUTE_COLORS[route],
            hatch=ROUTE_HATCHES[route],
            edgecolor='black', linewidth=0.5,
            alpha=0.85, zorder=3,
        )

# --------------------------------------------------------------------------
# Axes
# --------------------------------------------------------------------------
ax.set_xticks(x)
ax.set_xticklabels(x_labels, ha='right', rotation=35,
                   linespacing=1.3, multialignment='center')
ax.tick_params(axis='x', pad=8)

ax.set_ylabel('Scaled Impact Value', fontsize=17)
ax.set_xlim(-0.6, n_kpi - 0.4)

# Zero line for KPIs with negative values (e.g. Water Consumption)
ax.axhline(0, color='#333333', linewidth=0.8, linestyle='-', zorder=2)

ax.yaxis.grid(True, color='#CCCCCC', linestyle='--', linewidth=0.5, alpha=0.7, zorder=0)
ax.set_axisbelow(True)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# --------------------------------------------------------------------------
# Legend
# --------------------------------------------------------------------------
legend_handles = [
    mpatches.Patch(
        facecolor=ROUTE_COLORS[route],
        hatch=ROUTE_HATCHES[route],
        edgecolor='#444444', linewidth=0.8,
        label=ROUTE_DISPLAY[route],
    )
    for route in ROUTE_ORDER
]
ax.legend(handles=legend_handles, fontsize=15, loc='upper center',
          bbox_to_anchor=(0.5, -0.32), ncol=4,
          frameon=True, framealpha=0.95, edgecolor='#cccccc')

# --------------------------------------------------------------------------
# Save
# --------------------------------------------------------------------------
plt.tight_layout()
plt.subplots_adjust(bottom=0.28)
fname = os.path.join(OUTPUT_DIR, 'LCA_KPI.png')
plt.savefig(fname, dpi=DPI, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved: {fname}')
