# SCP Route Comparison: Why the MSPs Differ

**Document scope:** Explains the physical and economic drivers behind the MSP differences across all four routes.
**Last updated:** 2026-08-13
**Base case MSPs (all routes, 25,000 MT/yr SCP, 2025 USD):**

| Route | Feedstock | Base MSP ($/kg SCP) | FCI ($M) |
|-------|-----------|-------------------|---------|
| Fructose | Fructose sugar | $5.78 | $22.3 |
| Acetate | Acetic acid | $3.70 | $29.2 |
| Formate | Formic acid | **$15.51** | **$153.4** |
| Gas fermentation | H₂ + CO₂ | $80.19 | $3,977.8 |

**Formate revised 2026-08-13 (inhibition constraint):** MSP increased from $10.68 to an intermediate value and FCI from ~$93M following addition of the Grunwald et al. (2015) substrate inhibition constraint (S\*\_max = 3.0 g/L). The inhibition-constrained X* = 1.62 g/L drives N_total from 12 to 53 vessels and raises capital substantially. **FCI method revised 2026-08-13 (Lang → Turton BM):** All FCI values reduced by switching from Lang factor (4.28 × Σpurchase_cost) to Turton bare module method (1.18 × Σ(C_P × f_BM)); after this switch the Excel "installed cost" column per unit sums to IEC, and IEC × 1.18 = FCI exactly.

These differences are not modeling artifacts. They trace directly to measurable biophysical properties of *C. necator* on each substrate: biomass yield, specific growth rate, and achievable titer. This document traces each number back to the underlying parameters.

---

## 1. The two levers that set MSP

Every cost component ultimately traces to one of two quantities:

**Lever 1 — Substrate economics** (feedstock cost per kg SCP)
$$
\text{Feedstock cost ($/kg SCP)} \approx \frac{p_{\text{feed}}}{Y_{xs}}
$$
where $p_{\text{feed}}$ is the feedstock price ($/kg) and $Y_{xs}$ is the biomass yield on that substrate (g biomass / g substrate). A cheap feedstock with poor yield is not necessarily cheap to use.

**Lever 2 — Capital economics** (vessel count and FCI per kg SCP)
$$
N_{\text{vessels}} \propto \frac{1}{\mu_{\max} \cdot X^*}
$$
Slow-growing organisms at low titer require more reactor volume per unit of biomass output, which means more vessels, higher FCI, and more capital-related charges per kg SCP.

Both levers operate simultaneously. The four routes differ primarily in which lever dominates.

---

## 2. Route-by-route parameter comparison

### 2.1 Key kinetic and design parameters

| Parameter | Fructose | Acetate | Formate | Gas ferm |
|-----------|---------|---------|---------|---------|
| μmax (h⁻¹) | 0.22 | 0.15 | 0.18 | 0.12 |
| Yxs (g biomass/g substrate) | 0.32 | 0.45 | 0.06 | 2.26* |
| Max titer X_max (g/L) | 32.0 | 15.0 | 10.5 | 7.0† |
| ε (substrate conversion) | 0.90 | 0.90 | 0.90 | 0.99 |
| D_margin (fraction μmax) | 0.80 | 0.80 | 0.80 | 0.80 |
| X* used (g/L) | 24.0 | 11.25 | **1.62‡** | —† |
| S\*\_max inhibition ceiling (g/L) | None | 3.0 | **3.0** | None |
| Feedstock price ($/kg) | $1.16 | $0.65 | $0.35 | $4.83 |

‡ Formate X* is inhibition-constrained (not titer-forward 7.875 g/L). Grunwald et al. (2015) shows biomass yield declines linearly with residual formate; extrapolated zero-yield point ~3–4 g/L. S\*\_max = 3.0 g/L (conservative lower bound) is binding: X\*\_inhibition = 0.06 × 0.9 × 3.0 / 0.1 = 1.62 g/L < X\*\_titer = 7.875 g/L. Framework §5 inhibition branch, implemented in `design_reactor()` — `common/kinetics.py`.

\* Yxs = 2.26 g CDW/g H₂ is derived from the literature molar stoichiometry; H₂ is a high-energy-density electron donor.
† Gas fermentation uses a perfusion bioreactor with fixed dissolved H₂ feed concentration (not a titer target); the effective operating titer is set by the gas dissolution physics (Henry's law at 4 atm).

### 2.2 Substrate economics: feedstock cost per kg SCP

$$
\frac{p_{\text{feed}}}{Y_{xs}} = \text{minimum substrate cost to produce 1 kg biomass (before losses)}
$$

| Route | p_feed ($/kg) | Yxs (g/g) | p_feed / Yxs ($/kg SCP) |
|-------|-------------|---------|----------------------|
| Fructose | $1.16 | 0.32 | $3.63 |
| Acetate | $0.65 | 0.45 | $1.44 |
| Formate | $0.35 | 0.06 | $5.83 |
| Gas ferm (H₂) | $4.83 | 2.26 | $2.14 |

This single ratio already explains much of the ranking:
- **Acetate** has the most favorable substrate economics: both a moderate price and the highest Yxs among the three liquid routes.
- **Formate** has the worst substrate economics despite the cheapest feedstock. Formate is a highly oxidized C1 molecule (degree of reduction γ = 2, vs. 4 for fructose and acetate). Less available electron energy means less biomass per gram consumed — Yxs = 0.06 g/g means 16.7 g of formate must be purchased for each gram of biomass. At $0.35/kg, the substrate alone costs $5.83/kg SCP before any other cost is added.
- **Gas fermentation** achieves a competitive substrate ratio ($2.14/kg) because H₂ is a high-energy electron donor. But the feedstock price ($4.83/kg H₂) is the highest of any route, and the capital cost (below) overwhelms this advantage.
- **Fructose** sits in the middle: respectable Yxs but a feedstock price nearly 2× acetate.

### 2.3 Capital economics: what drives vessel count

The number of production vessels is:
$$
N_{\text{total}} = \left\lceil \frac{Q \cdot \tau}{V_{\max} \cdot V_{wf}} \right\rceil + 1
$$

where Q = required volumetric throughput (m³/h) and τ = 1/D = 1/(D_margin × μmax). The product Q × τ is the total working volume needed, which grows when:
- μmax is low (long τ → more volume per unit time), or
- X* is low (high Q needed to deliver enough biomass per hour)

| Route | D (h⁻¹) | τ (h) | X* (g/L) | Q (m³/h) | V_total (m³) | N_capacity | N_total |
|-------|--------|------|---------|--------|------------|----------|-------|
| Fructose | 0.176 | 5.68 | 24.0 | 142 | 1,005 | 3 | 4 |
| Acetate | 0.120 | 8.33 | 11.25 | 302 | 3,140 | 9 | 10 |
| Formate | 0.144 | 6.94 | **1.62** | **2,096** | **18,183** | **52** | **53** |
| Gas ferm | 0.096 | 10.4 | very low† | very high | very large | ~491 | ~492 |

Formate values revised by inhibition constraint (S\*\_max = 3.0 g/L — Grunwald 2015). The titer-forward result would have been X* = 7.875, Q = 432, V_total = 3,742, N_total = 12 — but S* at those conditions = 14.58 g/L >> 3.0 g/L ceiling, putting the CSTR well past the extrapolated zero-yield point.

† Gas fermentation titer is set by dissolved H₂ at Henry's law saturation; at 4 atm the dissolved H₂ concentration is 0.0051 g/L, and even with Yxs = 2.26, the achievable titer is on the order of 0.01 g/L — orders of magnitude lower than the liquid-substrate routes, requiring an enormous volumetric throughput and vessel count.

The vessel count for gas fermentation (~492) is not a modeling error — it reflects the physical constraint that H₂ has very low aqueous solubility regardless of operating pressure or engineering improvements within the model's scope.

---

## 3. What drives each route's MSP

### 3.1 Fructose ($5.78/kg)

**Dominant cost driver: feedstock.**

Fructose has the most favorable vessel count (N_total = 4) among all routes, keeping capital charges low. The MSP is determined primarily by feedstock cost: at Yxs = 0.32 and $1.16/kg, the raw substrate cost contribution is ~$3.63/kg SCP, representing roughly 60% of MSP.

The OAT SA confirms this: the feedstock price perturbation (±50%) produces the largest MSP swing of any parameter for fructose (±$2.012/kg, ±34.8%). The next-largest driver is substrate conversion (ε), which sets how much of that expensive feedstock is actually converted to biomass.

**Summary:** Fructose's MSP is determined by feedstock price × inverse yield. Improving Yxs (genetic engineering) or securing cheaper fructose are the highest-leverage interventions.

### 3.2 Acetate ($3.70/kg)

**Dominant cost driver: feedstock, partially offset by the highest Yxs.**

Acetate achieves the lowest MSP among all four routes in this model. Two factors combine:
1. Yxs = 0.45 g/g — the highest of any route — means less substrate per kg SCP
2. Feedstock price = $0.65/kg — cheapest of the liquid-substrate routes

These together give a substrate cost contribution of ~$1.44/kg SCP, well below fructose.

The higher vessel count (N_total = 10 vs. fructose's 4) adds capital cost, partially offsetting the feedstock advantage. Acetate's slower μmax = 0.15 h⁻¹ (vs. fructose's 0.22) means longer τ and more total volume needed per unit output. The OAT SA shows capital cost (TCI ±35%) and feedstock price contribute roughly equal swing magnitude for acetate.

**Acetate ε SA is highly asymmetric (+37.0% / −2.8%) — not a model artifact.** At base ε = 0.90, acetate's titer-forward S* = 2.78 g/L sits just below the Garcia-Gonzalez (2018) inhibition ceiling of 3.0 g/L — the inhibition constraint is non-binding by only 0.22 g/L. When the SA perturbs ε to 0.85, X\*\_inhibition = 0.45 × 0.85 × 3.0 / 0.15 = 7.65 g/L drops below X\*\_titer = 11.25 g/L and the inhibition constraint becomes binding, increasing vessel count from ~10 to ~15 on top of the feedstock efficiency penalty. When ε = 0.95, the ceiling is comfortably non-binding (X\*\_inhibition = 25.65 g/L) and only feedstock efficiency improves. The asymmetry is a real consequence of acetate operating near the inhibition threshold at base conditions.

**Summary:** Acetate's combination of high yield and low feedstock price drives a favorable MSP. Maintaining ε ≥ 0.90 is critical — dropping below this threshold risks triggering the acetate inhibition constraint and a non-linear increase in vessel count.

### 3.3 Formate ($15.51/kg)

**Dominant cost drivers: substrate economics (low Yxs) AND capital (inhibition-constrained vessel count).**

Formate's MSP is 180% higher than fructose and 323% higher than acetate, despite having the cheapest feedstock ($0.35/kg). Two compounding factors:

**Substrate economics (unchanged from prior model):** Yxs = 0.06 g/g is the lowest yield of any route. Formate (CH₂O₂) has degree of reduction γ = 2, vs. 4 for fructose and acetate — half the available electrons per C-mol, meaning less ATP for biosynthesis and therefore less biomass per gram consumed. The substrate alone costs $5.83/kg SCP. This is a thermodynamic constraint, not a kinetics constraint.

**Capital (revised 2026-08-13):** The Grunwald et al. (2015) substrate inhibition constraint (S\*\_max = 3.0 g/L) is binding for formate: X*\_inhibition = 1.62 g/L < X\*\_titer = 7.875 g/L. The inhibition-constrained X* increases the vessel count from N_total = 12 to 53 (~4.9×), raising FCI from ~$93M to $265.0M. Capital is now a co-dominant cost driver alongside substrate economics. The unconstrained model's S* = 14.58 g/L would have operated the CSTR well past the extrapolated zero-yield point — the prior model was physically inconsistent for the formate route.

**OAT SA results (re-run 2026-08-13, Turton BM FCI method, base MSP = $15.51):**

| Parameter | Swing ($/kg) | Swing (%) |
|-----------|-------------|----------|
| Substrate conversion (ε) | +$10.071 / −$4.208 | **+65.0% / −27.1%** |
| Feedstock price (±50%) | ±$3.237 | ±20.9% |
| Capital cost (TCI ±35%) | +$0.784 / −$0.767 | +5.1% / −4.9% |
| Centrifuge recovery | +$0.869 / −$0.468 | +5.6% / −3.0% |
| Nutrients (±50%) | ±$0.341 | ±2.2% |
| Target titer fraction | ±$0.000 | **±0.0%** |

ε is now the overwhelmingly dominant driver, overtaking feedstock price. When the inhibition ceiling is binding, X\*\_inhibition = Yxs × ε × S\*\_max / (1−ε) — ε appears in both numerator and denominator with compounding leverage, simultaneously controlling feedstock efficiency and capital. Target titer fraction shows exactly 0% because `min(X*_titer, X*_inhibition)` always returns X*\_inhibition when the ceiling is binding — perturbing the fraction has no effect.

**Summary:** Formate's MSP reflects both the thermodynamic yield penalty of a low-reduction-degree C1 substrate and a physically necessary vessel-count increase from the inhibition constraint. The OAT SA confirms ε is the highest-leverage intervention: it simultaneously reduces feedstock waste and raises the inhibition-constrained X* (reducing capital). Improving inhibition tolerance (genetic engineering) would raise S\*\_max and reduce vessel count directly.

### 3.4 Gas fermentation ($80.19/kg)

**Dominant cost driver: capital (vessel count driven by low dissolved H₂ concentration).**

Gas fermentation's MSP is 14× fructose's and is in a different cost regime from the three liquid routes. The root cause is not the feedstock price (H₂ is expensive at $4.83/kg but Yxs = 2.26 gives favorable substrate economics: ~$2.14/kg SCP substrate cost). The root cause is H₂ aqueous solubility.

H₂ has very low aqueous solubility. At 4 atm operating pressure, the dissolved H₂ concentration at the bioreactor inlet is ~0.0051 g/L (Henry's law). Even though *C. necator* fully converts this dissolved H₂ (ε = 0.99) and has a high Yxs, the operating biomass titer is constrained to be proportional to dissolved H₂ availability — far below what the organism could achieve if H₂ were supplied in abundance. The result is that the system must pump enormous volumes of liquid through the bioreactors to deliver enough biomass per hour, requiring ~492 vessels.

With ~492 vessels at V_max = 355 m³ each, the fixed capital investment is very large. Capital-related charges (depreciation, tax, required return — captured in the "Capital charge" OPEX category) dominate the MSP.

The OAT SA confirms the capital-driven nature: water recycle fraction (+$7.161/−$4.295/kg, +8.9%/−5.4%), electricity price (+$8.855/−$2.254/kg, +11.0%/−2.8%), capital cost (TCI ±35%: −$5.695/+$4.989/kg, −7.1%/+6.2%), and centrifuge recovery (+$4.032/−$3.296/kg, +5.0%/−4.1%) are all large — consistent with the very large physical scale of the plant.

**Why electricity matters so much for gas fermentation:** The ~492 vessels each require aeration (for O₂ supply) and cooling. With compressors and heat exchangers sized for 492 vessels, total electrical draw is large; the OAT SA electricity swing (+$8.9/kg high, −$2.3/kg low at base $0.032/kWh) is ~145× larger than the fructose electricity high swing (+$0.061/kg).

**Summary:** Gas fermentation's MSP is set by the physics of H₂ dissolution, not by biology or price. No realistic improvement to Yxs, μmax, or feedstock price changes the fundamental H₂ solubility constraint that forces the large vessel count and capital cost.

---

## 4. Cross-route sensitivity patterns

The OAT SA tornado charts reveal which parameters matter most for each route and where routes diverge.

### 4.1 Parameters that matter similarly across liquid routes

**Substrate conversion (ε)** is the dominant driver for formate (+65.0%/−27.1%) and a significant secondary driver for fructose and acetate. For formate this is a double penalty under the inhibition constraint: lower ε raises Q (more vessels, more capital) and simultaneously wastes more feedstock. Neither effect existed independently before — they are coupled through the inhibition-constrained X*. For fructose and acetate, ε drives feedstock waste but has minimal capital coupling.

**Feedstock price** is the top driver for fructose (±34.8%) and acetate (±21.6%). For formate it is now second (±20.9% relative, ±$3.237/kg absolute) — the absolute swing is unchanged (same Yxs and price range) but the percentage is lower because the base MSP is $15.51.

**Centrifuge recovery** matters proportionally the same for fructose and acetate (~±5.6%/−3.0–3.1%). Formate matches: +5.6%/−3.0%.

**Nutrients** (±9.2% for acetate, ±5.9% for fructose, ±2.2% for formate) scale with nutrients' fractional share of total MSP. The absolute swing is the same across routes (±$0.341/kg — the recipe is identical) but the percentage varies inversely with base MSP.

### 4.2 Parameters where gas fermentation diverges sharply

**Electricity price:** Liquid routes show ≤1.6% MSP swing; gas fermentation shows +11.0% at the high electricity price — the largest single high-direction swing of any parameter. The electricity demand for 492 large aerated vessels dominates.

**Capital cost (TCI ±35%):** Liquid routes show 2–5% swing; gas fermentation shows −7.1%/+6.2%. No longer the largest-swing parameter for gas fermentation (water recycle and electricity now exceed it).

**Water recycle fraction:** Small for liquid routes (≤8.1%); +8.9%/−5.4% for gas fermentation — the largest total swing range of any parameter for that route. At the scale of 492 vessels, water treatment and recycle flows are large enough that changing the recycle fraction substantially changes the WWT operating cost contribution.

**Restart frequency:** Very small for liquid routes (<0.3%); for gas fermentation the asymmetric swing (+3.4%/−0.4%) reflects the large N+1 redundancy overhead — more restarts mean more time in the spare vessel state, which affects capacity utilization and seed-train sizing.

### 4.3 Parameters that matter very little anywhere

**Ammonia price** (±$0.35–0.75/kg) produces <0.8% swing for all liquid routes and <0.1% for gas fermentation. NH₃ is a minor cost item relative to feedstock and capital at all scales modeled.

**Dilution rate margin** (D_margin 0.70–0.85) produces <1.3% swing for all routes. Within the tested range, changing D_margin slightly adjusts τ and vessel count, but the effect on MSP is small.

---

## 5. Cross-route comparison summary

| Driver | Fructose | Acetate | Formate | Gas ferm |
|--------|---------|---------|---------|---------|
| Primary MSP driver | Feedstock | Feedstock + Capital | ε + Feedstock (inhibition-constrained) | Capital (H₂ solubility) |
| Substrate cost (p/Yxs, $/kg SCP) | $3.63 | $1.44 | $5.83 | $2.14 |
| N_total (vessels) | 4 | 10 | **53** | ~492 |
| Capital sensitivity (TCI ±35%) | ±2.0% | ±4.0% | **±5.1%** | ±7.1% |
| Feedstock sensitivity (±50%) | ±34.8% | ±21.6% | **±20.9%** | ±1.4% |
| ε sensitivity (0.80–0.95) | +10.6%/−4.3% | +37.0%/−2.8% | **+65.0%/−27.1%** | +4.5% (hi only) |

The routes separate into two natural groups:
- **Liquid routes** (fructose, acetate, formate): MSP $4–16/kg, dominated by substrate economics. Feedstock price and Yxs are the primary levers.
- **Gas fermentation**: MSP $80/kg in this base case, dominated by capital from low H₂ aqueous solubility. Feedstock economics are relatively secondary.

The gas fermentation result is a valid base case at standard H₂ electrolysis pricing ($4.83/kg) with standard aerobic bioreactor configurations. Routes using H₂ at lower cost structures (co-located electrolysis, waste H₂) or alternative dissolved-gas delivery configurations (hollow-fiber membranes, higher pressure) would alter the capital structure substantially — those scenarios are outside the battery limits of this model and would require parameter changes or model extensions to evaluate.

---

*All parameter values from `common/parameters.py`. All MSPs and sensitivity swings from `outputs/sensitivity_results.xlsx`. Design calculations from `common/kinetics.py` — see `docs/SCP_Liquid_Route_Math.md` and `docs/SCP_Perfusion_Bioreactor_Math.md` for full derivations.*
