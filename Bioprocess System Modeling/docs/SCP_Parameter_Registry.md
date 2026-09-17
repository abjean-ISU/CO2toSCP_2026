# SCP Parameter Source Registry

**Document scope:** Every numeric parameter used in the model, with value, units, literature source, and Framework §9 reference.
**Last updated:** 2026-08-10
**Implementation:** `common/parameters.py`, `common/operating_hours.py`
**Authoritative source:** `docs/SCP_Project_Framework.md §9`

This document is a standalone reference that consolidates all numeric parameters in one place. It is generated from the actual code values in `common/parameters.py` — if there is a discrepancy between this table and the code, the code is authoritative.

---

## Part 1 — Per-route kinetic and design parameters

Stored as `RouteParams` dataclasses in `_ROUTE_PARAMS` in `common/parameters.py`. Accessed via `get(route)`.

### 1.1 Maximum specific growth rate (μmax)

| Route | Value (h⁻¹) | Literature source |
|-------|------------|-----------------|
| Fructose | 0.22 | Boy et al. (2021) AMB Express |
| Acetate | 0.15 | Garcia-Gonzalez & de Wever (2018) Appl. Sci. |
| Formate | 0.18 | Grunwald et al. (2015) Microb. Biotechnol. |
| Gas fermentation | 0.12 | Yu & Lu (2019) Biochem. Eng. J. |

### 1.2 Biomass yield on substrate (Yxs)

| Route | Value (g biomass/g substrate) | Literature source |
|-------|------------------------------|-----------------|
| Fructose | 0.32 | Boy et al. (2021) AMB Express |
| Acetate | 0.45 | Garcia-Gonzalez & de Wever (2018) Appl. Sci. |
| Formate | 0.06 | Claassens et al. (2020) Metab. Eng. |
| Gas fermentation | 2.26 | Derived from molar stoichiometry (§9.5a): MW_biomass / (n_H2 × MW_H2) = 97.20 / (21.36 × 2.016) = 2.26; supersedes Yu & Lu (2019) value of 1.56 |

Note on gas fermentation Yxs: this value is derived, not directly measured, to ensure consistency with the molar equation used in PerfusionBioreactor. The derivation is: one mol biomass requires 21.36 mol H₂; g CDW per g H₂ = MW_biomass / (21.36 × MW_H₂) = 97.20 / 43.06 = 2.26.

### 1.3 Literature ceiling titer (X_max)

| Route | Value (g/L) | Literature source |
|-------|------------|-----------------|
| Fructose | 32.0 | Nygaard et al. (2021) Heliyon |
| Acetate | 15.0 | Garcia-Gonzalez & de Wever (2018) Appl. Sci. |
| Formate | 10.5 | Grunwald et al. (2015) Microb. Biotechnol. |
| Gas fermentation | 7.0 | Yu & Lu (2019) Biochem. Eng. J. — not used by perfusion model (see note) |

Note on gas fermentation X_max: the perfusion bioreactor model does not use `target_titer_fraction × X_max` to set the operating titer. The effective titer is set by dissolved H₂ availability (Henry's law at operating pressure). The stored value is retained for registry completeness.

### 1.4 Substrate conversion extent (ε)

| Route | Value | Basis |
|-------|-------|-------|
| Fructose | 0.90 | Engineering judgment, §9.2 |
| Acetate | 0.90 | Engineering judgment, §9.2 |
| Formate | 0.90 | Engineering judgment, §9.2 |
| Gas fermentation | 0.99 | Near-complete H₂ conversion; bacteria fully convert dissolved H₂ — user decision, §9.2 |

### 1.5 Dilution rate margin (D_margin)

| Route | Value (fraction of μmax) | Basis |
|-------|------------------------|-------|
| All routes | 0.80 | Standard bioprocesstools.com recommendation — operates at 80% of washout dilution rate, §9.2 |

### 1.6 Target titer fraction

| Route | Value (fraction of X_max) | Basis |
|-------|--------------------------|-------|
| All routes | 0.75 | Engineering judgment — provides safety margin below ceiling titer, §9.2 |

Note: not used by gas fermentation (perfusion bioreactor model).

### 1.7 Feedstock price

| Route | Feedstock | Value ($/kg) | Literature source |
|-------|-----------|-------------|-----------------|
| Fructose | Fructose sugar | $1.16 | selinawamucii.com (bulk market price) |
| Acetate | Acetic acid | $0.65 | Crandall et al. (2023) Acc. Chem. Res. |
| Formate | Formic acid | $0.35 | Jouny et al. (2018) Ind. Eng. Chem. Res. |
| Gas fermentation | H₂ (PEM electrolysis) | $4.83 | Peterson et al. (2019) DOE Record — H₂ from PEM electrolysis |

---

## Part 2 — Universal module-level constants

Stored at module level in `common/parameters.py`. Shared across all routes.

### 2.1 Biological and physical process constants

| Constant | Value | Units | Basis | Framework |
|----------|-------|-------|-------|-----------|
| `THETA_O2` | 0.50 | fraction | BioSTEAM AeratedBioreactor default dissolved-O₂ setpoint; kept at default deliberately — revisit only if O₂-limitation symptoms appear | §9.2 |
| `CENTRIFUGE_RECOVERY` | 0.95 | fraction of biomass | Engineering judgment; disc-stack centrifuge on bacterial biomass | §9.2 |
| `CENTRIFUGE_CAKE_MOISTURE` | 0.75 | wt/wt | Engineering judgment; representative of scroll/disc-stack centrifuge on bacterial biomass | §9.2 |
| `SPRAY_DRYER_MOISTURE` | 0.05 | wt/wt | Industry standard for microbial SCP powder — Ugalde & Castrillo (2002) | §9.2 |
| `PRODUCTION_TARGET_MT_YR` | 25,000 | MT/yr of final SCP | Applied to final product (post-centrifuge, post-dryer); upstream steps sized backward via `required_fermenter_output()` | §9.2 |
| `WWT_ORGANIC_REMOVAL` | 0.99 | fraction removed | 99% BOD removal — Metcalf & Eddy, Wastewater Engineering 5th ed., Table 10-1; consistent with well-operated activated sludge | §9.2 |
| `WWT_WATER_RECYCLE_FRACTION` | 0.75 | fraction recycled | Fraction < 1 required for recycle-loop convergence: aerobic fermentation produces net H₂O, so 100% recycle causes unbounded accumulation; 0.75 makes the loop a contraction mapping | §9.2 |
| `WWT_SLUDGE_MOISTURE` | 0.80 | wt H₂O / wt total | Moisture fraction of dewatered sludge cake. 80 wt% H₂O (20 wt% dry solids) is characteristic of centrifuge- or belt-filter-press-dewatered sludge — Metcalf & Eddy, *Wastewater Engineering*, 5th ed., Table 22-10. Used in `_SludgeSettler._run()` to set the water-to-sludge split: H₂O_to_sludge = (0.80/0.20) × dry_sludge_mass. Also scales the sludge stream price: `sludge.price = −wwt_organic_removal_cost × (1 − WWT_SLUDGE_MOISTURE) = −$0.066/kg wet sludge`, which recovers $0.33/kg dry organic removed | §9.2 |

### 2.2 Operating schedule constants

| Constant | Value | Units | Basis | Framework |
|----------|-------|-------|-------|-----------|
| `RESTART_FREQUENCY_PER_LINE` | 2.0 | restarts/yr per production line | 6-month campaigns — Cauldron/Stansfield, AgFunderNews March 2024 (stated as margin below 8-month achieved) | §9.2 |
| `INOCULUM_RATIO` | 0.05 | fraction of next-stage working volume | Engineering judgment — user decision 2025-08-05; applied to all 3 modeled seed stages | §9.2 |
| `SEED_BATCH_DURATION_H` | 72.0 | h per 3-stage seed batch | 3 stages × 24 h/stage: each stage grows from 5% inoculum to working density; 24 h/stage provides ~7 h lag-phase margin beyond growth-time-alone (~17 h for fructose) — Doran, Bioprocess Engineering Principles, 2nd ed., §14.4 | §9.2 |

### 2.3 Equipment design constants

| Constant | Value | Units | Basis | Framework |
|----------|-------|-------|-------|-----------|
| `T_STERILIZATION_K` | 407.15 | K (134 °C) | Standard for continuous heat sterilization of liquid fermentation media — Doran (2012) §12.3; EN 285 | §9.2 |
| `STERILIZATION_HOLD_TAU_MIN` | 2.44 | min | Hold time at T_STERILIZATION_K (134 °C) for continuous sterilization. Stanbury, Whitaker & Hall (2017) *Principles of Fermentation Technology* (3rd ed.) §Sterilization. Implemented via HoldPipe (HP101 / SHP101); capital excluded (< 0.01 % FCI) | §9.2 |
| `T_FERMENTATION_K` | 303.15 | K (30 °C) | Optimal growth temperature for C. necator — Boy et al. (2021); Yu & Lu (2019) | §9.2 |
| `MIX_TANK_TAU` | 1.0 | h | Standard hold-up time for continuous-feed mixing of g/L mineral salts media — Doran, Bioprocess Engineering Principles, 2nd ed. | §9.2 |
| `STORAGE_TANK_TAU` | 168.0 | h (7 days) | 7-day buffer inventory — standard continuous-plant practice | §9.2 |
| `NH3_NUTRIENTS_EXCESS` | 0.05 | dimensionless | 5 % supplement above stoichiometric applied to both NH3 and Nutrients feeds in all four route model builders and `common/seed_train.py`. Ensures growth is never N- or mineral-limited in continuous culture; standard practice for mineral-salt media — Doran (2012) §12. NH3 VLE note: BioSTEAM routes residual NH3 to gas vent (Psat >> P at 30 °C); supplement has limited effect on liquid NH3; `_run_vent` floor in `common/reactors.py` provides the primary numerical fix. | §9.2 |

---

## Part 3 — Operating hours constants

Stored at module level in `common/operating_hours.py`.

| Constant | Value | Units | Basis | Framework |
|----------|-------|-------|-------|-----------|
| `CALENDAR_HOURS` | 8,760 | h/yr | 365 days × 24 h | §5a |
| `PLANT_TURNAROUND_H` | 336 | h/yr | 2 weeks/yr all-lines-down maintenance | §5a |
| `RESTARTS_PER_YEAR` | 2 | restarts/yr per line | 6-month campaigns — same source as RESTART_FREQUENCY_PER_LINE | §5a, §9.2 |
| `RESTART_DURATION_H` | 336 | h per restart event | 2 weeks per restart — same as turnaround duration | §5a |
| `CONTAMINATION_RESTART_H` | 672 | h/yr per line | = RESTARTS_PER_YEAR × RESTART_DURATION_H = 2 × 336 | §5a |
| **`effective_operating_hours()`** | **7,752** | **h/yr** | **= 8,760 − 336 − 672 = 88.5% uptime** | **§5a** |

---

## Part 4 — Shared economic basis

Stored as the `ECONOMICS` singleton (`EconomicBasis` dataclass) in `common/parameters.py`. Identical for all four routes.

### 4.1 Financial parameters

| Parameter | Value | Units | Literature source | Framework |
|-----------|-------|-------|------------------|-----------|
| `dollar_year` | 2025 | — | Reference year for all costs | §9.4 |
| `CEPCI` | 809.3 | — | 2025 average Chemical Engineering Plant Cost Index | §9.4 |
| `IRR` | 0.10 | fraction/yr | Internal rate of return target | §9.4 |
| `duration` | (2025, 2045) | (start, end) yr | 20-year plant life | §9.4 |
| `depreciation` | 'MACRS7' | BioSTEAM schedule | Modified Accelerated Cost Recovery System, 7-year property | §9.4 |
| `income_tax` | 0.35 | fraction | 35% combined federal + state | §9.4 |

### 4.2 Capital cost parameters

| Parameter | Value | Units | Literature source | Framework |
|-----------|-------|-------|------------------|-----------|
| `contingency_fee_factor` | 1.18 | — | Multiplier on Σ(C_P × f_BM) to reach FCI; covers contingency (15%) + contractor fees (3%). Turton et al. *Analysis, Synthesis and Design of Chemical Processes* (7th ed.) Table 16.1 | §9.4 |
| `WC_over_FCI` | 0.176 | fraction of FCI | Working capital fraction — Seider et al. | §9.4 |
| `construction_schedule` | (0.40, 0.60) | fraction of FCI per pre-startup year | Huang et al. (2016); sums to 1.0; 40% in year −2, 60% in year −1 | §9.4 |

### 4.3 Fixed operating cost parameters

| Parameter | Value | Units | Literature source | Framework |
|-----------|-------|-------|------------------|-----------|
| `labor_cost` | $3,600,000 | $/yr | All direct + fringe + supplies loaded into this single value — Turton *Analysis, Synthesis and Design of Chemical Processes* | §9.4 |
| `fringe_benefits` | 0.0 | fraction of labor | Loaded into labor_cost | §9.4 |
| `supplies` | 0.0 | fraction of labor | Loaded into labor_cost | §9.4 |
| `property_tax` | 0.01 | fraction of FCI | 1.0% FCI — Turton | §9.4 |
| `property_insurance` | 0.01 | fraction of FCI | 1.0% FCI — Turton | §9.4 |
| `maintenance` | 0.10 | fraction of FCI | 10.0% FCI — Turton | §9.4 |
| `administration` | 0.05 | fraction of FCI | 5.0% FCI — Turton | §9.4 |

### 4.4 Utility prices

| Parameter | Value | Units | Literature source | Framework |
|-----------|-------|-------|------------------|-----------|
| `electricity_price` | $0.032 | $/kWh | DOE Wind energy PPA price (renewable baseline) | §9.4 |
| `steam_price` | $13.00 | $/GJ | Turton *Analysis, Synthesis and Design of Chemical Processes* | §9.4 |
| `cooling_water_price` | $0.015 | $/m³ | Turton | §9.4 |
| `chilled_water_price` | $5.00 | $/GJ | Seider et al. Table 8.3 | §9.4 |
| `water_price` | $0.27 | $/m³ | Seider et al. Table 8.3 — process water | §9.4 |
| `ammonia_price` | $0.50 | $/kg NH₃ | BusinessAnalytiq commodity price database | §9.4 |
| `wwt_organic_removal_cost` | $0.33 | $/kg organic removed | Seider et al. — WWT operating cost basis | §9.4 |

---

## Part 5 — Nutrients recipe

Stored as the `NUTRIENTS_RECIPE` singleton (`NutrientsRecipe` dataclass) in `common/parameters.py`. Shared across all four routes; derived properties computed live in `common/nutrients.py`.

**Recipe source:** Yu & Munasinghe (2018) Fermentation 4(3):63 — mineral medium for C. necator.

### 5.1 Concentrations and prices

| Component | Concentration (g/L) | Price ($/kg) | Price basis |
|-----------|-------------------|------------|------------|
| Na₂HPO₄·2H₂O | 2.500 | $2.10 | Sigma-Aldrich list × 0.01 (industrial bulk discount) — §9.3 |
| KH₂PO₄ | 2.400 | $1.70 | Same source |
| NH₄Cl | 1.000 | $0.90 | Same source |
| MgSO₄·7H₂O | 0.500 | $1.70 | Same source |
| NaHCO₃ | 0.500 | $1.00 | Same source |
| FerricAmmoniumCitrate | 0.100 | $5.00 | Same source |
| TraceMetals† | 0.0014 | $60.00 | Same source |
| **Total** | **7.0014 g/L** | — | — |

† TraceMetals is a combined entry for H₃BO₃, CoCl₂, ZnSO₄, MnCl₂, Na₂MoO₄, NiCl₂, CuSO₄.

### 5.2 Derived properties (computed live by `common/nutrients.py`)

| Property | Formula | Value |
|----------|---------|-------|
| Composite price | mass-weighted average of component prices | ~$1.74/kg |
| Stoichiometric coefficient | total g/L ÷ achieved_titer g/L | 7.0014 / 18.0 = 0.389 g Nutrients/g biomass |
| `achieved_titer` | CDW titer at which recipe was reported — Yu & Munasinghe (2018) | 18.0 g/L |

The composite price (~$1.74/kg) is a snapshot reference value; the live computation from the recipe dict is the authoritative value used in the model.

---

## Part 6 — Gas fermentation stoichiometric constants

Stored at module level in `common/kinetics.py`. Molar coefficients per mol biomass for the lithoautotrophic H₂/CO₂ growth reaction (Framework §9.5a).

**Source:** Representative knallgas stoichiometry for *C. necator* — literature molar equation.

| Constant | Value | Units | Species |
|----------|-------|-------|---------|
| `GAS_FERM_N_H2` | 21.36 | mol H₂ / mol biomass | H₂ consumed (electron donor + H source) |
| `GAS_FERM_N_O2` | 6.21 | mol O₂ / mol biomass | O₂ consumed (terminal electron acceptor) |
| `GAS_FERM_N_CO2` | 4.09 | mol CO₂ / mol biomass | CO₂ consumed (carbon source) |
| `GAS_FERM_N_NH3` | 0.76 | mol NH₃ / mol biomass | NH₃ consumed (nitrogen source) |
| `GAS_FERM_N_H2O` | 18.70 | mol H₂O / mol biomass | H₂O produced |

These constants are used in two places:
1. `build_autotrophic_growth_reaction()` — assembles the mass-basis BioSTEAM Reaction
2. `PerfusionBioreactor` constructor — passed as molar coefficients for internal mass balance

The biomass formula C₄.₀₉H₇.₁₃O₁.₈₉N₀.₇₆ is confirmed by `n_CO2 = n_C = 4.09` and `n_NH3 = n_N = 0.76`.

---

## Part 7 — Perfusion bioreactor and gas delivery constants

These constants are internal to the gas fermentation model (`models/gas_fermentation_model.py` and `perfusion_bioreactor/`). They are not in `common/parameters.py` but are recorded here for completeness.

| Parameter | Value | Units | Basis | Framework |
|-----------|-------|-------|-------|-----------|
| Operating pressure (droplet column) | 4 | atm | Pre-saturation pressure for H₂ dissolution | §4, §4a |
| Dissolved H₂ feed concentration (S_f) | 0.0051 | g/L | Henry's law at 4 atm operating pressure | §4 |
| UF membrane Q_max (per unit) | 378,500 | m³/d | Guo et al. (2014) Table 1 validated range upper bound | §4a |
| UF capital correlation α | 1.003 | — | Guo et al. (2014) Table 1 | §4a |
| UF capital correlation β | 0.830 | — | Guo et al. (2014) Table 1 | §4a |
| UF capital correlation C | 3.832 | — | Guo et al. (2014) Table 1 (log₁₀ scale) | §4a |
| UF O&M correlation α | 1.828 | — | Guo et al. (2014) Table 1 | §4a |
| UF O&M correlation β | 0.598 | — | Guo et al. (2014) Table 1 | §4a |
| UF O&M correlation C | 1.876 | — | Guo et al. (2014) Table 1 (log₁₀ scale) | §4a |
| UF cost reference year | 2012 | — | Guo et al. (2014); CEPCI-escalated to 2025 | §4a |

---

## Part 8 — Derived quantities (not independent parameters)

These values are computed from parameters above and are recorded here as cross-checks only. They should not be hardcoded anywhere in the model.

| Quantity | Formula | Value | Computed in |
|----------|---------|-------|------------|
| Effective operating hours | 8,760 − 336 − 672 | 7,752 h/yr | `common/operating_hours.py` |
| Contamination restart hours | RESTARTS_PER_YEAR × RESTART_DURATION_H | 672 h/yr/line | `common/operating_hours.py` |
| Required fermenter output | 25,000 / CENTRIFUGE_RECOVERY | 26,316 MT CDW/yr | `common/kinetics.py` |
| Working capital | FCI × WC_over_FCI | FCI × 0.176 | BioSTEAM TEA |
| TCI | FCI × (1 + WC_over_FCI) | FCI × 1.176 | BioSTEAM TEA |
| Gas ferm Yxs | MW_biomass / (GAS_FERM_N_H2 × MW_H2) | 97.20 / 43.06 = 2.26 | `common/kinetics.py` |
| Nutrients composite price | mass-weighted recipe | ~$1.74/kg | `common/nutrients.py` |
| Nutrients coefficient | 7.0014 g/L / 18.0 g/L | 0.389 g/g biomass | `common/nutrients.py` |
| Fructose X* | 0.75 × 32.0 | 24.0 g/L | `common/kinetics.py` |
| Acetate X* | 0.75 × 15.0 | 11.25 g/L | `common/kinetics.py` |
| Formate X* | min(0.75 × 10.5, 0.06 × 0.9 × 3.0 / 0.1) = min(7.875, 1.62) | **1.62 g/L** (inhibition-constrained; S\*\_max = 3.0 g/L — Grunwald 2015 is binding) | `common/kinetics.py` inhibition branch |
| Fructose τ | 1 / (0.80 × 0.22) | 5.68 h | `common/kinetics.py` |
| Acetate τ | 1 / (0.80 × 0.15) | 8.33 h | `common/kinetics.py` |
| Formate τ | 1 / (0.80 × 0.18) | 6.94 h | `common/kinetics.py` |
| Gas ferm τ | 1 / (0.80 × 0.12) | 10.42 h | `common/kinetics.py` |
| TEA operating days | 7,752 / 24 | 323.0 d/yr | `common/economics.py` |

---

## Audit notes

1. **Formate Yxs source:** `common/parameters.py` cites Claassens et al. (2020) Metab. Eng. for the formate Yxs of 0.06 g/g, while the Framework may reference Grunwald et al. (2015) for μmax and titer. These are separate measurements — different experiments. The code is authoritative.

2. **Gas fermentation Yxs:** The stored value (2.26) is derived from the molar equation, not directly measured. This supersedes the Yu & Lu (2019) reported value of 1.56 g/g to ensure internal consistency between Yxs and the GAS_FERM_N_* stoichiometric constants. The comment in `parameters.py` documents this derivation explicitly.

3. **Nutrient prices:** Sigma-Aldrich list prices × 0.01 (1% of lab price as industrial bulk estimate). This is a deliberate methodological approximation — bulk industrial pricing data for specialty salts is not publicly available. The ±50% nutrient recipe scaling in the SA suite bounds the uncertainty.

5. **S_star_max inhibition ceiling:** Added to `RouteParams` (Framework §5 inhibition branch). Values: fructose = None, acetate = 3.0 g/L (Garcia-Gonzalez 2018, not binding), formate = 3.0 g/L (Grunwald 2015, **binding** — X* drops from 7.875 to 1.62 g/L, N_total rises from 12 to 53), gas fermentation = None (design_reactor() not called; Henry's law fixes S_f). The derived X* for formate in the table above reflects the inhibition branch output.

5. **H₂ feedstock price:** The $4.83/kg value from Peterson et al. (2019) reflects electrolytic H₂ at the time of that study. Current (2026) PEM electrolysis H₂ costs vary widely by location, electricity price, and electrolyzer cost learning rate. The SA `electricity_price` parameter partially captures this dependency, but the feedstock price for gas fermentation is treated as independent from electricity price in the OAT analysis (they are correlated in reality). The 2D sensitivity heatmap (`2d_sa_gas_fermentation.png`) shows MSP jointly as a function of electricity price and contingency_fee_factor, which provides the most relevant combined sensitivity view.
