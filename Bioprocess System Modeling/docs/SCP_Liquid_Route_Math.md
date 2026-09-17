# SCP Liquid-Route Bioreactor and Process Math

**Document scope:** Fructose, acetate, and formate routes.
**Last updated:** 2026-08-13
**Companion document:** `SCP_Perfusion_Bioreactor_Math.md` (gas fermentation route)
**Primary implementation:** `common/kinetics.py`, `common/reactors.py`, `common/nutrients.py`, `common/seed_train.py`

This document is written so that a reader familiar with bioprocess engineering can independently reproduce every intermediate value and verify the BioSTEAM model results. It covers the same ground as `SCP_Project_Framework.md §5` but presents all equations together in one place and makes all intermediate calculations explicit.

---

## 1. Overview: the liquid-route flowsheet

All three liquid-substrate routes (fructose, acetate, formate) share the same process topology. The carbon source and its kinetic parameters change; the sequence of unit operations does not.

```
Feedstock feed  ──────────────────────────────────┐
Nutrients feed  ────────────────────────────────┐ │
NH₃ feed       ──────────────────────────────┐ │ │
Recycle water  ──────────────────────────┐   │ │ │
                                          ↓   ↓ ↓ ↓
                                    M101 (MixTank)
                                          ↓
                                   HX101 (Sterilize, 134 °C)
                                          ↓
                                   HP101 (Hold, 2.44 min)
                                          ↓
                                   HX102 (Cool, 30 °C)
                                          ↓
                                   R101 (ExtentBasedBioreactor)
                                     ↓               ↓
                              Liquid effluent      Vent (CO₂, N₂, O₂, H₂O vapor)
                                     ↓
                               C101 (SolidsCentrifuge)
                                  ↓              ↓
                             Cake (biomass)    Centrate (→ WWT)
                                  ↓
                               D101 (SprayDryer)
                                  ↓              ↓
                            SCP product        Vapor (H₂O, atmospheric emission)
                                  ↓
                              ST105 (ProductStorage)
                                  ↓
                              Final SCP

                         [Seed train — see §6]
                         [WWT subsystem — see §7]
```

**Battery limits:** The system boundary starts at raw feedstocks (fructose/acetate/formate, NH₃, water, mineral nutrients) and ends at dried SCP powder. CO₂ in the vent is emitted to atmosphere (not captured or sold). H₂ is not a reactant for these routes.

---

## 2. Downstream recovery chain — backward pass

The production target of **25,000 MT/yr** applies to the **final packaged SCP product**, not the fermenter output. Each downstream step recovers less than 100% of the biomass, so the fermenter must be sized to a higher rate.

This is a backward pass through the process:

$$
\dot{m}_{\text{fermenter}} = \frac{\dot{m}_{\text{product}}}{\prod_i \eta_i}
$$

where $\eta_i$ is the fractional recovery at each downstream step (ordered from fermenter output toward final product).

### 2.1 Downstream steps and recoveries

| Step | Unit | Recovery η | Basis |
|------|------|-----------|-------|
| Centrifugation | C101 (`bst.SolidsCentrifuge`) | 0.95 (CENTRIFUGE_RECOVERY) | Engineering judgment, §9.2 |
| Spray drying | D101 (`bst.SprayDryer`) | 1.00 | Solids recovery = 100%; moisture addition only |

The spray dryer is not a recovery loss step — it removes water to reach 5% product moisture. All solid biomass that enters D101 exits in the SCP product stream. The final product moisture fraction is 0.05 (SPRAY_DRYER_MOISTURE).

### 2.2 Required fermenter output

$$
\dot{m}_{\text{fermenter}} = \frac{25{,}000 \text{ MT/yr}}{0.95} = 26{,}316 \text{ MT CDW/yr}
$$

The `required_fermenter_output()` function in `common/kinetics.py` performs this calculation for any list of efficiencies. The result becomes the input to `design_reactor()` as `adjusted_fermenter_output_MT_yr`.

---

## 3. Operating hours

Effective operating hours must be computed before sizing the fermenter (throughput Q depends on h/yr).

**Two independent downtime sources:**

| Source | Duration | Basis |
|--------|----------|-------|
| Plant-wide turnaround | 336 h/yr (2 weeks) | All lines down simultaneously |
| Contamination restarts | 672 h/yr per line (2 × 336 h) | Staggered — Cauldron/Stansfield, AgFunderNews March 2024 |

$$
h_{\text{eff}} = 8{,}760 - 336 - 672 = 7{,}752 \text{ h/yr} \quad (88.5\%)
$$

This value is returned by `effective_operating_hours()` in `common/operating_hours.py` and is used in two places:
1. **Throughput sizing** (Step 6 of `design_reactor()`)
2. **TEA operating days** (`SCPTEA` constructor: `operating_days = h_eff / 24 = 323.0 d/yr`)

---

## 4. Reactor design chain — forward pass

`design_reactor()` in `common/kinetics.py` implements nine sequential steps. Every quantity is derived from inputs; no additional constants are introduced inside the function.

### Inputs to `design_reactor()`

| Parameter | Symbol | Unit | Example (fructose) |
|-----------|--------|------|-------------------|
| Maximum specific growth rate | μmax | h⁻¹ | 0.22 |
| Biomass yield on substrate | Yxs | g biomass/g substrate | 0.32 |
| Literature ceiling titer | X_max | g/L | 32.0 |
| Substrate conversion extent | ε | — | 0.90 |
| Dilution rate margin | D_margin | fraction of μmax | 0.80 |
| Target titer fraction | f_titer | fraction of X_max | 0.75 |
| Adjusted fermenter output | ṁ_adj | MT CDW/yr | 26,316 |
| Max vessel volume | V_max | m³ | 355 (BioSTEAM default) |

### Step 2 — Target biomass titer X*

$$
X^* = f_{\text{titer}} \times X_{\max}
$$

The target titer is set as a fraction of the literature maximum. This is a design choice — operating below the maximum provides a safety margin and avoids inhibition near ceiling concentration.

**Inhibition branch (Framework §5):** For routes with a known residual-substrate inhibition ceiling S\*\_max (§9.1), `design_reactor()` also computes X\*\_inhibition = Yxs × ε × S\*\_max / (1 − ε) and uses X\* = min(X\*\_titer, X\*\_inhibition). The formate route is binding; acetate is not.

| Route | f_titer | X_max (g/L) | X\*\_titer (g/L) | S\*\_max (g/L) | X\*\_inhibition (g/L) | X\* used (g/L) | Binding? |
|-------|---------|-------------|----------------|--------------|---------------------|----------------|---------|
| Fructose | 0.75 | 32.0 | 24.0 | None | — | 24.0 | No |
| Acetate | 0.75 | 15.0 | 11.25 | 3.0 | 12.15 | 11.25 | No |
| Formate | 0.75 | 10.5 | 7.875 | 3.0 | **1.62** | **1.62** | **Yes** |

### Step 3 — Substrate feed concentration S₀

The feed concentration must be consistent with the target titer and conversion extent. At steady state, substrate consumed = S₀ × ε, and biomass produced = Yxs × (S₀ × ε):

$$
X^* = Y_{xs} \cdot S_0 \cdot \varepsilon
$$

$$
S_0 = \frac{X^*}{Y_{xs} \cdot \varepsilon}
$$

| Route | X* (g/L) | Yxs (g/g) | ε | S₀ (g/L) |
|-------|---------|---------|---|---------|
| Fructose | 24.0 | 0.32 | 0.90 | 83.3 |
| Acetate | 11.25 | 0.45 | 0.90 | 27.8 |
| Formate | **1.62** | 0.06 | 0.90 | **30.0** |

Note: The formate route uses the inhibition-constrained X* = 1.62 g/L (not the titer-forward 7.875 g/L), because the Grunwald et al. (2015) inhibition ceiling S\*\_max = 3.0 g/L is binding. This brings S0 down from the unconstrained 145.8 g/L to 30.0 g/L — a physically realistic feed concentration (see §4 Step 2 above). Yxs = 0.06 g/g still means 16.7 g formate per gram of biomass, but the lower X* means the reactor must process proportionally more liquid volume, driving a much higher vessel count (N_total = 53 vs. 12 unconstrained).

### Step 4 — Residual substrate concentration S*

At steady state, the residual substrate in the effluent is the unconverted fraction:

$$
S^* = S_0 \cdot (1 - \varepsilon)
$$

S* represents the substrate loading on wastewater treatment (WWT). Higher ε → lower WWT burden.

| Route | S₀ (g/L) | ε | S* (g/L) |
|-------|---------|---|---------|
| Fructose | 83.3 | 0.90 | 8.33 |
| Acetate | 27.8 | 0.90 | 2.78 |
| Formate | **30.0** | 0.90 | **3.0** |

Formate S* = 3.0 g/L equals S\*\_max exactly — the inhibition ceiling is saturated, not exceeded. The unconstrained S* would have been 14.58 g/L, well above the Grunwald (2015) extrapolated zero-yield point (~3–4 g/L).

### Step 5 — Operating dilution rate D and hydraulic residence time τ

A chemostat operates at steady state when the dilution rate D equals the specific growth rate μ. To prevent washout (D > μmax → cells washed out before they can grow) while maintaining productivity, D is set conservatively below μmax:

$$
D = D_{\text{margin}} \times \mu_{\max}
$$

$$
\tau = \frac{1}{D}
$$

| Route | μmax (h⁻¹) | D_margin | D (h⁻¹) | τ (h) |
|-------|-----------|---------|--------|------|
| Fructose | 0.22 | 0.80 | 0.176 | 5.68 |
| Acetate | 0.15 | 0.80 | 0.120 | 8.33 |
| Formate | 0.18 | 0.80 | 0.144 | 6.94 |

τ is set at construction in `ExtentBasedBioreactor._init()` as `tau = 1.0 / (D_margin × mu_max)`. BioSTEAM uses τ internally to size the reactor volume (V = Q × τ / V_wf).

### Step 6 — Required volumetric throughput Q

Q is the **water** volumetric throughput of the fermentation system — i.e., `Q × 1000 kg/h` is the water mass fed to M101, and solutes (substrate, nutrients, NH₃) are additional mass on top of that water. At the dilute concentrations used here (X* ≈ 8–24 g/L, substrate ≈ 10–80 g/L), the broth is effectively aqueous and Q is the quantity needed to deliver the required fermenter CDW output:

$$
Q = \frac{\dot{m}_{\text{adj}} \times 10^6 \text{ g/MT}}{h_{\text{eff}} \text{ [h/yr]} \times X^* \text{ [g/L]} \times 1000 \text{ L/m}^3} \quad [\text{m}^3/\text{h}]
$$

The 10⁶ converts MT/yr to g/yr; dividing by X* (g/L) gives L/h; dividing by 1000 converts L/h to m³/h.

| Route | ṁ_adj (MT/yr) | h_eff (h/yr) | X* (g/L) | Q (m³/h) |
|-------|--------------|------------|---------|--------|
| Fructose | 26,316 | 7,752 | 24.0 | 141.6 |
| Acetate | 26,316 | 7,752 | 11.25 | 302.1 |
| Formate | 26,316 | 7,752 | **1.62** | **2,096** |

Formate's Q is now ~5× higher than the unconstrained value (431.6 m³/h) because the inhibition-constrained X* = 1.62 g/L is ~5× lower than the titer-forward 7.875 g/L. More liquid volume per unit time must pass through the system to deliver the same 26,316 MT CDW/yr at the lower titer.

### Step 7 — Total required reactor volume V_total

BioSTEAM's `AbstractStirredTankReactor` applies a working-volume fraction V_wf = 0.80, meaning 80% of each vessel's geometric volume is usable liquid volume. The total geometric volume needed is:

$$
V_{\text{total}} = \frac{Q \times \tau}{V_{\text{wf}}} = \frac{Q \times \tau}{0.80}
$$

This matches BioSTEAM's internal sizing calculation exactly (confirmed from installed source).

| Route | Q (m³/h) | τ (h) | V_wf | V_total (m³) |
|-------|--------|------|------|------------|
| Fructose | 141.6 | 5.68 | 0.80 | 1,005 |
| Acetate | 302.1 | 8.33 | 0.80 | 3,140 |
| Formate | **2,096** | 6.94 | 0.80 | **18,183** |

### Step 8 — Number of capacity vessels N_capacity

Each vessel has a maximum volume of V_max = 355 m³ (BioSTEAM default for industrial-scale stirred tanks). The number of parallel production vessels needed to provide V_total is:

$$
N_{\text{capacity}} = \left\lceil \frac{V_{\text{total}}}{V_{\max}} \right\rceil
$$

| Route | V_total (m³) | V_max (m³) | N_capacity |
|-------|------------|----------|----------|
| Fructose | 1,005 | 355 | 3 |
| Acetate | 3,140 | 355 | 9 |
| Formate | **18,183** | 355 | **52** |

The ceiling function ensures the total installed volume meets or exceeds V_total.

### Step 9 — Total vessel count with N+1 redundancy

One additional production vessel is added as an N+1 spare. This vessel covers capacity during planned maintenance, contamination-driven restarts of individual lines, or equipment failure. It is priced as a full vessel in the TEA.

$$
N_{\text{total}} = N_{\text{capacity}} + 1
$$

| Route | N_capacity | N_total |
|-------|----------|-------|
| Fructose | 3 | 4 |
| Acetate | 9 | 10 |
| Formate | **52** | **53** |

The N+1 mechanism in BioSTEAM is implemented in `ExtentBasedBioreactor._design()`:
```python
def _design(self) -> None:
    super()._design()           # BioSTEAM auto-solves N_capacity → self.parallel['self']
    self.parallel['self'] += 1  # N+1 redundancy vessel
```

`self.parallel['self']` tells BioSTEAM to price that many identical vessels. After `super()._design()`, `self.parallel['self'] = N_capacity`; the `+= 1` makes it `N_total`.

---

## 5. Growth stoichiometry — Roels' degree-of-reduction method

The growth reaction stoichiometry determines: (a) how much O₂ the reactor needs, (b) how much CO₂ and H₂O are produced in the vent, and (c) how much NH₃ is consumed for nitrogen. These coefficients are computed from the molecular formulas — nothing is hardcoded.

### 5.1 Biomass formula

All four routes use *C. necator* biomass with empirical formula:

$$
\text{C}_{4.09}\text{H}_{7.13}\text{O}_{1.89}\text{N}_{0.76}
$$

Molecular weight: MW_X = 4.09(12.011) + 7.13(1.008) + 1.89(15.999) + 0.76(14.007) = **97.20 g/mol**

### 5.2 Per-C-mol atomic ratios

For any formula $\text{C}_{n_C}\text{H}_{n_H}\text{O}_{n_O}\text{N}_{n_N}$, the per-C-mol ratios are:

$$
h = n_H / n_C, \quad o = n_O / n_C, \quad n = n_N / n_C
$$

**Substrate formulas and ratios:**

| Route | Substrate | Formula | n_C | h | o | n |
|-------|-----------|---------|-----|---|---|---|
| Fructose | C₆H₁₂O₆ | — | 6 | 2.000 | 1.000 | 0 |
| Acetate | C₂H₄O₂ | — | 2 | 2.000 | 1.000 | 0 |
| Formate | CH₂O₂ | — | 1 | 2.000 | 2.000 | 0 |

**Biomass ratios (C₄.₀₉H₇.₁₃O₁.₈₉N₀.₇₆):**

$$
h_X = 7.13/4.09 = 1.743, \quad o_X = 1.89/4.09 = 0.462, \quad n_X = 0.76/4.09 = 0.186
$$

### 5.3 Degree of reduction γ (Roels)

The degree of reduction per C-mol quantifies the available electrons for respiration:

$$
\gamma = 4 + h - 2o - 3n
$$

This formula assigns oxidation states: C → 4 electrons; H → +1 (contributing); O → −2 (consuming 2 electrons each); N → −3 (consuming 3 electrons each, as NH₃ is the reference nitrogen source).

| Species | Formula | γ |
|---------|---------|---|
| Fructose | C₆H₁₂O₆ | 4 + 2 − 2(1) − 0 = **4.00** |
| Acetate | C₂H₄O₂ | 4 + 2 − 2(1) − 0 = **4.00** |
| Formate | CH₂O₂ | 4 + 2 − 2(2) − 0 = **2.00** |
| Biomass | C₄.₀₉H₇.₁₃O₁.₈₉N₀.₇₆ | 4 + 1.743 − 2(0.462) − 3(0.186) = **4.261** |

Formate's γ = 2 is notably low — it is a more oxidized substrate than fructose or acetate, meaning less energy is available per C-mol for biosynthesis. This is reflected in the very low Yxs = 0.06 g/g.

### 5.4 Yield conversion: g/g → C-mol/C-mol

Yxs is given in g biomass / g substrate. Converting to C-mol/C-mol:

$$
Y_{xs}^{C\text{-mol}} = Y_{xs} \cdot \frac{MW_S / n_{C,S}}{MW_X / n_{C,X}}
$$

where MW_S / n_C,S is the mass per C-mol of substrate and MW_X / n_C,X is the mass per C-mol of biomass.

| Route | Yxs (g/g) | MW_S | n_C,S | MW_X | n_C,X | MW_S/n_C,S | MW_X/n_C,X | Y_Cmol |
|-------|---------|------|------|------|------|-----------|-----------|--------|
| Fructose | 0.32 | 180.16 | 6 | 97.20 | 4.09 | 30.03 | 23.76 | 0.404 |
| Acetate | 0.45 | 60.05 | 2 | 97.20 | 4.09 | 30.03 | 23.76 | 0.568 |
| Formate | 0.06 | 46.03 | 1 | 97.20 | 4.09 | 46.03 | 23.76 | 0.116 |

### 5.5 Stoichiometric coefficients per C-mol substrate

**O₂** (from electron balance):
$$
\nu_{O_2} = \frac{\gamma_S - Y_{xs}^{C\text{-mol}} \cdot \gamma_X}{4}
$$

**CO₂** (from C balance; C in substrate = C in biomass + C in CO₂):
$$
\nu_{CO_2} = 1 - Y_{xs}^{C\text{-mol}}
$$

**NH₃** (from N balance; N in biomass comes from NH₃):
$$
\nu_{NH_3} = Y_{xs}^{C\text{-mol}} \cdot n_X - n_S
$$

Since all three substrates contain no nitrogen (n_S = 0):
$$
\nu_{NH_3} = Y_{xs}^{C\text{-mol}} \cdot 0.186
$$

**H₂O** (from H balance; H in substrate + 3×H in NH₃ = H in biomass + 2×H in H₂O):
$$
\nu_{H_2O} = \frac{h_S + 3 \nu_{NH_3} - Y_{xs}^{C\text{-mol}} \cdot h_X}{2}
$$

All values below are per **C-mol substrate** (positive = consumed, negative = produced):

| Route | ν_O₂ | ν_CO₂ | ν_NH₃ | ν_H₂O |
|-------|------|------|------|------|
| Fructose | (4.00 − 0.404×4.261)/4 = 0.569 | 1 − 0.404 = 0.596 | 0.404×0.186 = 0.0751 | (2 + 3×0.0751 − 0.404×1.743)/2 = 0.760 |
| Acetate | (4.00 − 0.568×4.261)/4 = 0.395 | 1 − 0.568 = 0.432 | 0.568×0.186 = 0.106 | (2 + 3×0.106 − 0.568×1.743)/2 = 0.663 |
| Formate | (2.00 − 0.116×4.261)/4 = 0.376 | 1 − 0.116 = 0.884 | 0.116×0.186 = 0.0216 | (2 + 3×0.0216 − 0.116×1.743)/2 = 0.933 |

### 5.6 Scale to per-mol substrate (multiply by n_C,S)

Multiply each coefficient by n_C,S to convert from per-C-mol to per-mol substrate:

| Route | n_C,S | O₂ (mol/mol S) | CO₂ (mol/mol S) | NH₃ (mol/mol S) | H₂O (mol/mol S) |
|-------|------|--------------|---------------|---------------|---------------|
| Fructose | 6 | 3.414 | 3.576 | 0.451 | 4.562 |
| Acetate | 2 | 0.790 | 0.864 | 0.212 | 1.326 |
| Formate | 1 | 0.376 | 0.884 | 0.0216 | 0.933 |

### 5.7 Mass-basis conversion for BioSTEAM Reaction

BioSTEAM reactions use mass basis (g/g substrate). Convert mol/mol → g/g using MW:

$$
\nu_{\text{wt}}(i) = \nu_{\text{mol}}(i) \times \frac{MW_i}{MW_S}
$$

The growth reaction is assembled as:
```
{Substrate} + {N_wt} Nutrients + {NH3_wt} NH3 + {O2_wt} O2
    -> {Yxs} CNecatorBiomass + {CO2_wt} CO2 + {H2O_wt} H2O
```
with `X=epsilon` (conversion fraction) and `basis='wt'`.

The `Nutrients` coefficient is: N_wt = nutrient_coefficient × Yxs (g Nutrients per g substrate).

---

## 6. Seed train

The seed train provides inoculum for production vessel restarts. Each contamination event requires a fresh 3-stage batch seed from a cryopreserved stock.

### 6.1 Stage working volumes

Three seed stages, each 5% (INOCULUM_RATIO = 0.05) of the next larger stage's working volume:

$$
V_{\text{work},i} = V_{\text{work,prod}} \times \text{INOCULUM\_RATIO}^{4-i}
$$

where i = 1 (smallest) to 3 (largest stage, directly inoculating production vessels), and V_work,prod is the working volume of one production vessel = V_total / N_capacity × 0.80.

**Example (fructose, V_total = 1,005 m³, N_capacity = 3):**
$$
V_{\text{work,prod}} = \frac{1{,}005}{3} \times 0.80 = 268 \text{ m}^3
$$

| Stage | Reactor | Volume |
|-------|---------|--------|
| 1 (smallest) | SR101 | 268 × 0.05³ = **0.034 m³** (34 L) |
| 2 | SR102 | 268 × 0.05² = **0.670 m³** (670 L) |
| 3 (largest) | SR103 | 268 × 0.05¹ = **13.4 m³** |

### 6.2 Steady-state representation of batch operation

Seed vessels run as periodic-batch processes in reality, but BioSTEAM's TEA is a steady-state model. The steady-state approximation is achieved by setting the seed bioreactor residence time τ_seed such that BioSTEAM computes the correct batch working volume:

$$
\tau_{\text{seed}} = \frac{h_{\text{eff}}}{N_{\text{total}} \times \text{RESTARTS\_PER\_YEAR}}
$$

With this τ_seed, BioSTEAM computes:
$$
V_{\text{vessel}} = \frac{Q_{\text{seed}} \times \tau_{\text{seed}}}{V_{\text{wf}}} = V_{\text{work},i}
$$

which is exactly the batch working volume of stage i.

**Example (fructose, N_total = 4, RESTARTS_PER_YEAR = 2):**
$$
\tau_{\text{seed}} = \frac{7{,}752}{4 \times 2} = 969 \text{ h}
$$

### 6.3 Number of concurrent seed trains

Multiple restart events may overlap in time. If a restart requires SEED_BATCH_DURATION_H = 72 h, and there are N_total × RESTARTS_PER_YEAR restart events per year spread over h_eff hours, the fraction of time a seed train is busy is:

$$
N_{\text{seed\_trains}} = \left\lceil \frac{N_{\text{total}} \times \text{RESTARTS\_PER\_YEAR} \times \text{SEED\_BATCH\_DURATION\_H}}{h_{\text{eff}}} \right\rceil
$$

| Route | N_total | Restarts/yr | Seed h | h_eff | N_seed_trains |
|-------|---------|-----------|--------|-------|-------------|
| Fructose | 4 | 2 | 72 | 7,752 | 1 |
| Acetate | 10 | 2 | 72 | 7,752 | 1 |
| Formate | **53** | 2 | 72 | 7,752 | 1 |

All three liquid routes need only N_seed_trains = 1. Even with formate's N_total = 53, the calculation gives ceil(53 × 2 × 72 / 7,752) = ceil(0.985) = 1 — restart events still do not overlap often enough to require a second concurrent seed train. (Compare gas fermentation with N_total ≈ 493, which needs N_seed_trains ≈ 10.)

### 6.4 Seed train topology

```
ST201 (feedstock storage, τ=168 h) ─┐
ST202 (nutrients storage, τ=168 h)  ─┤→ SM101 (MixTank, τ=1h)
ST203 (NH₃ storage, τ=168 h)       ─┘    → SHX101 (HXutility, heat to 134°C)
seed_water_feed ────────────────────┘         → SHP101 (HoldPipe, 2.44 min)
                                                  → SHX102 (HXutility, cool to 30°C)
                                                  → SSP101 (Splitter)
                                                      ↓ (split_ssp101)    ↓ (1−split_ssp101)
                                                    SR103               SSP102 (Splitter)
                                                                          ↓ (split_ssp102)  ↓
                                                                        SR101              SR102
```

Split fractions derived from stage volumes (computed, not hardcoded):
$$
\text{split\_ssp101} = \frac{V_{\text{work,3}}}{V_{\text{work,1}} + V_{\text{work,2}} + V_{\text{work,3}}} \approx 0.952
$$
$$
\text{split\_ssp102} = \frac{V_{\text{work,1}}}{V_{\text{work,1}} + V_{\text{work,2}}} \approx 0.048
$$

SR103 receives ~95.2% of the pooled seed flow (it is the largest stage), SR101 ~0.24%, SR102 ~4.75%.

---

## 7. Nutrients — composite price and stoichiometry

The mineral nutrients recipe is taken from Yu & Munasinghe (2018) (same medium composition for all routes). All derived quantities are computed live from the raw recipe dict.

### 7.1 Recipe (per liter of fermentation medium)

| Component | Concentration (g/L) | Price ($/kg) |
|-----------|-------------------|------------|
| Na₂HPO₄·2H₂O | 2.500 | 2.10 |
| KH₂PO₄ | 2.400 | 1.70 |
| NH₄Cl | 1.000 | 0.90 |
| MgSO₄·7H₂O | 0.500 | 1.70 |
| NaHCO₃ | 0.500 | 1.00 |
| FerricAmmoniumCitrate | 0.100 | 5.00 |
| TraceMetals | 0.0014 | 60.00 |
| **Total** | **7.0014** | — |

### 7.2 Composite price (mass-weighted average)

$$
p_{\text{Nutrients}} = \sum_i \frac{c_i}{\sum_j c_j} \cdot p_i
$$

where $c_i$ are component concentrations (g/L) and $p_i$ are prices ($/kg).

$$
p_{\text{Nutrients}} = \frac{2.5(2.10) + 2.4(1.70) + 1.0(0.90) + 0.5(1.70) + 0.5(1.00) + 0.1(5.00) + 0.0014(6.00)}{7.0014} \approx \$1.74\text{/kg}
$$

### 7.3 Stoichiometric coefficient

$$
\text{coefficient} = \frac{\sum_i c_i}{\text{achieved\_titer}} = \frac{7.0014}{18.0} = 0.389 \text{ g Nutrients / g biomass}
$$

where achieved_titer = 18.0 g CDW/L is from Yu & Munasinghe (2018) — the same paper that reports the recipe. This ensures the nutrient demand scales with the titer at which the recipe was characterized.

The stoichiometric coefficient enters the growth reaction as: N_wt = 0.389 × Yxs (g Nutrients / g substrate).

---

## 8. Wastewater treatment

### 8.1 WWT sources

| Stream | Source | Composition |
|--------|--------|-------------|
| Centrifuge centrate | C101 outs[1] | Dilute aqueous: residual substrate, dissolved organics, water |
| Seed train effluents | SR101, SR102, SR103 (each outs[1]) | Same composition as production effluent, small volumes |

Note: D101 (SprayDryer) `outs[0]` is evaporated water vapor discharged directly to atmosphere — it is **not** a WWT feed. Only the centrifuge centrate and seed train effluents enter WWT101.

Both streams are combined in WWT101 (bst.Mixer), then processed through WWT102 and RCY101.

### 8.2 WWT101 — inline mixer

All wastewater streams combined at atmospheric conditions. Zero capital (bst.Mixer). No reaction or dissolution.

### 8.3 WWT102 — biological treatment (activated sludge model)

Two-step mass balance implemented in `_SludgeSettler` (custom `bst.Unit`, zero capital):

**Step 1 — organic removal:** 99% of each non-H₂O component is routed to sludge; 1% passes to treated water (outs[0]).

**Step 2 — moisture-controlled sludge water:** Water is transferred to sludge to reach WWT_SLUDGE_MOISTURE = 0.80 (80% wt/wt):

$$
\dot{m}_{H_2O \to \text{sludge}} = \frac{0.80}{1 - 0.80} \times \dot{m}_{\text{dry sludge}} = 4 \times \dot{m}_{\text{dry sludge}}
$$

The remaining water passes to treated water. At typical process flows, water lost to sludge is <1.1% of inlet water — negligible effect on the recycle balance.

Effective split fractions:
- Non-H₂O components: 0.01 → treated water (outs[0]); 0.99 → sludge (outs[1])
- H₂O: 4 × dry sludge mass → sludge; remainder → treated water

**Sludge pricing:** wwt_organic_removal_cost = $0.33/kg is a cost per kg of *dry organic removed* (Seider et al.). BioSTEAM charges `stream.price × total_stream_mass`, so the price is scaled by `(1 − moisture)` to recover the correct cost:

$$
\text{sludge.price} = -0.33 \times (1 - 0.80) = -\$0.066\text{/kg wet sludge}
$$

$$
\text{WWT cost} (\$/\text{yr}) = 0.066 \times \dot{m}_{\text{wet sludge}} \times h_{\text{eff}}
= 0.33 \times \dot{m}_{\text{dry organic}} \times h_{\text{eff}}
$$

BioSTEAM deducts this from variable operating costs automatically via the negative stream price.

### 8.4 RCY101 — recycle splitter

75% (WWT_WATER_RECYCLE_FRACTION = 0.75) of treated water is recycled to the process feed (M101 inlet). 25% is discharged as clean treated effluent (price = 0).

**Why 75% and not 100%?** Aerobic fermentation is a net water-*producing* process: the reaction

```
Substrate + O₂ → CNecatorBiomass + CO₂ + H₂O
```

produces water as a stoichiometric product. Recycling all treated water would cause unbounded accumulation of water in the recycle loop. A recycle fraction < 1 makes the loop a contraction mapping, guaranteeing convergence to a finite steady-state recycle flow. At 75% recycle, the steady-state recycle flow is finite and the system converges.

### 8.5 Recycle wiring

The recycle_water stream is pre-created with a convergence seed flow by the model builder and wired into M101's inlets before the system is assembled. RCY101 sets it as its outlet (outs[0]). BioSTEAM iterates the recycle loop (bst.System convergence) until the recycle flow is consistent.

---

## 9. Techno-economic analysis

### 9.1 Capital cost basis

Capital costs use the **Turton bare module + contingency/fees method**:

$$
\text{IEC} = \sum_i C_{P,i} \times f_{\text{BM},i}
\qquad
\text{FCI} = 1.18 \times \text{IEC}
$$

where $C_{P,i}$ is the bare purchase cost of unit $i$ and $f_{\text{BM},i}$ is its bare module factor
(accounts for direct installation — field labour, piping, civil, electrical, insulation — sourced from
BioSTEAM's built-in unit cost correlations, which are drawn from Turton Tables A.1–A.8 and Seider;
the f_BM values are properties of each unit class, not project-level parameters).
The 1.18 factor covers contingency (15%) + contractor fees (3%) on the sum of installed costs
— this is the only quantity from Turton Table 16.1 in this calculation.

BioSTEAM computes IEC as `system.installed_equipment_cost` = Σ(u.installed_cost) when `lang_factor=None`;
SCPTEA._FCI then applies the 1.18 multiplier.
The Excel "installed cost" column per unit sums to IEC, and IEC × 1.18 = FCI exactly.

In the fructose base case, per-unit f_BM values range from 1.65 (tanks) to 3.21 (heat exchangers),
with a purchase-cost-weighted average of **2.034**. The effective total multiplier from purchase cost
to FCI is therefore 1.18 × 2.034 ≈ **2.40×** — substantially less than the previous Lang factor
of 4.28×, which accounts for the FCI reduction across all routes.

$$
\text{TCI} = \text{FCI} \times (1 + \text{WC\_over\_FCI}) = \text{FCI} \times 1.176
$$

Working capital fraction = 0.176 (Seider et al.).

Construction schedule: 40% FCI in year −2, 60% in year −1.

### 9.2 Annual operating costs

**Fixed operating costs (FOC):**

| Category | Rate | $/yr (illustrative, fructose) |
|----------|------|------------------------------|
| Property tax | 1.0% × FCI | — |
| Property insurance | 1.0% × FCI | — |
| Maintenance | 10.0% × FCI | — |
| Administration | 5.0% × FCI | — |
| Labor | $3.6M/yr (all routes) | — |
| **Total FOC** | | |

**Variable operating costs (VOC):** BioSTEAM sums costs of all feed streams and utility consumptions and subtracts revenue from product streams. The key VOC contributors for liquid routes are feedstock, nutrients, NH₃, electricity (aeration compressor), and WWT sludge disposal.

### 9.3 MSP calculation

The minimum selling price (MSP) is the product price at which NPV = 0 over the 20-year project life, at IRR = 10%, income tax = 35%, MACRS7 depreciation.

BioSTEAM computes MSP via `tea.solve_price(product_stream)`. Despite the name, this method does **not** iterate over prices. It performs a single analytical solve:

1. Compute `price2cost` — the incremental effect on cumulative NPV of a unit increase in the product price: effectively the total discounted production volume (kg), Σ F_mass × op_hours / (1 + IRR)^t over the plant life.
2. Call `tea.solve_sales()` — finds the additional annual revenue needed to bring NPV from its current value (at product price = 0) to exactly 0. This is a linear solve on the cash flow equations.
3. Return `MSP = current_price + solve_sales_result / price2cost`.

The product stream price is **not modified** by `solve_price()` — it remains at 0 after the call. The cash flow table in the Cash Flow sheet sets the product stream price to MSP temporarily before calling `tea.get_cashflow_table()`, then restores it, so that the Sales column and cumulative NPV column correctly reflect the MSP scenario. Reference year: 2025, CEPCI = 809.3.

---

## 10. Reading the outputs

### Key metrics from `{route}_results.xlsx` → Executive Summary

| Metric | What it means |
|--------|--------------|
| MSP ($/kg SCP) | Minimum selling price — the central result |
| FCI ($M) | Fixed capital investment — installed equipment |
| Annual FOC ($M/yr) | Labor, maintenance, taxes, insurance |
| Annual VOC ($M/yr) | Feedstock, nutrients, electricity, WWT disposal |

### Checking stoichiometry — Mass Balance sheet

- **N₂**: input from air, output in vent. Closure should be ~100% (inert).
- **O₂**: input from air (via AeratedBioreactor), output in vent + consumed in reaction. Closure < 100% reflects consumption.
- **CNecatorBiomass**: input = 0 (not fed), output = product + sludge losses. Closure = N/A.
- **CO₂**: produced by respiration; input = 0 (not fed in liquid routes), output in vent.
- **H₂O**: net produced by aerobic metabolism; closure > 100% is expected (water generated).

### Checking reactor sizing — Equipment sheet

- R101 row: N (parallel) should equal N_total from Step 9 above.
- SR101/SR102/SR103 rows: N (parallel) = N_seed_trains (= 1 for all liquid routes).
- Vessel volume per unit should equal V_total / N_capacity (confirmed against `_V_WF = 0.80`).

### Checking cost decomposition — `cost_breakdown.xlsx` → Cost Breakdown sheet

The 10 OPEX categories should sum to MSP exactly (Capital charge is computed as the residual to ensure this). Large feedstock shares indicate feedstock price sensitivity (confirmed by OAT SA tornado charts).

### Checking year-by-year economics — Cash Flow sheet

The Cash Flow sheet (sheet 8 in `{route}_results.xlsx`) contains the full year-by-year table from `tea.get_cashflow_table()`. Key columns:

| Column | What to check |
|--------|--------------|
| Depreciable capital / Fixed capital investment | Pre-startup years (2023–2024) only; sums to FCI × construction schedule (40%/60%) |
| Working capital | Appears in year −1 (pre-startup); recovered in final year |
| Depreciation | MACRS7 schedule applied to FCI; front-loaded in years 1–8, then zero |
| Annual operating cost | Constant across operating years = VOC + FOC (matches Operating Costs sheet totals) |
| Sales | Revenue from the SCP product stream at MSP × annual production |
| Forwarded losses | Cumulative tax losses carried forward; reduces to zero once plant becomes profitable |
| Cash flow | Net cash position each year; should trend toward positive as depreciation shield phases out |
| Discount factor | 1/(1+IRR)^n — decreasing from 1.0; spot-check: year 1 ≈ 0.909 at 10% IRR |
| Cumulative NPV | Converges to ≈ 0 at end of plant life (by construction — MSP is the price that achieves this) |

---

## 11. Common questions

**Q: Why is formate's MSP ($15.51/kg) so much higher than acetate ($3.70/kg) despite formate being cheaper ($0.35 vs $0.65/kg)?**

Two compounding factors:

1. **Substrate economics:** Formate's Yxs = 0.06 g/g is 7.5× lower than acetate's Yxs = 0.45 g/g. This means ~16.7 kg of formate must be consumed to produce 1 kg of biomass. At $0.35/kg, the feedstock contribution alone is $5.83/kg SCP — more than acetate's entire MSP. This is a thermodynamic constraint from formate's low degree of reduction (γ = 2 vs. 4 for acetate).

2. **Inhibition-constrained vessel count:** The Grunwald et al. (2015) inhibition ceiling (S\*\_max = 3.0 g/L) is binding for formate. The CSTR must operate at X* = 1.62 g/L (not 7.875 g/L from the titer-forward design), requiring N_total = 53 vessels (vs. 10 for acetate) and FCI = $153.4M vs. $29.2M. Capital charges are therefore a co-dominant cost driver alongside feedstock.

**Q: Why do more vessels cost more — isn't each vessel the same price?**

Each vessel is the same per-unit cost, so N×cost scales linearly. But more vessels also means more N+1 redundancy overhead (one spare regardless of how many capacity vessels there are), more seed train restarts per year (N_total × 2 events/yr), and more maintenance labor (MOC = 10% × FCI). The capital component of MSP is therefore roughly proportional to N_total.

**Q: What is the working volume fraction V_wf = 0.80 and where does it appear?**

V_wf is a design convention: vessels are filled to 80% of their geometric volume to provide headspace for foam, level control, and sampling. It appears in:
- `design_reactor()` Step 7: V_total = Q × τ / 0.80
- `build_seed_train()`: V_work_prod = (V_total / N_capacity) × 0.80
- BioSTEAM's internal `AbstractStirredTankReactor._design()`: same formula

All three are consistent by design.

**Q: Why is aeration computed by BioSTEAM automatically and not specified explicitly?**

`ExtentBasedBioreactor` inherits from `bst.AeratedBioreactor`, which solves the O₂ demand from the reaction extent and the dissolved-O₂ setpoint (θ_O₂ = 0.5). The Roels-derived O₂ stoichiometric coefficient tells BioSTEAM how much O₂ the reaction consumes; BioSTEAM computes the required air flow, compressor power, and cooling duty automatically. The project does not specify an air flow rate directly — it is derived from the stoichiometry.

**Q: What happens when the recycle converges?**

BioSTEAM iterates the recycle loop (M101 → ... → RCY101 → M101) until the recycle_water flow is self-consistent (successive differences < tolerance). The converged recycle flow represents the steady-state water return from WWT. At 75% recycle efficiency, the steady-state recycle = feed water / (1 − 0.75 × WWT_water_recovery) — finite because 0.75 < 1.

---

*All equations implemented in `common/kinetics.py`, `common/reactors.py`, `common/nutrients.py`, `common/seed_train.py`, and `common/wastewater.py`. Framework §5, §6, §7, §9.*
