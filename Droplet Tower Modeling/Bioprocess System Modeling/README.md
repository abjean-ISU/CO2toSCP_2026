# SCP Techno-Economic Analysis — Library Reference

This library contains BioSTEAM-based techno-economic analysis (TEA) models comparing four single-cell protein (SCP) production routes using *Cupriavidus necator* (*C. necator*) as the host organism. All four routes share the same host, same battery limits, and the same evaluation framework — differences in results reflect real process physics, not inconsistent modeling choices.

**Routes:**
- **Fructose** — heterotrophic growth on fructose sugar
- **Acetate** — heterotrophic growth on acetic acid
- **Formate** — heterotrophic growth on formic acid
- **Gas fermentation** — lithoautotrophic growth on H₂/CO₂

**Key authoritative documents** (read before changing any code):
- `docs/SCP_Project_Framework.md` — architecture, decisions, and reasoning
- `docs/SCP_Implementation_Spec.md` — function signatures, equations, pseudocode
- `docs/SCP_Perfusion_Bioreactor_Math.md` — governing equations for the gas fermentation bioreactor
- `docs/SCP_Liquid_Route_Math.md` — governing equations for the fructose/acetate/formate bioreactors

**Reference documents** (explanatory, for users and analysts):
- `docs/SCP_Parameter_Registry.md` — every numeric parameter, its value, unit, and source citation
- `docs/SCP_Route_Comparison.md` — why the four MSPs differ; substrate economics and capital economics levers
- `docs/SCP_Sensitivity_Analysis_Guide.md` — how the OAT SA is structured, how to add parameters, how to interpret outputs

---

## Quick start

```bash
# Run all four route models and generate per-route Excel workbooks
python run_models.py

# Run one-at-a-time sensitivity analysis (91 simulations)
python sensitivity_analysis.py

# Run additional comparative analyses (cost breakdown, scale curve, 2D heatmaps)
# Note: plot_cross_route_tornado reads outputs/sensitivity_results.xlsx,
# so sensitivity_analysis.py must be run first.
python additional_analyses.py
```

All outputs land in `outputs/`.

---

## Repository layout

```
Bioprocess System Modeling/
├── run_models.py               # top-level driver — build, simulate, TEA, export
├── sensitivity_analysis.py     # OAT sensitivity analysis (11 parameters, 91 runs)
├── additional_analyses.py      # cost breakdown, scale curve, cross-route tornado, 2D SA
├── common/                     # shared modules — one implementation per concern
│   ├── chemicals.py            # BioSTEAM chemicals registry (all species, biomass formula)
│   ├── parameters.py           # parameter registry (RouteParams, EconomicBasis, globals)
│   ├── kinetics.py             # reactor design chain and stoichiometry
│   ├── reactors.py             # ExtentBasedBioreactor and SeedBioreactor classes
│   ├── nutrients.py            # nutrients composite price, coefficient, mass fractions
│   ├── seed_train.py           # 3-stage seed train builder
│   ├── economics.py            # SCPTEA class, build_tea(), configure_utility_prices()
│   ├── wastewater.py           # WWT101/WWT102/RCY101 subsystem builder
│   ├── sterilization.py        # UltrafiltrationSterilizer (gas fermentation only)
│   ├── operating_hours.py      # effective operating hours derivation (7,752 h/yr)
│   ├── export.py               # 7-sheet Excel workbook, PFD, unit details, cross-route comparison
│   ├── lca_config.py           # NAICS mapping, elementary flows, per-route OP_FLOW_SPECS
│   └── lca_export.py           # export_lca_inventory() — LCI workbook generator
├── models/                     # route-specific model builders
│   ├── fructose_model.py       # build_fructose_system()
│   ├── acetate_model.py        # build_acetate_system()
│   ├── formate_model.py        # build_formate_system()
│   └── gas_fermentation_model.py  # build_gas_fermentation_system()
├── perfusion_bioreactor/       # custom BioSTEAM unit for gas fermentation
│   ├── droplet_column.py       # DropletColumnContactor — H₂/CO₂ pre-saturation
│   └── unitwithauxiliary.py    # PerfusionBioreactor — aerated perfusion vessel
├── docs/                       # documentation
│   ├── SCP_Project_Framework.md          # authoritative — architecture and decisions
│   ├── SCP_Implementation_Spec.md        # authoritative — function signatures and pseudocode
│   ├── SCP_Perfusion_Bioreactor_Math.md  # authoritative — gas fermentation math
│   ├── SCP_Liquid_Route_Math.md          # authoritative — liquid route math
│   ├── SCP_Parameter_Registry.md         # reference — all parameters, values, and sources
│   ├── SCP_Route_Comparison.md           # reference — why the four MSPs differ
│   └── SCP_Sensitivity_Analysis_Guide.md # reference — OAT SA structure and interpretation
├── lca/                        # LCA inventory assessment workbooks (auto-generated)
│   ├── README.md                       # how these files are structured and generated
│   ├── Fructose_InventoryAssessment.xlsx
│   ├── Acetate_InventoryAssessment.xlsx
│   ├── Formate_InventoryAssessment.xlsx
│   └── GasFerment_InventoryAssessment.xlsx
└── outputs/                    # all generated files (gitignored if large)
    ├── {route}_results.xlsx            # 7-sheet workbook per route
    ├── {route}_unit_details.xlsx       # per-unit stream tables
    ├── {route}_unit_details.txt        # per-unit design results (text)
    ├── {route}_pfd.png / .html         # process flow diagram
    ├── cross_route_comparison.xlsx     # summary across all routes
    ├── sensitivity_results.xlsx        # OAT SA results (3 sheets)
    ├── sensitivity_tornado_{route}.png # per-route tornado charts
    ├── cost_breakdown.png / .xlsx      # stacked-bar cost breakdown
    ├── scale_curve.png / .xlsx         # MSP vs. production scale
    ├── cross_route_tornado.png         # cross-route sensitivity comparison
    └── 2d_sa_{route}.png / 2d_sa_results.xlsx  # 2D sensitivity heatmaps
```

---

## File-by-file reference

### Root-level scripts

#### `run_models.py`

Top-level driver that builds, simulates, and exports all four routes.

**What it does:**
1. Iterates over all routes in `_BUILDERS` (fructose → acetate → formate → gas_fermentation).
2. For each route: opens a `bst.Flowsheet` (isolates unit/stream IDs), calls the route's builder, calls `system.simulate()`, builds a `SCPTEA`, identifies the product stream, and computes MSP.
3. Exports TEA results via `common/export.py` — 7-sheet workbook, unit details (xlsx + txt), and PFD.
4. Exports LCA inventory via `common/lca_export.py` — Capital Goods and Operational Flows workbook in `lca/`.
5. After all routes: writes `cross_route_comparison.xlsx`.

**How to run:**
```bash
python run_models.py
```

**To run a subset of routes:**
```python
from run_models import main
results = main(routes=['fructose', 'acetate'])
```

**Output per route:**
- `outputs/{route}_results.xlsx` — 7-sheet workbook (see `common/export.py` below)
- `outputs/{route}_unit_details.xlsx` — per-unit stream tables
- `outputs/{route}_unit_details.txt` — per-unit design results (text)
- `outputs/{route}_pfd.png` and `outputs/{route}_pfd.html` — process flow diagram (requires Graphviz on PATH)
- `lca/{RouteTitle}_InventoryAssessment.xlsx` — LCA inventory workbook (see `common/lca_export.py` below)
- `outputs/cross_route_comparison.xlsx` — when ≥2 routes run

---

#### `sensitivity_analysis.py`

One-at-a-time (OAT) sensitivity analysis across all four routes and 11 parameters.

**What it does:**
1. Runs a base case for each route (4 simulations) and records MSP, design variables, and OPEX breakdown.
2. For each of 11 parameters, perturbs to low and high values and re-simulates (up to 91 total runs).
3. Computes MSP swing ($/kg and %) and OPEX breakdown per perturbation.
4. Exports tornado charts (4 PNGs) and a 3-sheet Excel workbook.

**The 11 SA parameters** (see `_SA_PARAMS` in the script):

| # | Label | Range | Routes |
|---|-------|-------|--------|
| 1 | Substrate conversion (ε) | 0.80 – 0.95 | all |
| 2 | Dilution rate (fraction of μmax) | 0.60 – 0.90 | all |
| 3 | Target titer (fraction of max) | 0.60 – 0.90 | liquid |
| 4 | Centrifuge recovery | 85 % – 98 % | all |
| 5 | Restart frequency | 1 – 4 /yr | all |
| 6 | Nutrient recipe scaling | 0.5× – 1.5× | all |
| 7 | Feedstock price | 0.5× – 1.5× base | all |
| 8 | Electricity price | $0.018 – $0.087/kWh | all |
| 9 | Ammonia price | $0.35 – $0.75/kg | all |
| 10 | Capital cost (TCI) | ±35% | all |
| 11 | Water recycle fraction | 50 % – 90 % | all |

**How to run:**
```bash
python sensitivity_analysis.py
```

**Output:**
- `outputs/sensitivity_results.xlsx` — 3 sheets:
  - *OAT Results*: one row per (route × parameter × direction), including design variables and OPEX breakdown (10 categories × $/kg + $/MM/yr)
  - *Tornado Summary*: per-route sorted swing table
  - *Base Case Design*: design variables + OPEX for each route at base case
- `outputs/sensitivity_tornado_{route}.png` — 4 PNG tornado charts

---

#### `additional_analyses.py`

Four supplementary comparative analyses that do not require re-implementing route logic.

**What it does:**

1. **Cost breakdown** (`run_cost_breakdown`): Decomposes each route's MSP into 10 cost categories (Feedstock, Ammonia, Nutrients, Electricity, Other utilities, Waste disposal, Labor, Maintenance, Other FOC, Capital charge). Capital charge is the residual — it ensures categories sum exactly to MSP. Produces a stacked-bar chart and Excel table.

2. **Scale curve** (`run_scale_curve`): Sweeps production target from 5,000 to 100,000 MT/yr for all routes (40 simulations). Shows how MSP changes with plant scale. Produces a log-scale line chart and Excel table.

3. **Cross-route tornado** (`plot_cross_route_tornado`): Single figure comparing all four routes' total OAT sensitivity swing per parameter. Reads existing `sensitivity_results.xlsx` — no new simulations. Sorted by mean range across routes.

4. **2D sensitivity** (`run_2d_sensitivity`): Heatmaps for two key parameter pairs:
   - Gas fermentation: electricity price × Lang factor (25 runs)
   - Liquid routes (each): feedstock price × ε (20 runs × 3 routes = 60 runs)
   Total: 85 new simulations.

**How to run:**
```bash
python additional_analyses.py
```

**Output:**
- `outputs/cost_breakdown.png`, `outputs/cost_breakdown.xlsx`
- `outputs/scale_curve.png`, `outputs/scale_curve.xlsx`
- `outputs/cross_route_tornado.png`
- `outputs/2d_sa_{route}.png` (4 files), `outputs/2d_sa_results.xlsx`

---

### `common/` — shared modules

All logic shared across routes lives here exactly once.

---

#### `common/chemicals.py`

Defines all BioSTEAM chemical species used by the four routes and registers them via `bst.settings.set_thermo()`. Called once at startup; every module that needs the chemicals registry imports from here or calls this before using `bst.settings.chemicals`.

**Key species defined:**
- Carbon substrates: Fructose (C₆H₁₂O₆), AceticAcid (C₂H₄O₂), FormicAcid (CH₂O₂), H₂
- Metabolic gases: O₂, CO₂, N₂, H₂O
- Nitrogen source: NH₃
- Host biomass: `CNecatorBiomass` — empirical formula C₄.₀₉H₇.₁₃O₁.₈₉N₀.₇₆ (MW ≈ 97.2 g/mol)
- Nutrients: `Nutrients` pseudo-component (all mineral salts lumped)
- Wastewater: H₂O (water balance, recycle)

---

#### `common/parameters.py`

Single source of truth for all numeric parameters. Nothing in the codebase should hardcode a value that belongs here.

**Three dataclasses:**
- `RouteParams` — per-route kinetics and design: `mu_max`, `Yxs`, `max_titer`, `epsilon`, `D_margin`, `target_titer_fraction`, `feedstock_price`
- `NutrientsRecipe` — raw recipe dict: `concentrations` (g/L), `prices` ($/kg), `achieved_titer`
- `EconomicBasis` — shared TEA basis: IRR, CEPCI, depreciation, labor, utility prices, etc.

**Module-level constants** (shared by all routes):
- `THETA_O2 = 0.5` — dissolved O₂ setpoint fraction
- `RESTART_FREQUENCY_PER_LINE = 2.0` — contamination restarts/yr per line
- `CENTRIFUGE_RECOVERY = 0.95` — fraction of biomass recovered
- `CENTRIFUGE_CAKE_MOISTURE = 0.75` — centrifuge cake water fraction
- `SPRAY_DRYER_MOISTURE = 0.05` — final product moisture
- `PRODUCTION_TARGET_MT_YR = 25_000.0` — annual production target (final product)
- `T_STERILIZATION_K = 407.15` — continuous media sterilization temperature (134 °C)
- `T_FERMENTATION_K = 303.15` — fermentation temperature (30 °C)
- `WWT_ORGANIC_REMOVAL = 0.99` — WWT organic removal fraction
- `WWT_WATER_RECYCLE_FRACTION = 0.75` — treated water recycle fraction
- `MIX_TANK_TAU = 1.0 h` — feed mixer residence time
- `STORAGE_TANK_TAU = 168.0 h` — feedstock/product storage (7 days)
- `INOCULUM_RATIO = 0.05` — seed inoculum fraction
- `SEED_BATCH_DURATION_H = 72.0` — 3-stage seed batch duration

**Public API:** `get(route)` → `RouteParams`; `ECONOMICS` singleton; `NUTRIENTS_RECIPE` singleton.

---

#### `common/kinetics.py`

Reactor design calculations and stoichiometry. No simulation — pure calculation.

**Key public functions:**

`required_fermenter_output(target_MT_yr, downstream_efficiencies)` → float
: Backward pass: walks from final product target to required fermenter CDW output, dividing by each downstream step's recovery efficiency.

`design_reactor(mu_max, Yxs, max_titer, epsilon, D_margin, target_titer_fraction, adjusted_MT_yr)` → dict
: Forward design chain for liquid-substrate routes (fructose, acetate, formate). 9-step calculation returning X*, S₀, S*, D, τ, Q, V_total, N_capacity, N_total. See `docs/SCP_Liquid_Route_Math.md` for full derivation.

`design_gas_fermentation_reactor(mu_max, Yxs, S_f, epsilon, D_margin, adjusted_MT_yr)` → dict
: Same 9-step chain for gas fermentation. S_f (dissolved H₂ feed, fixed by Henry's law) is given, and X* is solved forward from it.

`compute_O2_CO2_H2O_coefficients(substrate_formula, biomass_formula, Yxs)` → dict
: Roels' degree-of-reduction method. Computes O₂, CO₂, NH₃, and H₂O stoichiometric coefficients per mol substrate. Used by liquid routes only.

`build_growth_reaction(substrate_id, substrate_formula, Yxs, epsilon, nutrient_coeff)` → bst.Reaction
: Assembles the mass-basis growth reaction for ExtentBasedBioreactor (liquid routes).

`build_autotrophic_growth_reaction(epsilon, nutrient_coeff)` → bst.Reaction
: Mass-basis growth reaction for the gas fermentation route using literature molar coefficients directly (Roels' method does not apply to lithoautotrophic H₂/CO₂ growth).

**Module-level constants:** `GAS_FERM_N_H2 = 21.36`, `GAS_FERM_N_O2 = 6.21`, `GAS_FERM_N_CO2 = 4.09`, `GAS_FERM_N_NH3 = 0.76`, `GAS_FERM_N_H2O = 18.70` (mol per mol biomass, Framework §9.5a).

---

#### `common/reactors.py`

Two BioSTEAM unit subclasses. Gas fermentation uses `PerfusionBioreactor` (in `perfusion_bioreactor/`), not these classes.

**`ExtentBasedBioreactor(bst.AeratedBioreactor)`**
: Continuous chemostat for liquid-substrate routes. Sets τ = 1/(D_margin × μmax) at construction. Conversion is encoded directly in the `bst.Reaction` object (X=ε) — no Monod solve. `_design()` adds the N+1 redundancy vessel by incrementing `self.parallel['self']` after BioSTEAM's auto-solve. Includes a VLE numerical fix for NH₃ and Nutrients negative vapor flows.

**`SeedBioreactor(bst.AeratedBioreactor)`**
: Periodic-batch seed vessel modeled in steady-state. τ is set so that BioSTEAM computes the correct batch working volume per stage. No N+1 redundancy; `N_seed_trains` overrides `parallel['self']` to account for concurrent restart events.

---

#### `common/nutrients.py`

Derives all nutrients properties from the raw recipe dict. Nothing is hardcoded.

**`build_nutrients_properties(concentrations, prices, achieved_titer)`** → `(composite_price, coefficient, mass_fractions)`
: Computes:
- `composite_price` ($/kg) — mass-weighted average of component prices
- `coefficient` (g Nutrients / g biomass) — total recipe g/L ÷ titer g/L at which recipe was reported
- `mass_fractions` (dict) — component mass fractions, passed to `export.py` to unlump the Nutrients stream

---

#### `common/seed_train.py`

Builds the 3-stage seed train BioSTEAM subsystem. Called by each route model builder after `design_reactor()`.

**`build_seed_train(...)`** → `(units, waste_streams)`
: Topology: ST201/ST202/ST203 (storage tanks) → SM101 (mix tank) → SHX101 (sterilize to 134 °C) → SHX102 (cool to 30 °C) → SSP101/SSP102 (flow splitters) → SR101/SR102/SR103 (seed bioreactors, stages 1–3).

Stage working volumes: SR101 = V_work_prod × 0.05³ (~34 L), SR102 = V_work_prod × 0.05² (~650 L), SR103 = V_work_prod × 0.05¹ (~13 m³). The effective τ_seed makes BioSTEAM compute these volumes exactly.

Returns 11 units and 3 waste streams (SR effluents → WWT).

**`seed_train_operating_hours(N_total)`** → float
: Total annual seed-train hours = N_total × 672 h/yr (2 restarts × 336 h each).

---

#### `common/economics.py`

**`SCPTEA(bst.TEA)`**
: BioSTEAM TEA subclass shared by all four routes. Overrides only `_FCI()` and `_FOC()`; inherits `_DPI` and `_TDC` from `bst.TEA`. Fixed operating costs are independently sourced (property tax, insurance, maintenance, administration, labor) — not collapsed to a single overhead factor. Startup ramp-up and project debt financing are zeroed (ConventionalEthanolTEA convention).

`_FOC()` also picks up `annual_om_usd` from `UltrafiltrationSterilizer` units (gas fermentation only).

**`build_tea(system, economics)`** → SCPTEA
: Factory — one call, same EconomicBasis, different System per route.

**`configure_utility_prices(economics)`**
: Sets BioSTEAM's global utility prices and CEPCI before `simulate()`. Must be called by the model builder before `system.simulate()`, because BioSTEAM caches unit purchase costs during simulation using whatever CEPCI is current at that moment.

---

#### `common/wastewater.py`

**`build_wastewater_treatment(wastewater_streams, economics, recycle_water)`** → list[bst.Unit]
: Builds three units:
- **WWT101** (`bst.Mixer`): combines all wastewater streams
- **WWT102** (`bst.Splitter`): 99% organic removal; sludge priced at −$0.33/kg (WWT operating cost)
- **RCY101** (`bst.Splitter`): 75% treated water recycled to process feed, 25% discharged

The caller must pre-create the `recycle_water` stream and wire it into the upstream feed mixer before calling this function. RCY101 sets it as its outlet, closing the recycle loop.

---

#### `common/sterilization.py`

**`UltrafiltrationSterilizer(bst.Unit)`**
: Gas fermentation route only. Media sterilization by ultrafiltration (replacing autoclave/heat sterilization). Pass-through at TEA chemical level. Capital and O&M from Guo et al. (2014) Table 1 power-law correlations, CEPCI-escalated. Numbered up at Q_max = 378,500 m³/d. Annual O&M stored in `self.annual_om_usd`, picked up by `SCPTEA._FOC()`.

---

#### `common/operating_hours.py`

Derives effective plant operating hours from first principles.

**Two downtime sources:**
- Plant-wide turnaround: 336 h/yr (2 weeks), all lines simultaneously
- Contamination restarts: 672 h/yr per line (2 restarts × 336 h each), staggered

**`effective_operating_hours()`** → 7,752 h/yr (8,760 − 336 − 672 = 88.5% uptime)

Used by `common/kinetics.py` (throughput sizing Q) and `common/economics.py` (operating_days argument to SCPTEA).

---

#### `common/export.py`

Produces all file outputs for a single route.

**`export_results(system, tea, route, nutrients_mass_fractions)`** → Path
: 7-sheet Excel workbook at `outputs/{route}_results.xlsx`:

| Sheet | Contents |
|-------|----------|
| Executive Summary | MSP, annual production, FCI, WC, TCI, FOC, VOC, depreciation (in $/yr and $/kg SCP) |
| All Streams | One row per named stream; kg/h and kg/kg SCP per chemical; Nutrients unlumped to individual salts |
| Equipment | Unit ID, type, N parallel, material, purchase/installed cost, BM factor, heat duty, power, design parameters |
| Mass Balance | Component-level Input / Output / Balance / Closure %; air streams from AeratedBioreactors added explicitly |
| TEA Parameters | All EconomicBasis fields |
| Capital Costs | FCI, Working Capital, TCI |
| Operating Costs | FOC block then VOC block; feeds unlumped for Nutrients |

**`export_unit_details_xlsx(system, route, nutrients_mass_fractions)`** → Path
: Per-unit workbook: one sheet per unit, showing `unit.results()` table followed by full stream composition tables (IN and OUT) with kg/h, mass fraction, kg/d, g/L.

**`export_unit_details(system, route)`** → Path
: Text version of unit details using BioSTEAM's native `unit.results()` output.

**`export_pfd(system, route)`** → dict
: PNG and HTML process flow diagrams via BioSTEAM's graphviz backend. Requires Graphviz executables on PATH; degrades gracefully with a warning if unavailable.

**`export_cross_route_comparison(results)`** → Path
: Cross-route workbook at `outputs/cross_route_comparison.xlsx` with 3 sheets: Summary (transposed metrics), Capital by Unit, Operating Costs by Route.

---

#### `common/lca_config.py`

Configuration-only module (no computation). Three structures drive the LCA inventory export:

**`NAICS_CATEGORIES`** — ordered list of six `(name, code)` tuples defining the Capital Goods rows (Heavy Gauge Metal Tanks through Air Conditioning/Refrigeration/Heating).

**`COST_KEY_TO_NAICS_ROW`** — maps every BioSTEAM `purchase_costs` key to a NAICS row index (0–5). Allocation is at the individual cost-item level, not the unit level, so multi-item equipment (bioreactors, seed bioreactors) correctly splits vessel costs from agitator, compressor, and heat-exchanger costs. Any key not in this dict raises `KeyError` at runtime.

**`ELEMENTARY_FLOWS`** — maps short keys to verbatim elementary flow strings for the openLCA foreground model.

**`OP_FLOW_SPECS`** — dict keyed by route name; each value is a list of row-spec dicts. Each spec declares `section` (`'ins'`/`'outs'`), `material` (display label), `ef_key`, `units`, `scope` (contributing unit/stream IDs for Col B), and `accessor` (tuple describing how to read the value from BioSTEAM). Liquid routes share specs generated by `_liquid_route_specs()`; gas fermentation is defined explicitly.

---

#### `common/lca_export.py`

Generates `lca/{RouteTitle}_InventoryAssessment.xlsx` for one route. All values are computed directly from the simulated BioSTEAM system — no hardcoded numbers, no external links.

**`export_lca_inventory(system, route, economics)`** → Path
: Public entry point called by `run_models.py` after `system.simulate()`. Computes Capital Goods (six NAICS rows in 2012 USD/kg SCP) and Operational Flows (28 or 30 rows in per-hour units), then writes a two-sheet openpyxl workbook.

Capital Goods computation: sums `purchase_costs` via `COST_KEY_TO_NAICS_ROW`, deflates 2025→2012 USD using `CEPCI_LCA_BASE / economics.CEPCI`, normalizes by `plant_life_yr × annual_production_kg`.

Operational Flows computation: loops `OP_FLOW_SPECS[route]`, evaluates each accessor (dispatched by type: `feed_stream`, `unit_in_sum`, `cost_sum`, `power_sum`, `h2o_feed_sum`, `utility_sum`, `air_sum`, `wwt_cost`, `discharge`, `gas_out_sum`, `dryer_vapor`, `discharge_unlump`), applies unit conversion (kW→MWh, kmol→kg or m³, current USD→2012 USD).

See `lca/README.md` for full details on sheet structure, unit conventions, and how to extend for new routes.

---

### `models/` — route model builders

Each module exposes one public function `build_{route}_system(params, economics)` → `(bst.System, nutrients_mass_fractions)`. The function constructs and wires all BioSTEAM units but does not simulate, build a TEA, or export — that is `run_models.py`'s job.

---

#### `models/fructose_model.py`

**Feedstock:** Fructose (C₆H₁₂O₆), $1.16/kg

**Process topology:**
```
ST101 (fructose storage) ─┐
ST102 (nutrients storage) ─┤
ST103 (NH3 storage)       ─┤
ST104 (water storage)     ─┴→ M101 (MixTank, τ=1h)
                               → HX101 (sterilize, 134°C)
                               → HX102 (cool, 30°C)
                               → R101 (ExtentBasedBioreactor, N+1)
                               → C101 (SolidsCentrifuge, 95% recovery)
                               → D101 (SprayDryer, 5% moisture)
                               → ST105 (product storage)
                               [Seed train: ST201→SR103, see common/seed_train.py]
                               [WWT: WWT101→WWT102→RCY101, see common/wastewater.py]
```

**Key design parameters (base case):** μmax = 0.22 h⁻¹, Yxs = 0.32 g/g, max titer = 32 g/L, ε = 0.90, D_margin = 0.80, target titer fraction = 0.75 → X* = 24 g/L, ~6 production vessels.

---

#### `models/acetate_model.py`

**Feedstock:** Acetic acid (C₂H₄O₂), $0.65/kg

**Process topology:** Same as fructose model. Feedstock ID changes to `AceticAcid`.

**Key design parameters (base case):** μmax = 0.15 h⁻¹, Yxs = 0.45 g/g, max titer = 15 g/L, ε = 0.90, D_margin = 0.80 → X* = 11.25 g/L, ~35–40 production vessels (slower μmax → longer τ → larger N).

---

#### `models/formate_model.py`

**Feedstock:** Formic acid (CH₂O₂), $0.35/kg

**Process topology:** Same as fructose model. Feedstock ID changes to `FormicAcid`.

**Key design parameters (base case):** μmax = 0.18 h⁻¹, Yxs = 0.06 g/g, max titer = 10.5 g/L, ε = 0.90, D_margin = 0.80 → X* = 7.875 g/L. Very low Yxs drives high substrate consumption and large feedstock cost contribution.

---

#### `models/gas_fermentation_model.py`

**Feedstock:** H₂ (electron donor and energy source), $4.83/kg; CO₂ (carbon source, typically free from industrial waste gas).

**Process topology** (structurally different from liquid routes):
```
H2 feed → DC101 (DropletColumnContactor, pre-saturation at 4 atm)
CO2 feed ─┘                  ↓
                     pre-saturated liquid → R101 (PerfusionBioreactor)
                              → C101 (SolidsCentrifuge)
                              → D101 (SprayDryer)
                              → ST101 (product storage)
[Gas sterilization: UFS101 (UltrafiltrationSterilizer)]
[Seed train: gas-adapted — N_seed_trains ≈ 9 (492 vessels need concurrent seeding)]
[WWT: same topology as liquid routes]
```

**Key differences from liquid routes:**
- Feed is gaseous H₂/CO₂, dissolved into the liquid phase by a droplet column contactor
- Titer is set by dissolved H₂ concentration (Henry's law, S_f = 0.0051 g/L at 4 atm) × Yxs × ε — not by a titer target
- Very high vessel count (~492) due to low titer and slow growth; dominates capital cost
- UltrafiltrationSterilizer replaces heat sterilization (avoid H₂ in heat exchangers)
- N_seed_trains ≈ 9 (9 concurrent seed trains needed to cover 492 lines × 2 restarts/yr)

---

### `perfusion_bioreactor/` — gas fermentation custom units

#### `perfusion_bioreactor/droplet_column.py`

**`DropletColumnContactor(bst.Unit)`**
: Dissolves H₂ and CO₂ into the liquid medium before the bioreactor. Sets dissolved gas concentration based on Henry's law at the operating pressure. Sized from the framework's gas/liquid contacting parameters (Framework §4, §4a).

#### `perfusion_bioreactor/unitwithauxiliary.py`

**`PerfusionBioreactor(bst.Unit)`**
: Custom BioSTEAM unit for the gas fermentation perfusion reactor. Handles:
- H₂/CO₂ mass balance using literature molar stoichiometry (GAS_FERM_N_* constants from `common/kinetics.py`)
- Vessel count (N) stored in `design_results['Number of parallel reactors']`; `parallel['self']` stays at 1 (BioSTEAM cost scales through `design_results` for this unit)
- N+1 redundancy included in N
- UF membrane sterilization O&M passed through to `SCPTEA._FOC()` via `annual_om_usd`

For full governing equations, see `docs/SCP_Perfusion_Bioreactor_Math.md`.

---

## Outputs directory

All generated files land in `outputs/`. The directory is created automatically on first run.

| File pattern | Generated by | Contents |
|---|---|---|
| `outputs/{route}_results.xlsx` | `run_models.py` | 7-sheet TEA workbook per route |
| `outputs/{route}_unit_details.xlsx` | `run_models.py` | Per-unit stream tables |
| `outputs/{route}_unit_details.txt` | `run_models.py` | Per-unit design results (text) |
| `outputs/{route}_pfd.png / .html` | `run_models.py` | Process flow diagram (requires Graphviz) |
| `outputs/cross_route_comparison.xlsx` | `run_models.py` | Summary, capital, OPEX across routes |
| `lca/{RouteTitle}_InventoryAssessment.xlsx` | `run_models.py` | LCA inventory — Capital Goods (NAICS, 2012 USD/kg SCP) + Operational Flows (per-hour rates) |
| `outputs/sensitivity_results.xlsx` | `sensitivity_analysis.py` | OAT Results + Tornado Summary + Base Case Design |
| `outputs/sensitivity_tornado_{route}.png` | `sensitivity_analysis.py` | 4 per-route tornado charts |
| `cost_breakdown.png / .xlsx` | `additional_analyses.py` | Stacked-bar MSP decomposition |
| `scale_curve.png / .xlsx` | `additional_analyses.py` | MSP vs. production scale (5k–100k MT/yr) |
| `cross_route_tornado.png` | `additional_analyses.py` | Cross-route OAT swing comparison |
| `2d_sa_{route}.png` | `additional_analyses.py` | 2D sensitivity heatmaps (4 routes) |
| `2d_sa_results.xlsx` | `additional_analyses.py` | 2D SA MSP grids (one sheet per route) |

---

## Dependencies

**Python:** ≥3.10

```
biosteam        # process simulation and TEA
thermosteam     # thermodynamic property calculations (bundled with biosteam)
pandas          # tabular output and Excel export
openpyxl        # Excel writer backend
matplotlib      # charts and heatmaps
graphviz        # PFD export (optional; degrades gracefully if absent)
```

Install with:
```bash
pip install biosteam pandas openpyxl matplotlib
pip install -e .   # installs common/, models/, perfusion_bioreactor/ as importable packages
# Graphviz: https://graphviz.org/download/ (system package, not pip)
```

---

## Design principles

- **Compute, don't assert.** Any quantity derivable from other inputs is computed live (nutrient composite price, stoichiometric coefficients, vessel counts). Nothing derivable is hardcoded.
- **One shared implementation per concern.** All logic shared across routes lives once in `common/` and is imported. Route model files wire route-specific parameters into shared functions — they do not re-implement the same logic.
- **Build/run separation.** `models/*.py` build and return systems. `run_models.py` simulates, builds TEAs, and exports. These responsibilities are not mixed.
- **Cite reasoning, not just results.** Code comments point to the Framework section that justifies each design decision.
- **No invented values.** Every numeric parameter traces to a literature source or an explicit engineering judgment recorded in the Framework.
