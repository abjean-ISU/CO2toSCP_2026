# SCP Implementation Spec

*Code-ready reference. No rationale — see `SCP_Project_Framework.md` for the "why" behind any of
this. Perfusion bioreactor equations are in `SCP_Perfusion_Bioreactor_Math.md`, not repeated here.*

## File layout

```
scp_project/
├── common/{chemicals, economics, operating_hours, kinetics, reactors,
│           nutrients, seed_train, export, parameters,
│           lca_config, lca_export}.py
├── perfusion_bioreactor/unitwithauxiliary.py
├── models/{fructose,acetate,formate,gas_fermentation}_model.py   # build_X_system() only, no execution
├── lca/{Fructose,Acetate,Formate,GasFerment}_InventoryAssessment.xlsx  # auto-generated LCI workbooks
├── run_models.py            # driver: build → simulate → TEA → export → LCA inventory, all 4 routes
└── sensitivity_analysis.py  # OAT sweep, reuses builders
```

## `common/economics.py`

```
class SCPTEA(bst.TEA):
    # Modeled directly on biorefineries/tea/conventional_ethanol_tea.py's ConventionalEthanolTEA
    # (Huang, Long & Singh 2016) -- real, published, generic structure, not ethanol-specific.
    # _DPI, _TDC: bst.TEA defaults. _FCI: multiplies TDC by contingency_fee_factor.
    # lang_factor=None passed to super().__init__() → system uses Σ(u.installed_cost).
    def _FCI(self, TDC):
        return self.contingency_fee_factor * TDC  # Turton (7th ed.) Table 16.1; Framework §9.4
    def _FOC(self, FCI):
        return (FCI*(self.property_tax + self.property_insurance
                     + self.maintenance + self.administration)
                + self.labor_cost*(1 + self.fringe_benefits + self.supplies))
        # 6 independently-sourced categories (Section 9), not one blended number

def build_tea(system: bst.System, economics: EconomicBasis) -> SCPTEA:
    # one factory, called identically by all 4 routes -- same EconomicBasis, different System
    return SCPTEA(system=system, IRR=economics.IRR, duration=economics.duration,
                  depreciation=economics.depreciation, income_tax=economics.income_tax,
                  operating_days=effective_operating_hours()/24, lang_factor=None,
                  labor_cost=economics.labor_cost, fringe_benefits=economics.fringe_benefits,
                  supplies=economics.supplies, property_tax=economics.property_tax,
                  property_insurance=economics.property_insurance,
                  maintenance=economics.maintenance, administration=economics.administration, ...)

def solve_msp(tea: SCPTEA, product_stream: bst.Stream) -> float:
    # tea.solve_price() performs a single analytical solve — not iterative price search.
    # price2cost = Σ(F_mass × op_hours / (1+IRR)^t); MSP = solve_sales() / price2cost.
    # Product stream price remains 0 after this call; stream.price is NOT set to MSP.
    return tea.solve_price(product_stream)
```
Wastewater treatment: `bst.create_conventional_wastewater_treatment_system()` (real BioSTEAM
subsystem, Humbird et al./NREL) — reused per route, not built from scratch. `autopopulate` grabs
unpriced/non-combustible product streams automatically. Biogas output: flared, not captured (cheap
to revisit later since the stream already exists).

## `common/parameters.py`

Single source of truth. One record per route, fields below. Values live in
`SCP_Project_Framework.md` Section 9 — this module reads from there (or a structured file derived
from it), never hardcodes locally.

```
RouteParams:
    mu_max: float          # h^-1
    Yxs: float              # g biomass / g substrate
    max_titer: float        # g/L, literature ceiling
    epsilon: float           # conversion extent, 0-1
    D_margin: float          # fraction of mu_max, 0.8 (finalized, Section 9.2 -- NOT 0.3-0.5)
    feedstock_price: float   # $/kg
```
Plus shared (non-per-route) records: `NutrientsRecipe`, `EconomicBasis`
(dollar-year/CEPCI/IRR/tax/plant-life/depreciation), `theta_O2`, `restart_frequency_per_line`.

## `common/operating_hours.py`

```
CALENDAR_HOURS = 8760
PLANT_TURNAROUND_H = 336            # 2 wk/yr, all lines simultaneously
RESTARTS_PER_YEAR = 2                # finalized (Cauldron-based, 6-month campaigns), NOT 1
CONTAMINATION_RESTART_H = RESTARTS_PER_YEAR * 336  # = 672 h/yr, per line, independent/staggered

def effective_operating_hours() -> float:
    return CALENDAR_HOURS - PLANT_TURNAROUND_H - CONTAMINATION_RESTART_H  # = 7752
```

## `common/kinetics.py`

**Downstream recovery chain (backward pass — run first):**
```
def required_fermenter_output(target_final_product_MT_yr, downstream_efficiencies: list[float]) -> float:
    result = target_final_product_MT_yr
    for eta in downstream_efficiencies:
        result /= eta
    return result   # feeds forward chain step 6 below, NOT the raw target
```

**Reactor design chain (forward pass):**
```
def design_reactor(mu_max, Yxs, max_titer, epsilon, D_margin,
                    target_titer_fraction, adjusted_fermenter_output_MT_yr,
                    V_max=355.0,        # m3, AeratedBioreactor default
                    S_star_max=None):   # g/L inhibition ceiling — Framework §9.1; None = no constraint
    X_star_titer = target_titer_fraction * max_titer      # step 2 — titer-forward
    if S_star_max is not None:                             # step 2 — inhibition branch (Framework §5)
        X_star = min(X_star_titer,
                     Yxs * epsilon * S_star_max / (1 - epsilon))
    else:
        X_star = X_star_titer
    S0 = X_star / (Yxs * epsilon)                         # step 3
    S_star = S0 * (1 - epsilon)                            # step 4, -> wastewater load
    D = D_margin * mu_max                                  # step 5
    Q = (adjusted_fermenter_output_MT_yr * 1e6
         / effective_operating_hours()) / X_star            # step 6, g/h -> consistent units
    V_total = Q / D                                          # step 7
    tau = 1 / D
    N_capacity = ceil(V_total / V_max)                        # step 8 -- BioSTEAM auto-solves this
                                                                 #   in _design() if self.N left None;
                                                                 #   replicate here only if needed
                                                                 #   pre-simulation for seed train calc
    N_total = N_capacity + 1                                    # step 9, N+1 redundancy
    return dict(X_star=X_star, S0=S0, S_star=S_star, D=D, tau=tau,
                Q=Q, V_total=V_total, N_capacity=N_capacity, N_total=N_total,
                inhibition_constrained=(X_star < X_star_titer))
```
**Gas fermentation variant (S_f fixed, solve forward instead of backward):**
```
def design_gas_fermentation_reactor(mu_max, Yxs, S_f, epsilon, D_margin, ...):
    X_star = Yxs * S_f * epsilon     # <-- only difference from liquid routes: X* is an output,
                                      #     not S0; S_f is fixed externally (Henry's law), not chosen
    # steps 5-9 otherwise identical to design_reactor() above
```

**Oxygen/CO2/H2O stoichiometry (not a sourced parameter — computed):**
```
def compute_O2_CO2_H2O_coefficients(substrate_formula, biomass_formula, Yxs_Cmol):
    # degree of reduction, per C-mol, Roels' method: gamma = 4 + h - 2*o - 3*n
    gamma_S = degree_of_reduction(substrate_formula)
    gamma_X = degree_of_reduction(biomass_formula)
    O2_coeff = (gamma_S - Yxs_Cmol * gamma_X) / 4     # mol O2 / C-mol substrate
    # CO2, H2O coefficients then close via standard C and O atom balances
    return O2_coeff, CO2_coeff, H2O_coeff
    # Called once per route at build time; automatically correct if ever
    # epsilon/Yxs/substrate change upstream -- not re-sourced, re-derived.
```

## `common/reactors.py`

```
class ExtentBasedBioreactor(bst.AeratedBioreactor):
    """
    _run() override:
        conversion = epsilon          # NOT solved via Monod/Haldane -- asserted per Section 5
        D = D_margin * mu_max
        # feeds `reactions=` Reaction/elemental-balance object (Yxs sets stoichiometric coeff)
        # theta_O2 set explicitly, not left at BioSTEAM default (0.5) without checking Section 9
    _design():
        # let AbstractStirredTankReactor._design() auto-solve N_capacity from V_max
        # THEN override: self.N = N_capacity + 1   (redundancy, Section 5 step 9)
    """
```
One class. Fructose/acetate/formate instantiate it with different `RouteParams`. Gas fermentation
does NOT use this class — see `perfusion_bioreactor/unitwithauxiliary.py` +
`SCP_Perfusion_Bioreactor_Math.md`, with corrections per that doc's Section 13 (mu_max/epsilon no
longer free parameters — set via the same `design_gas_fermentation_reactor()` above; hardcoded
`350*24` operating-hours replaced with `effective_operating_hours()`).

## `common/nutrients.py`

```
def build_nutrients_chemical(recipe: dict[str, float],       # {component_name: g/L}
                              component_prices: dict[str, float],  # {component_name: $/kg}
                              achieved_titer: float) -> bst.Chemical:
    mass_fractions = normalize(recipe)                    # sum to 1
    ref_stream = build_reference_stream(recipe)             # real bst.Chemical per component
    MW = ref_stream.MW                                        # BioSTEAM computes automatically
    composite_price = sum(mass_fractions[c] * component_prices[c] for c in recipe)  # mass-weighted
    coefficient = sum(recipe.values()) / achieved_titer          # g Nutrients / g biomass
    Nutrients = bst.Chemical('Nutrients', MW=MW, phase='l')
    Nutrients.price = composite_price
    return Nutrients, coefficient, mass_fractions   # mass_fractions reused by export.py
```
Reaction term: `... + coefficient·Nutrients → ... + biomass` (mass basis, `basis='wt'`).

## `common/seed_train.py`

```
def seed_train_operating_hours(N_total: int) -> float:
    return N_total * CONTAMINATION_RESTART_H
    # CONTAMINATION_RESTART_H now = 672 (2 restarts/yr x 336h), already matches
    # framework's "N_total x 2 x 336 h/yr" formula -- no separate x2 needed here.
    # MUST run after common.kinetics.design_reactor() produces N_total -- one-directional dependency
```

## `common/export.py`

### `export_results(system, tea, route, nutrients_mass_fractions)`

Writes `outputs/{route}_results.xlsx` — 9-sheet workbook, identical schema across all four routes.

| Sheet | Contents |
|-------|----------|
| Executive Summary | MSP, annual production, FCI, TCI, FOC, VOC |
| All Streams | Flat table: one row per named stream; paired kg/h and kg/kg SCP columns; Nutrients unlumped to individual salt rows |
| Equipment | ID, type, N (parallel), material, purchase cost, BM factor, installed cost, heat duty, power, all `design_results` keys |
| Mass Balance | Component-level Input / Output / Balance / Closure (%) |
| TEA Parameters | All `EconomicBasis` fields used in the analysis |
| Capital Costs | FCI, working capital, TCI |
| Operating Costs | FOC block (startrow=0) then 3 blank rows then VOC block |
| Cash Flow | Year-by-year from `tea.get_cashflow_table()`; product stream price temporarily set to MSP so NPV → 0 |
| Stoichiometry | Production reaction stoichiometric coefficients in mass basis (g / g substrate consumed) with g / kg SCP column; header block (Substrate, Basis, X) then coefficient table |

Notes:
- Nutrients unlumping: `stream.imass['Nutrients'] × nutrients_mass_fractions[salt]` — same fractions computed once in `common/nutrients.py`, consumed by both TEA costing and this export.
- Equipment N: reads `design_results['Number of parallel reactors']` first (PerfusionBioreactor), falls back to `unit.parallel['self']` (ExtentBasedBioreactor).
- Stoichiometry: liquid routes extract from `ExtentBasedBioreactor.reactions` (bst.Reaction, basis=wt); gas fermentation divides PerfusionBioreactor `design_results` rates by H2 consumed (g/h).

### `print_stoichiometry(system, route)`

Prints the production reaction stoichiometry to stdout. Same extraction logic as the Stoichiometry sheet. Called by `run_models.py` inside the verbose block after MSP/FCI/production print.

## `common/lca_config.py`

Configuration-only; no computation. Defines:

```
_CEPCI_LCA_BASE: float = 584.6   # 2012 CEPCI — LCA dollar-year basis

NAICS_CATEGORIES: list[tuple[str, str]]
    # six (name, code) tuples — Capital Goods sheet rows 0-5

COST_KEY_TO_NAICS_ROW: dict[str, int]
    # maps every purchase_costs key -> NAICS row index (0-5)
    # allocation at individual cost-item level (not unit level)
    # any unmapped key raises KeyError at runtime

ELEMENTARY_FLOWS: dict[str, str]
    # short key -> verbatim elementary flow string for openLCA

OP_FLOW_SPECS: dict[str, list[dict]]
    # route -> list of row-spec dicts, each with:
    #   section  : 'ins' or 'outs'
    #   material : Col A display label
    #   ef_key   : key into ELEMENTARY_FLOWS
    #   units    : Col D unit string
    #   scope    : [unit_id or stream_id, ...] — written to Col B
    #   accessor : (type, *args) — describes how to read from BioSTEAM
    # Liquid routes: _liquid_route_specs(substrate_stream_id, component, ef_key)
    # Gas fermentation: explicit list (different topology)
```

Accessor types and return values (before unit conversion):

| Type | Args | Returns |
|------|------|---------|
| `feed_stream` | `stream_id, component` | `stream.imass[component]` kg/hr |
| `unit_in_sum` | `[(uid, in_idx, comp), ...]` | sum of `unit.ins[in_idx].imass[comp]` kg/hr |
| `cost_sum` | `[(uid, in_idx, comp), ...]`, `price` | sum(mass × price) $/hr; `'<composite_price>'` sentinel substituted at runtime |
| `power_sum` | `[uid, ...]` | sum of `unit.power_utility.consumption` kW |
| `h2o_feed_sum` | `[stream_id, ...]` | sum of `stream.imass['H2O']` kg/hr |
| `utility_sum` | `[uid, ...]`, `agent_id` | sum of `hu.flow` kmol/hr for matching agent |
| `air_sum` | `[uid, ...]`, `component` | sum of `unit.air.imass[component]` kg/hr (skips units without `.air`) |
| `wwt_cost` | `wwt_uid` | non-H₂O mass in WWT inlet × `economics.wwt_organic_removal_cost` $/hr |
| `discharge` | `component` | `RCY101.outs[1].imass[component]` kg/hr |
| `gas_out_sum` | `[uid, ...]`, `component` | sum of `unit.outs[0].imass[component]` kg/hr |
| `dryer_vapor` | `component` | `D101.outs[0].imass[component]` kg/hr |
| `discharge_unlump` | `nutrient_key` | `RCY101.outs[1].imass['Nutrients']` × `nutrients_mass_fracs[nutrient_key]` kg/hr |

## `common/lca_export.py`

```
def export_lca_inventory(
    system: bst.System,
    route: str,
    economics: EconomicBasis,
) -> pathlib.Path:
    # Writes lca/{RouteTitle}_InventoryAssessment.xlsx
    # Sheet 1: Capital Goods — 6 NAICS rows; cols: NAICS Category, NAICS Code,
    #           Equipment included, 2025 USD (total), 2012 USD / kg SCP
    # Sheet 2: Operational Flows — 28 rows (liquid) or 33 rows (gas ferm); cols:
    #           Material, Scope, Elementary Flow, Units, Value (per hr), Value / kg SCP
    # composite_price computed internally from NUTRIENTS_RECIPE via build_nutrients_properties()
    # cepci_ratio = _CEPCI_LCA_BASE / economics.CEPCI (584.6 / 809.3 ≈ 0.722)
    # scp_kgh = CNecatorBiomass flow from max-biomass system.products stream (kg CDW/hr)
    # capital goods normaliser = plant_life_yr × scp_kgh × effective_operating_hours()
```

## `models/{route}_model.py` template

```
def build_{route}_system(params: RouteParams, economics: EconomicBasis) -> bst.System:
    # construct flowsheet using common.reactors / common.nutrients / common.kinetics
    # NO .simulate(), NO TEA build, NO export call -- builder only
    return system
```

## `run_models.py`

```
for route in ROUTES:
    params = parameters.get(route)
    system = builders[route](params, economics)
    system.simulate()
    tea = economics.build_tea(system)             # shared settings, all 4 routes
    export.print_stoichiometry(system, route)     # prints to stdout (verbose block)
    export.export_results(system, tea, route, nutrients_mass_fractions)
    # -> outputs/{route}_results.xlsx (9-sheet workbook, includes Stoichiometry sheet)
    lca_export.export_lca_inventory(system, route, ECONOMICS)
    # -> lca/{RouteTitle}_InventoryAssessment.xlsx (Section 8 LCI deliverable)
```

## `sensitivity_analysis.py`

```
for param_name, base_value, sa_range in registry:     # Section 9 table
    for perturbed_value in sweep(base_value, sa_range):
        system = builders[route](params_with(param_name=perturbed_value), economics)
        system.simulate()
        record(param_name, perturbed_value, tea.MSP)
# rank by |delta MSP| -> tornado diagram, per route, same convention across routes
```

## Known corrections required to the April `unitwithauxiliary.py` before reuse

(Full detail: `SCP_Perfusion_Bioreactor_Math.md` Section 13)
1. `mu` → set via `design_gas_fermentation_reactor()`, not a free constructor argument.
2. `conversion=0.99` default → explicit `epsilon`, sourced/justified per Section 9, not a silent default.
3. Hardcoded `350*24` → `effective_operating_hours()`.
4. `Y_mol`/`m_s_mol` → confirm real citation exists; audit before reuse.
