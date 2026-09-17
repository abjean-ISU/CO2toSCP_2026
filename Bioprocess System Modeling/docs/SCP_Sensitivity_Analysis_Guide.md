# Sensitivity Analysis User Guide

**Document scope:** How `sensitivity_analysis.py` works, how to add a new parameter, and how to interpret the outputs.
**Last updated:** 2026-08-10
**Implementation:** `sensitivity_analysis.py`
**Output:** `outputs/sensitivity_results.xlsx`, `outputs/sensitivity_tornado_{route}.png`

---

## 1. What the SA does

The sensitivity analysis is a **one-at-a-time (OAT)** method: one parameter is changed from its base value while all others are held fixed. For each perturbation, the full model is rebuilt and re-simulated, and the resulting change in MSP (the "swing") is recorded. Repeating this for all parameters and both directions (low and high) produces a ranked picture of which parameters matter most for each route.

**Why OAT rather than Monte Carlo?** OAT is more transparent and auditable. Every row in `sensitivity_results.xlsx` corresponds to a single, identifiable simulation with a specific parameter value — the reader can verify any swing by changing that one value in the model and re-running. Monte Carlo collapses all interactions into a distribution that is harder to trace back to physics.

**Simulation count (all 4 routes, 11 parameters):**
- 4 base runs (one per route)
- 11 parameters × 2 directions × 4 routes = 88 perturbation runs
- Minus 1 skipped run (gas fermentation ε low: see §3.2)
- **Total: 91 simulations**

---

## 2. The parameter registry (`_SA_PARAMS`)

Each parameter is a `_SAParam` named tuple:

```python
class _SAParam(typing.NamedTuple):
    category:    str       # 'economics' | 'route' | 'global' | 'global_recipe_conc'
    field:       str       # attribute name to perturb
    label:       str       # tornado y-axis label
    lo:          float     # low absolute value, or low factor (if is_relative)
    hi:          float     # high absolute value, or high factor (if is_relative)
    is_relative: bool      # True → actual value = base_value × lo/hi
    section:     str       # §9.x citation for audit trail
    skip_lo:     frozenset # routes to skip the low perturbation (default empty)
    skip_hi:     frozenset # routes to skip the high perturbation (default empty)
```

### 2.1 Categories

The `category` field controls how the perturbation is applied:

| Category | What it perturbs | Mechanism |
|----------|-----------------|-----------|
| `'economics'` | One field of `EconomicBasis` | `dataclasses.replace(ECONOMICS, field=val)` — new economics object passed to builder |
| `'route'` | One field of `RouteParams` | `dataclasses.replace(get(route), field=val)` — new route params passed to builder |
| `'global'` | A module-level constant shared across routes | `_patch_attrs(...)` — patches all import locations simultaneously (see §4) |
| `'global_recipe_conc'` | `NUTRIENTS_RECIPE.concentrations` dict | All concentration values scaled by a factor; `NUTRIENTS_RECIPE` patched everywhere it is imported |

### 2.2 Relative vs. absolute values

- `is_relative=False`: `lo` and `hi` are the absolute values applied (e.g., electricity_price = $0.018/kWh)
- `is_relative=True`: `lo` and `hi` are multipliers on the base value (e.g., feedstock_price_factor = 0.50 → actual = base × 0.50)

In the output Excel, both the factor and the actual perturbed value are recorded so the reader can always verify what was applied.

### 2.3 Direction labeling

The direction label ('low' / 'high') reflects the actual perturbation direction relative to the **base value**, not which slot (lo/hi) the number came from. This matters for gas fermentation ε:

- Gas fermentation base ε = 0.99
- The only ε perturbation for gas fermentation runs from the `hi` slot (value = 0.95)
- Since 0.95 < 0.99 (base), the effective direction is labeled **'low'** in the output

The code that enforces this:
```python
if base_param_val is not None:
    if pert_val_display < base_param_val:
        effective_direction = 'low'
    elif pert_val_display > base_param_val:
        effective_direction = 'high'
    else:
        effective_direction = direction
```

This ensures the tornado chart and Excel output always reflect the true direction of change, regardless of which slot holds which value.

### 2.4 Skip flags

`skip_lo` and `skip_hi` are frozensets of route names for which a given direction should not be run. Used when a perturbation is not meaningful for a specific route:

```python
# gas_fermentation base ε = 0.99; lo=0.80 is so far below base it is not
# a useful perturbation point — skip lo, run only hi=0.95 for that route.
_SAParam('route', 'epsilon', 'Substrate conversion (ε)', 0.80, 0.95, False, '§9.2',
         skip_lo=frozenset({'gas_fermentation'}))
```

The skipped run contributes `NaN` to the Tornado Summary range column for that route×direction.

---

## 3. Current parameters (11 total)

| # | Field | Label | Category | Lo | Hi | Relative? | Section |
|---|-------|-------|----------|----|----|----------|---------|
| 1 | `epsilon` | Substrate conversion (ε) | route | 0.80 | 0.95 | No | §9.2 |
| 2 | `D_margin` | Dilution rate (fraction of μmax) | route | 0.70 | 0.85 | No | §9.2 |
| 3 | `target_titer_fraction` | Target titer (fraction of max) | route | 0.60 | 0.90 | No | §9.2 |
| 4 | `CENTRIFUGE_RECOVERY` | Centrifuge recovery (% biomass) | global | 0.90 | 0.98 | No | §9.2 |
| 5 | `RESTART_FREQUENCY_PER_LINE` | Restart frequency (per line/yr) | global | 1.5 | 2.5 | No | §9.2 |
| 6 | `NUTRIENTS_RECIPE` | Nutrient recipe scaling (×base) | global_recipe_conc | 0.50 | 1.50 | Yes | §9.3 |
| 7 | `feedstock_price` | Feedstock price ($/kg) | route | 0.50 | 1.50 | Yes | §9.4 |
| 8 | `electricity_price` | Electricity price ($/kWh) | economics | 0.018 | 0.087 | No | §9.4 |
| 9 | `ammonia_price` | Ammonia price ($/kg) | economics | 0.50 | 1.50 | Yes | §9.4 |
| 10 | `contingency_fee_factor` | Capital cost (TCI ±35%) | economics | 0.65 | 1.35 | Yes | §9.4 |
| 11 | `WWT_WATER_RECYCLE_FRACTION` | Water recycle fraction | global | 0.50 | 0.90 | No | §9.2 |

Note: parameter #3 (`target_titer_fraction`) is `n/a` for gas fermentation (the perfusion bioreactor does not use a titer target), but it is not skipped — gas fermentation's builder simply ignores the field. The resulting swing is ~$0.00/kg, which correctly appears in the tornado as a zero-width bar.

---

## 4. The multi-module patching system

### 4.1 The problem

Python's `from module import NAME` creates a **local binding** at import time. After that, the local name is independent of the original module:

```python
# In models/fructose_model.py:
from common.parameters import CENTRIFUGE_RECOVERY  # creates fructose_model.CENTRIFUGE_RECOVERY

# Later, in sensitivity_analysis.py:
_params.CENTRIFUGE_RECOVERY = 0.90   # patches _params only
# fructose_model.CENTRIFUGE_RECOVERY is STILL 0.95 — the import binding is frozen
```

If you only patch `_params.CENTRIFUGE_RECOVERY`, the model builder will use the old value from its own frozen local binding.

### 4.2 The solution: `_patch_attrs`

`_patch_attrs` is a context manager that simultaneously patches multiple `(module, attribute, value)` triples and restores all originals on exit, even if an exception is raised:

```python
@contextlib.contextmanager
def _patch_attrs(patches: list[tuple]):
    originals = [(mod, attr, getattr(mod, attr)) for mod, attr, _ in patches]
    for mod, attr, val in patches:
        setattr(mod, attr, val)
    try:
        yield
    finally:
        for mod, attr, orig in originals:
            setattr(mod, attr, orig)
```

Usage:
```python
with _patch_attrs([
    (_params,          'CENTRIFUGE_RECOVERY', 0.90),
    (_fructose_model,  'CENTRIFUGE_RECOVERY', 0.90),
    (_acetate_model,   'CENTRIFUGE_RECOVERY', 0.90),
    (_formate_model,   'CENTRIFUGE_RECOVERY', 0.90),
    (_gas_ferm_model,  'CENTRIFUGE_RECOVERY', 0.90),
]):
    msp = _run_single(route, params, economics, run_id)
```

After the `with` block, all five attributes are restored to their original values.

### 4.3 `_global_patches(field, val)` — patch target registry

For each `'global'` category parameter, `_global_patches()` returns the complete list of `(module, attr, value)` tuples that must be patched. The current patch targets are:

**`CENTRIFUGE_RECOVERY`** — 5 targets
```python
[(_params, 'CENTRIFUGE_RECOVERY', val)]
+ [(m, 'CENTRIFUGE_RECOVERY', val) for m in [_fructose_model, _acetate_model,
                                               _formate_model, _gas_ferm_model]]
```
The four model modules import this directly for sizing the centrifuge. `_params` is also patched for consistency.

**`RESTART_FREQUENCY_PER_LINE`** — 3 targets
```python
[
    (_params,     'RESTART_FREQUENCY_PER_LINE', val),
    (_op_hours,   'CONTAMINATION_RESTART_H',    val * _op_hours.RESTART_DURATION_H),
    (_seed_train, 'CONTAMINATION_RESTART_H',    val * _op_hours.RESTART_DURATION_H),
]
```
The model builders do not import `RESTART_FREQUENCY_PER_LINE` directly. What they use is `CONTAMINATION_RESTART_H = RESTARTS_PER_YEAR × RESTART_DURATION_H` from `common/operating_hours.py` and `common/seed_train.py`. Patching requires converting the restarts/yr value to the derived `CONTAMINATION_RESTART_H` and patching both modules that imported it directly.

**`WWT_WATER_RECYCLE_FRACTION`** — 6 targets
```python
[(_params, 'WWT_WATER_RECYCLE_FRACTION', val), (_wastewater, 'WWT_WATER_RECYCLE_FRACTION', val)]
+ [(m, 'WWT_WATER_RECYCLE_FRACTION', val) for m in [_fructose_model, _acetate_model,
                                                      _formate_model, _gas_ferm_model]]
```
Used in two distinct contexts: at model-build time (model modules import it to compute the recycle-water seed flow) and at call time inside `build_wastewater_treatment()` (wastewater.py imports it as the RCY101 split fraction). Both must be patched.

### 4.4 `'global_recipe_conc'` — nutrients recipe patching

The nutrients recipe is a `NutrientsRecipe` dataclass, not a scalar. The perturbation scales all concentration values by a factor:

```python
perturbed_recipe = dataclasses.replace(
    _params.NUTRIENTS_RECIPE,
    concentrations={k: v * factor for k, v in _params.NUTRIENTS_RECIPE.concentrations.items()},
)
patches = [(m, 'NUTRIENTS_RECIPE', perturbed_recipe)
           for m in [_params, _fructose_model, _acetate_model,
                     _formate_model, _gas_ferm_model, _chemicals]]
```

Six targets are patched: the four model modules, `_params`, and `_chemicals` (which reads the recipe inside `build_chemicals()` to set the Nutrients pseudo-component properties).

---

## 5. How to add a new SA parameter

### Step 1 — Identify the parameter and its category

First answer: where does the parameter live?
- Is it a field of `EconomicBasis` (in `ECONOMICS`)? → category `'economics'`
- Is it a field of `RouteParams` (per-route, different value per route)? → category `'route'`
- Is it a module-level constant in `common/parameters.py` imported directly by model modules? → category `'global'`
- Is it the nutrients recipe dict? → category `'global_recipe_conc'`

### Step 2 — Determine the perturbation range

The range must be grounded in a §9 parameter registry entry or an explicit justification. Per the project's hard rules:
- Do not use a ±X% convention without justification
- Record the literature source or engineering judgment in the `_SAParam` section field
- If the parameter has an n/a SA range in the Framework (§9.4), it should not be added to `_SA_PARAMS` without first discussing the decision in the Framework doc

### Step 3 — Add the `_SAParam` entry

Add to `_SA_PARAMS` in `sensitivity_analysis.py`:

```python
_SAParam(
    category='economics',          # or 'route', 'global', 'global_recipe_conc'
    field='my_new_param',          # exact attribute name
    label='My new parameter label', # text shown on tornado y-axis
    lo=0.10,                       # low absolute value (or factor if is_relative=True)
    hi=0.30,                       # high absolute value (or factor if is_relative=True)
    is_relative=False,             # True if lo/hi are multipliers on base value
    section='§9.4',                # Framework §9.x citation
    # skip_lo=frozenset({'gas_fermentation'}),  # if needed
)
```

### Step 4 — For `'global'` parameters: update `_global_patches()`

If your parameter is a global constant, you must add a branch to `_global_patches()`. Follow the existing pattern:

1. Determine which modules import the constant directly (search the codebase for the constant name)
2. For each such module, add `(module_alias, 'CONSTANT_NAME', val)` to the patch list
3. Add the module alias to the import block at the top of the file

**Example: adding a new constant `MY_CONST` imported by the four model modules:**

```python
# 1. Add to imports at the top:
import models.my_new_module as _my_new_module  # if applicable

# 2. Add branch to _global_patches():
if field == 'MY_CONST':
    return (
        [(_params, field, val)]
        + [(m, field, val) for m in _ALL_MODELS]
    )
```

**Verify the patch targets by grep:**
```bash
grep -rn "MY_CONST" common/ models/ perfusion_bioreactor/
```
Every module that appears in the grep output and imports the constant via `from ... import MY_CONST` or has `MY_CONST = ...` at module level must be included in the patch list.

### Step 5 — Update simulation count docstrings

`run_oat_sensitivity()` has a docstring stating the simulation count. Update it:
```
Simulation count for all 4 routes:
    4 base runs + {N} params × 2 directions × 4 routes − {skips} = {total} total.
```

### Step 6 — Update `docs/SCP_Project_Framework.md §11`

The Framework doc tracks the SA parameter table and simulation count. Update:
- The parameter table (add a row for the new parameter)
- The simulation count statement
- If a new global parameter was added, update the patching targets table

---

## 6. Interpreting the outputs

### 6.1 `sensitivity_results.xlsx` — three sheets

**OAT Results sheet**

One row per (route × parameter × direction). Key columns:

| Column | Meaning |
|--------|---------|
| Route | Route name |
| Parameter | Field name (e.g. 'epsilon') |
| Label | Human-readable label (tornado y-axis) |
| Direction | 'low' or 'high' (actual perturbation direction vs. base) |
| Base param value | Base value of the parameter (None for recipe) |
| Perturbed value | Actual value applied in this run |
| Base MSP ($/kg) | MSP at base case for this route |
| Perturbed MSP ($/kg) | MSP with this perturbation |
| MSP swing ($/kg) | Perturbed − Base (positive = MSP increased) |
| MSP swing (%) | Swing / Base × 100 |
| op_hours (h/yr) | Effective operating hours (reflects restart-frequency patching) |
| FCI ($MM) | Fixed capital investment ($M) |
| N_reactors | Production vessel count including N+1 spare |
| N_seed_trains | Number of concurrent seed trains |
| Q (m³/h) | Volumetric throughput at production bioreactor inlet |
| Feedstock ($/kg) | Feedstock OPEX per kg SCP |
| ... ($/kg) | Other OPEX categories per kg SCP |
| Capital charge ($/kg) | MSP residual after all other categories |
| Feedstock ($MM/yr) | Feedstock OPEX per year |
| ... ($MM/yr) | Other OPEX categories per year |

**OPEX categories** (10 total, each in $/kg and $MM/yr):
1. Feedstock — carbon source feed streams
2. Ammonia — NH₃ co-reactant
3. Nutrients — mineral salts
4. Electricity — all electrical consumption (aeration compressors, etc.)
5. Other utilities — steam and cooling water
6. Waste disposal — WWT sludge (negative-priced product stream)
7. Labor — $3.6M/yr
8. Maintenance — 10% × FCI
9. Other FOC — property tax + insurance + administration (7% × FCI combined)
10. Capital charge — residual ensuring categories sum exactly to MSP

**Tornado Summary sheet**

One row per parameter, sorted descending by maximum |swing| across all routes and directions. Columns: Label, Category, Section, plus `{route}_lo`, `{route}_hi`, `{route}_range` for each route. This is the source data for `plot_cross_route_tornado()` in `additional_analyses.py`.

**Base Case Design sheet**

One row per route: base MSP, design variables (op_hours, FCI, N_reactors, N_seed_trains, Q), and full OPEX breakdown at base case. The "control" state that each OAT row deviates from.

### 6.2 Tornado charts (`sensitivity_tornado_{route}.png`)

Each chart shows one bar pair (low perturbation in blue/hatched, high in orange/hatched) per parameter, sorted so the widest bar (most impactful parameter) appears at the top. The x-axis is MSP swing in $/kg SCP, zero-centered.

**Reading the chart:**
- A bar extending left means this perturbation *reduces* MSP (favorable)
- A bar extending right means this perturbation *increases* MSP (unfavorable)
- The total width of both bars together is the "total swing range" — the key metric for ranking parameters
- A symmetric chart (both bars same length) means the parameter effect is linear in MSP; asymmetry indicates nonlinearity

**What asymmetry means:** For feedstock price (relative perturbation, ±50%), the low and high bars are equal length because the feedstock cost enters MSP linearly. For electricity price (asymmetric absolute range: $0.018–$0.087/kWh around a base of $0.032/kWh), the high bar is longer because the high value is further from base than the low value is.

### 6.3 Cross-route tornado (`cross_route_tornado.png`)

Generated by `plot_cross_route_tornado()` in `additional_analyses.py`. Shows total swing range (|hi_swing − lo_swing|) per parameter per route as grouped horizontal bars, sorted by mean range across routes. Useful for identifying which parameters are universally important vs. route-specific.

### 6.4 2D sensitivity heatmaps (`2d_sa_{route}.png`)

Generated by `run_2d_sensitivity()` in `additional_analyses.py`. Show MSP across a grid of two parameters simultaneously. The base case cell is highlighted with a black border. Color scale: green = low MSP, red = high MSP.

For gas fermentation: electricity price × contingency_fee_factor (the two largest single-parameter drivers).
For liquid routes: feedstock price factor × ε (the two largest single-parameter drivers).

Heatmaps reveal interaction effects not visible in OAT charts. If the MSP contours are parallel straight lines, the two parameters are independent; if the contours curve, there is a nonlinear interaction.

---

## 7. Running a subset

```python
# Single route
from sensitivity_analysis import run_oat_sensitivity
paths = run_oat_sensitivity(routes=['acetate'])

# Two routes
paths = run_oat_sensitivity(routes=['fructose', 'formate'])

# Replot tornados from an existing Excel file (no re-simulation)
from sensitivity_analysis import replot_tornados
paths = replot_tornados()  # reads outputs/sensitivity_results.xlsx
```

---

## 8. Common issues

**Issue: new parameter swing is zero for all routes**

Check that the perturbation is actually reaching the model builder. If the parameter is a global constant imported by model modules, you probably need to add it to `_global_patches()`. Verify by adding a `print(val)` inside the model builder at the place where the constant is used.

**Issue: new global parameter swap doesn't work even after adding to `_global_patches()`**

Check the import style. If the model module uses `from common.parameters import MY_CONST` (direct binding) rather than `from common import parameters as _params; _params.MY_CONST` (attribute access), only the direct binding is frozen — patching `_params.MY_CONST` has no effect. You must patch the model module's local binding too. Grep for the constant name in all model files.

**Issue: gas fermentation ε low perturbation is showing up as 'high'**

Check whether the model is running the `effective_direction` correction. Verify: `base_param_val` is not None (it will be None for `global_recipe_conc` parameters but should be a float for `route` parameters like epsilon). The correction only applies when `base_param_val is not None`.

**Issue: simulation count is wrong in the docstring**

After adding or removing a parameter or a skip, update both the docstring in `run_oat_sensitivity()` and the Framework §11 simulation count statement.

**Issue: BioSTEAM CostWarning spam in output**

BioSTEAM emits `CostWarning` when a vessel is outside its cost-correlation range. These are suppressed with `warnings.simplefilter('ignore')` inside `_run_single()` and `_run_single_with_design()`. The warnings do not affect MSP values, only the equipment cost confidence — which is why the TCI ±35% parameter is included to bound this uncertainty.
