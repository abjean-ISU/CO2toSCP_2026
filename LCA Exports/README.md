# lca/ — LCA Inventory Assessment Workbooks

This directory contains four automatically-generated Excel workbooks, one per SCP production route, providing the foreground life cycle inventory (LCI) for import into openLCA (Framework §8).

## Files

| File | Route |
|------|-------|
| `Fructose_InventoryAssessment.xlsx` | Fructose (heterotrophic) |
| `Acetate_InventoryAssessment.xlsx` | Acetate (heterotrophic) |
| `Formate_InventoryAssessment.xlsx` | Formate (heterotrophic) |
| `GasFerment_InventoryAssessment.xlsx` | Gas fermentation (lithoautotrophic H₂/CO₂) |
| `stream_balance_check.py` | Standalone sanity-check script — see [Stream balance check](#stream-balance-check) below |

These files are **regenerated automatically** on every `run_models.py` run, after `system.simulate()` for each route. They are self-contained (no external links) — all values are computed directly from BioSTEAM stream and unit objects at runtime.

Source modules: `common/lca_config.py` (what to compute and how to allocate) and `common/lca_export.py` (accessor interpreter and Excel writer).

---

## Workbook structure

Each workbook has two sheets.

### Sheet 1: Capital Goods

Six rows, one per NAICS category. Five columns:

| Col | Header | Content |
|-----|--------|---------|
| A | NAICS Category | Category name |
| B | NAICS Code | 4-digit NAICS code |
| C | Equipment included | One line per BioSTEAM unit whose cost items map to this row, format `UnitID (cost_key1, cost_key2, ...)` — derived at runtime from the simulated system, so it reflects the actual equipment present |
| D | 2025 USD (total) | Raw sum of `purchase_costs` for this row in the model's project dollar year (2025, CEPCI 809.3), before deflation |
| E | 2012 USD / kg SCP | Deflated and normalized value — see computation below |

| Row | NAICS Category | Code |
|-----|----------------|------|
| 0 | Heavy Gauge Metal Tanks | 3324 |
| 1 | Power Boilers and Heat Exchangers | 3324 |
| 2 | Pumps and Pumping Equipment | 3339 |
| 3 | Air and Gas Compressors | 3339 |
| 4 | Welding/Soldering/General Machinery | 3339 |
| 5 | Air Conditioning/Refrigeration/Heating | 3334 |

**Computation:** each unit's `purchase_costs` items are allocated to a NAICS row via `COST_KEY_TO_NAICS_ROW` in `common/lca_config.py`, then deflated from the model's 2025 dollar year (CEPCI 809.3) to the LCA base year (2012, CEPCI 584.6), then normalized per functional unit:

```
value = purchase_cost × (584.6 / 809.3) / (plant_life_yr × annual_production_kg/yr)
```

Allocation is at the **individual cost-item level**, not the unit level. Equipment with multiple sub-items (for example, `ExtentBasedBioreactor` carries vessel, agitator, aeration compressor, heat exchanger, air cooler, and recirculation pump cost keys) splits across multiple NAICS rows according to the type of sub-equipment. The full mapping is in `COST_KEY_TO_NAICS_ROW`; any unmapped key raises `KeyError` at runtime to force the map to stay current if BioSTEAM adds new cost items.

**PerfusionBioreactor sub-items** (gas fermentation R101) are prefixed `Cstr -` and `Cell separator -` by BioSTEAM's internal sub-unit naming:

| Cost key | NAICS row |
|----------|-----------|
| `Cstr - Vertical pressure vessel` | 0 — Heavy Gauge Metal Tanks |
| `Cstr - Platform and ladders` | 0 — Heavy Gauge Metal Tanks |
| `Cstr - Agitator - Agitator` | 4 — Welding/General Machinery |
| `Cell separator - Centrifuges` | 4 — Welding/General Machinery |

**DropletColumn contactors** (DC101, DC102, gas fermentation) report `Vertical pressure vessel` and `Platform and ladders`, mapping to row 0 (Heavy Gauge Metal Tanks).

### Sheet 2: Operational Flows

One row per material or energy flow, organised into **INPUTS** and **OUTPUTS** sections. Six columns:

| Col | Header | Content |
|-----|--------|---------|
| A | Material | Display label |
| B | Scope | Unit and stream IDs contributing to this row |
| C | Elementary Flow | Verbatim elementary flow string for openLCA |
| D | Units | Unit string for columns E and F |
| E | Value (per hr) | Computed value per operating hour in col D units |
| F | Value / kg SCP | Col E ÷ actual CNecatorBiomass flow from ST104 outlet (kg CDW/hr); denominator is the simulated product stream, not the production-target constant, so it reflects the true operating point |

| Route group | Input rows | Output rows | Total |
|-------------|-----------|-------------|-------|
| Fructose, acetate, formate | 10 | 18 | 28 |
| Gas fermentation | 13 | 20 | 33 |

Gas fermentation has three extra input rows (H₂ feed, CO₂ feed, O₂ feed) replacing the single liquid-substrate row, plus a fructose seed-train row and separate seed-only steam row, totalling 13 inputs. Its output section includes extra rows for dissolved gases (H₂, O₂, CO₂) in the liquid effluent that do not apply to liquid routes.

Row-level specifications — which unit IDs and stream IDs contribute to each row, the accessor type, and the units — are declared in `OP_FLOW_SPECS` in `common/lca_config.py`. The export function in `common/lca_export.py` is a thin interpreter of those specs with no route-specific logic.

**Key unit conventions:**

| Flow | Units | Conversion |
|------|-------|------------|
| Substrate feed | kg/hr | direct from `stream.imass[component]` |
| Nutrients salts | 2012 USD/hr | mass × composite $/kg × CEPCI ratio; cost rather than mass because `Nutrients` is a lumped BioSTEAM pseudo-component |
| Electricity | MWh/hr | `power_utility.consumption` kW ÷ 1000 |
| Water inputs | m³/hr | `stream.imass['H2O']` kg ÷ 1000 |
| Low-pressure steam | kg/hr | heat utility flow kmol/hr × 18.015 kg/kmol |
| Chilled water | m³/hr | heat utility flow kmol/hr × 18.015 / 1000 |
| WWT operating cost | 2012 USD/hr | non-H₂O mass in WWT inlet × WWT cost rate × CEPCI ratio |
| Water effluent | m³/hr | `unit_out_sum` over `RCY101.outs[1]` + `WWT102.outs[1]`, summed H₂O kg ÷ 1000. Includes both the treated discharge (RCY101) and the water in the sludge cake (WWT102 — 80% moisture per `WWT_SLUDGE_MOISTURE`; `_SludgeSettler` routes H₂O to sludge to meet this target) |
| Liquid effluent (all components) | kg/hr | `unit_out_sum` sums `RCY101.outs[1]` + `WWT102.outs[1]`; one row per component (no separate discharge vs. sludge rows) |
| Liquid effluent nutrients | kg/hr | `multi_out_unlump` sums `Nutrients` across `RCY101.outs[1]` + `WWT102.outs[1]`, then × per-salt mass fractions (7 individual rows, unlumped via `NUTRIENTS_RECIPE`) |
| Air emissions — bioreactor + dryer | kg/hr | `gas_out_sum` reads `unit.outs[0].imass[component]`; H₂O row combines bioreactor vents and spray dryer vapor (`D101.outs[0]`) in a single row |
| Air emissions — other gases | kg/hr | `gas_out_sum` over the aerated bioreactor list; one row per gas species |

**Steam scope note:** liquid routes heat-sterilize production media (HX101) and seed media (SHX101) — both appear in the steam row. Gas fermentation sterilizes production media by ultrafiltration (UF101, no steam); only SHX101 (seed media) uses steam.

**Chilled water scope note:** the 30 °C fermentation target is below the cooling water supply temperature (32.2 °C), so BioSTEAM selects chilled water for all bioreactor cooling and media coolers. Gas fermentation additionally uses chilled water for HX101 and HX102 (gas aftercoolers on the H₂ and CO₂ compression trains).

**Air supply note:** `ExtentBasedBioreactor` (liquid routes R101) and `SeedBioreactor` (SR101–SR103) expose a `.air` attribute; values are read via the `air_sum` accessor. `PerfusionBioreactor` (gas fermentation R101) is a closed pressurized vessel with no direct air supply — O₂ is dissolved via the droplet column — and has no `.air` attribute; it is silently skipped by the `air_sum` accessor.

---

## Source modules

### `common/lca_config.py`

Contains all configuration with no computation. Three structures drive the export:

- **`NAICS_CATEGORIES`** — ordered list of `(name, code)` tuples defining the six Capital Goods rows.
- **`COST_KEY_TO_NAICS_ROW`** — maps every observed BioSTEAM `purchase_costs` key to a row index (0–5). Any unmapped key raises `KeyError` at runtime.
- **`ELEMENTARY_FLOWS`** — maps short keys to verbatim elementary flow strings for the openLCA foreground model.
- **`OP_FLOW_SPECS`** — dict keyed by route name, each value a list of row-spec dicts. Each row spec declares `section`, `material`, `ef_key`, `units`, `scope` (list of unit/stream IDs), and `accessor` (tuple describing how to read the value). Liquid routes share specs generated by `_liquid_route_specs()`; gas fermentation is defined explicitly.

### `common/lca_export.py`

Public entry point: `export_lca_inventory(system, route, economics) -> pathlib.Path`.

Internally:
- `_compute_capital_goods()` — iterates `system.units`, sums `purchase_costs` into NAICS rows via `COST_KEY_TO_NAICS_ROW`. Returns a 3-tuple: (1) raw 2025 USD totals per row before deflation; (2) deflated and normalized 2012 USD / kg SCP values; (3) equipment-contents strings (`"UnitID (cost_key1, cost_key2, ...)"` per unit, newline-joined per row).
- `_compute_op_flows()` — loops `OP_FLOW_SPECS[route]`, calls `_evaluate_accessor()` per row, then `_apply_conversion()` for unit conversion.
- `_evaluate_accessor()` — dispatches per accessor type (`feed_stream`, `unit_in_sum`, `cost_sum`, `power_sum`, `h2o_feed_sum`, `utility_sum`, `air_sum`, `wwt_cost`, `discharge`, `gas_out_sum`, `dryer_vapor`, `unit_out_sum`, `multi_out_unlump`; plus legacy types `discharge_unlump`, `unit_out`, `unit_out_unlump` that remain valid but are not used in any current spec).
- `_write_workbook()` — writes two-sheet xlsx via openpyxl (row 1 bold, no color, no merged cells). Accepts `scp_kgh` (kg CDW/hr from the highest-CNecatorBiomass `system.products` stream) to populate the "Value / kg SCP" column on the Operational Flows sheet.

`composite_price` ($/kg nutrients, mass-weighted) is computed internally from `NUTRIENTS_RECIPE` via `build_nutrients_properties()` — the same call used by the model builders.

---

---

## How to make changes

**The single rule:** all customizable behavior lives in `common/lca_config.py`. Changes there propagate automatically to all four output workbooks on the next `run_models.py` run. `common/lca_export.py` only needs editing if you need a new accessor type (i.e., a new way of reading a value from BioSTEAM that none of the existing accessor types support).

---

### Change which NAICS row a cost item maps to

Open `common/lca_config.py` and change the row index for the relevant key in `COST_KEY_TO_NAICS_ROW`. The row indices correspond to positions in `NAICS_CATEGORIES` (0 = Heavy Gauge Metal Tanks, 1 = Power Boilers and Heat Exchangers, etc.).

Example — move UF membrane from row 4 to a hypothetical row 6:
```python
'UF membrane system': 6,   # was 4
```
Re-run `run_models.py`. All four workbooks regenerate immediately.

---

### Add or rename a NAICS category

1. Edit `NAICS_CATEGORIES` in `common/lca_config.py`. Each entry is a `(name, NAICS_code)` tuple; the order defines the row indices used by `COST_KEY_TO_NAICS_ROW`.
2. Update all affected row indices in `COST_KEY_TO_NAICS_ROW` to match the new positions.
3. Re-run `run_models.py`.

Example — add a seventh row for membrane equipment:
```python
NAICS_CATEGORIES = [
    ("Heavy Gauge Metal Tanks",                "3324"),  # 0
    ("Power Boilers and Heat Exchangers",       "3324"),  # 1
    ("Pumps and Pumping Equipment",             "3339"),  # 2
    ("Air and Gas Compressors",                "3339"),  # 3
    ("Welding/Soldering/General Machinery",    "3339"),  # 4
    ("Air Conditioning/Refrigeration/Heating", "3334"),  # 5
    ("Industrial Membrane Equipment",          "3559"),  # 6  ← new
]
```
Then change `'UF membrane system': 4` → `'UF membrane system': 6` in `COST_KEY_TO_NAICS_ROW`.

---

### Update an elementary flow string

Find the key in `ELEMENTARY_FLOWS` in `common/lca_config.py` and change its value to the exact string used in your openLCA database.

Example:
```python
ELEMENTARY_FLOWS = {
    ...
    'Steam': 'Natural gas, steam boiler, at plant',   # updated to match openLCA entry
    ...
}
```
Re-run `run_models.py`. The new string appears in Col C of the Operational Flows sheet for every row that references that `ef_key`.

---

### Add a new elementary flow

Add an entry to `ELEMENTARY_FLOWS` in `common/lca_config.py`, then reference the new key in the relevant row spec(s) in `OP_FLOW_SPECS`.

```python
ELEMENTARY_FLOWS = {
    ...
    'CO2_captured': 'Carbon dioxide, captured at plant',  # new
}
```

---

### Change which units or streams contribute to an Operational Flow row

Find the relevant row spec in `OP_FLOW_SPECS` in `common/lca_config.py` and edit its `scope` list and `accessor` args. Both must be updated together — `scope` is the Col B display label only; `accessor` is what actually reads the value.

Example — add unit `R102` to the electricity row for the fructose route. Because fructose uses `_liquid_route_specs()`, you would either pass a modified spec or override the generated list:
```python
# In OP_FLOW_SPECS['fructose'], find the electricity row and change:
'scope':    ['M101', 'R101', 'R102', 'C101', 'SM101', 'SR101', 'SR102', 'SR103'],
'accessor': ('power_sum',
             ['M101', 'R101', 'R102', 'C101', 'SM101', 'SR101', 'SR102', 'SR103']),
```
If all three liquid routes share the same topology, edit `_liquid_route_specs()` directly so the change applies to fructose, acetate, and formate simultaneously.

---

### Add a new Operational Flow row

Insert a new row-spec dict at the appropriate position in `OP_FLOW_SPECS[route]`. The position within the list sets the row order in the workbook; rows with `section='ins'` must all appear before rows with `section='outs'` (the writer inserts an INPUTS / OUTPUTS header on the first row of each section).

Required keys in the spec dict:

| Key | Type | Meaning |
|-----|------|---------|
| `section` | `'ins'` or `'outs'` | Which section header to place this row under |
| `material` | str | Col A — display label |
| `ef_key` | str | Key into `ELEMENTARY_FLOWS` for Col C |
| `units` | str | Col D — unit string (e.g. `'kg'`, `'MWh'`, `'m3'`, `'2012 USD'`) |
| `scope` | list[str] | Col B — unit IDs or stream IDs contributing to this row |
| `accessor` | tuple | `(type, *args)` — see accessor type table in `common/lca_config.py` docstring |

If the value requires a conversion not handled by an existing accessor + units combination, add a handler in `_apply_conversion()` in `common/lca_export.py`.

---

### Remove an Operational Flow row

Delete the relevant dict from the list in `OP_FLOW_SPECS[route]` in `common/lca_config.py`. If the row's `ef_key` is no longer used by any other row, you may also remove it from `ELEMENTARY_FLOWS`, though leaving unused keys there does no harm.

---

### Change the LCA dollar-year basis

Change `_CEPCI_LCA_BASE` in `common/lca_config.py` to the CEPCI value for your target dollar year. All Capital Goods values and cost-based Operational Flows (Nutrients, WWT) deflate using `_CEPCI_LCA_BASE / economics.CEPCI` at runtime.

```python
_CEPCI_LCA_BASE: float = 541.7   # 2010 CEPCI, for example
```

The model's project dollar year (and its CEPCI) is set in `common/parameters.py` via `ECONOMICS.CEPCI`.

---

### Add a new route

1. Add a `_liquid_route_specs(...)` call (or write explicit specs) for the new route key in `OP_FLOW_SPECS` in `common/lca_config.py`.
2. Add the route title to `_ROUTE_TITLES` in `common/lca_export.py`.
3. Run `export_lca_inventory()` once — any `purchase_costs` keys not in `COST_KEY_TO_NAICS_ROW` will raise `KeyError` identifying the key, unit ID, and class name. Add the missing entries to `COST_KEY_TO_NAICS_ROW`.

---

### Handle new BioSTEAM cost-item keys after a BioSTEAM upgrade

A `KeyError` from `_compute_capital_goods()` will identify the unmapped key, the unit ID, and the unit class name. Add the key to `COST_KEY_TO_NAICS_ROW` in `common/lca_config.py` with the appropriate row index and a comment indicating which unit type produces it.

---

## Dollar-year basis

All values are in **2012 USD** (CEPCI 584.6), matching the ecoinvent background database version used in this project. The model's 2025 dollar year (CEPCI 809.3) is deflated at export time by the factor 584.6 / 809.3 ≈ 0.722.

## Functional unit

1 kg SCP (dried *C. necator* biomass, ≤5% moisture), at 25,000 MT/yr annual production and 7,752 effective operating hours/yr.

---

## Stream balance check

`lca/stream_balance_check.py` is a standalone diagnostic script that verifies coverage of the LCA inventory against the simulated system:

```
python lca/stream_balance_check.py
```

Produces a stdout-only report (writes nothing to disk). For each route it prints:

1. **System boundary — feed streams**: every stream in `system.feeds` (excluding `recycle_water`) with non-zero component flows, and which `OP_FLOW_SPECS` row covers each.
2. **Bioreactor gas vents** (`outs[0]`): component flows from R101/SR101–SR103 (liquid routes) or SR101–SR103 (gas ferm; R101 has no gas vent), with coverage.
3. **Spray dryer vapor** (`D101.outs[0]`): H₂O and any other vapor components.
4. **Liquid effluents**: `RCY101.outs[1]` (discharge) and `WWT102.outs[1]` (sludge), component-by-component.
5. **Product stream**: CNecatorBiomass and H₂O flow from the ST104 outlet (not a system emission).
6. **OP_FLOW_SPECS evaluated**: every row for this route evaluated against the simulated system, showing the same values that appear in the xlsx.
7. **Coverage check**: any non-zero system-boundary flow with no corresponding `OP_FLOW_SPECS` row. Reports `None (ok)` if all flows are covered.

The script imports `_evaluate_accessor` and `_apply_conversion` directly from `common/lca_export.py`, so section 6 uses the identical code path as the xlsx generator.
