# SCP Gas Fermentation Route — Bioreactor and Process Math

**Document scope:** Gas fermentation route (autotrophic *C. necator* on H₂ + CO₂).
**Last updated:** 2026-08-14
**Companion document:** `SCP_Liquid_Route_Math.md` (fructose, acetate, formate routes)
**Primary implementation:** `models/gas_fermentation_model.py`, `perfusion_bioreactor/unitwithauxiliary.py`, `common/kinetics.py`

This document is written so that a reader familiar with bioprocess engineering can independently reproduce every intermediate value and verify the BioSTEAM model results. It covers the same ground as `SCP_Project_Framework.md §4, §5, §9.5a` but presents all equations together in one place and makes all intermediate calculations explicit.

---

## 1. Overview: the gas fermentation flowsheet

The gas fermentation route differs from the three liquid-substrate routes in four structural ways: H₂ is the electron donor (and cost-driving feedstock) rather than an organic carbon source; dissolved-gas pre-saturation replaces a liquid carbon-source feed tank; a `PerfusionBioreactor` replaces the `ExtentBasedBioreactor`; and UF membrane sterilization replaces heat sterilization for the main media circuit.

```
nutrients_feed → ST102 (StorageTank, 7 days) ─┐
nh3_feed       → ST103 (StorageTank, 7 days) ─┤→ M101 (Mixer, inline — no capital)
water_feed     ──────────────────────────────────┤
recycle_water  ──────────────────────────────────┘
    → UF101 (UltrafiltrationSterilizer — Guo et al. 2014)
    → P101  (Pump, pressurize to 4 atm)
    → SP101 (Splitter: f → DC101; (1−f) → DC102)

h2_feed     → DC101 (DropletColumn, H₂ dissolved at 4 atm) ─┐
co2_o2_feed → DC102 (DropletColumn, O₂+CO₂ dissolved)       ─┤→ MX101 (Mixer)
    → R101  (PerfusionBioreactor, autotrophic C. necator, 4 atm)
         |___________harvest_slurry (biomass-enriched)
    → C101  (SolidsCentrifuge, 95% recovery)
         |___________centrate (→ WWT101)
    → D101  (SprayDryer, 5% final moisture)
         |___________vapor / H₂O (atmospheric emission — NOT WWT feed)
    → ST104 (StorageTank, 7 days — dried SCP product)

WWT path (centrate + seed wastes → WWT101):
    → WWT101 (wastewater Mixer — centrifuge centrate + seed train effluents)
    → WWT102 (_SludgeSettler — 99% organics → sludge; H₂O split for 80% sludge moisture; remaining H₂O → treated water)
    → RCY101 (Splitter — 75% treated H₂O → recycle_water; 25% → discharge)
    → recycle_water (back to M101)

Seed train (heterotrophic fructose basis — see §9):
    ST201/ST202/ST203 → SM101 → SHX101 → SHP101 → SHX102 → SSP101/SSP102
    → SR101 / SR102 / SR103
```

**Battery limits:** Raw feedstocks (H₂, CO₂, O₂, NH₃, water, mineral nutrients) through dried SCP powder. H₂ and CO₂ are assumed on-site generation (no gas storage tanks modeled — conservative FCI underestimate). The gas fermentation route does not produce a CO₂ vent from the bioreactor (CO₂ is consumed, not produced).

---

## 2. Pre-saturation design — Henry's law and DC split fraction

### 2.1 Why pre-saturation is required

H₂ has very low aqueous solubility. At atmospheric pressure, dissolved H₂ ≈ 0.0013 g/L — far too low to sustain meaningful growth. To increase H₂ availability to the bioreactor, the liquid media is pressurized to 4 atm in dedicated droplet column contactors (DC101, DC102) before entering the bioreactor. This is the design choice that sets S_f — the maximum achievable dissolved H₂ at the reactor inlet.

DC101 and DC102 are physically separate vessels to prevent H₂ and O₂ contact in the gas phase (explosion hazard). DC101 carries H₂; DC102 carries CO₂ + O₂.

### 2.2 Henry's law — dissolved gas concentrations at 4 atm

Both values are externally fixed by operating pressure and gas-phase composition. They are module-level constants in `models/gas_fermentation_model.py` (Framework §4a):

| Gas | Symbol | Value at 4 atm | Basis |
|-----|--------|----------------|-------|
| H₂ dissolved | S_f_H2 | 0.0051 g/L | Henry's law, 4 atm, Framework §4a |
| O₂ dissolved | S_f_O2 | 0.11 g/L | DC102 design target, Framework §4a |

S_f_H2 is the parameter that ultimately determines the achievable titer and drives the vessel count — the single most consequential number in this route.

### 2.3 CO₂ dissolved design concentration

CO₂ must be supplied in stoichiometric proportion to O₂ demand. The CO₂ design concentration is computed from the molar stoichiometric ratio (not a separate parameter):

$$
S_{f,\text{CO}_2} = \frac{n_{\text{CO}_2} \cdot \text{MW}_{\text{CO}_2}}{n_{\text{O}_2} \cdot \text{MW}_{\text{O}_2}} \times S_{f,\text{O}_2}
= \frac{4.09 \times 44.01}{6.21 \times 32.00} \times 0.11 = 0.906 \times 0.11 \approx 0.0997 \text{ g/L}
$$

### 2.4 DC split fraction f

The total liquid flow Q is split between DC101 (H₂ side) and DC102 (CO₂ + O₂ side). The split fraction f is derived from stoichiometric parity — DC101 must supply enough dissolved H₂ and DC102 must supply enough dissolved O₂ to meet the bioreactor's demand at the same total cell production rate:

$$
f \cdot S_{f,\text{H}_2} \cdot \frac{1}{g_{\text{H}_2/\text{CDW}}} = (1-f) \cdot S_{f,\text{O}_2} \cdot \frac{1}{g_{\text{O}_2/\text{CDW}}}
$$

Rearranging:

$$
f = \frac{S_{f,\text{O}_2} \cdot g_{\text{H}_2/\text{CDW}}}{S_{f,\text{H}_2} \cdot g_{\text{O}_2/\text{CDW}} + S_{f,\text{O}_2} \cdot g_{\text{H}_2/\text{CDW}}}
$$

The mass stoichiometric ratios $g_{\text{H}_2/\text{CDW}}$ and $g_{\text{O}_2/\text{CDW}}$ are derived from the molar coefficients (see §8):

$$
g_{\text{H}_2/\text{CDW}} = \frac{n_{\text{H}_2} \cdot \text{MW}_{\text{H}_2}}{\text{MW}_{\text{biomass}}} = \frac{21.36 \times 2.016}{97.20} = 0.443 \text{ g H}_2/\text{g CDW}
$$

$$
g_{\text{O}_2/\text{CDW}} = \frac{n_{\text{O}_2} \cdot \text{MW}_{\text{O}_2}}{\text{MW}_{\text{biomass}}} = \frac{6.21 \times 32.00}{97.20} = 2.044 \text{ g O}_2/\text{g CDW}
$$

$$
f = \frac{0.11 \times 0.443}{0.0051 \times 2.044 + 0.11 \times 0.443} = \frac{0.04873}{0.01042 + 0.04873} = \frac{0.04873}{0.05915} = 0.824
$$

82.4% of the liquid flow goes through DC101 (H₂ side); 17.6% through DC102 (CO₂ + O₂ side).

### 2.5 Effective dissolved H₂ at R101 inlet

After DC101 and DC102 recombine in MX101, the dissolved H₂ concentration is diluted by the O₂/CO₂ side (which carries no H₂):

$$
[\text{H}_2]_{\text{inlet}} = f \times S_{f,\text{H}_2} = 0.824 \times 0.0051 = 0.00420 \text{ g/L}
$$

This is the effective S_f that `PerfusionBioreactor._run()` reads from the inlet stream via `_calculate_inlet_S_f()`.

---

## 3. Downstream recovery chain — backward pass

The production target of **25,000 MT/yr** applies to the final SCP product. The backward pass is identical to the liquid routes:

| Step | Unit | Recovery η | Basis |
|------|------|-----------|-------|
| Centrifugation | C101 | 0.95 | Engineering judgment, §9.2 |
| Spray drying | D101 | 1.00 | Solids recovery = 100%; moisture change only |

$$
\dot{m}_{\text{fermenter}} = \frac{25{,}000}{0.95} = 26{,}316 \text{ MT CDW/yr}
$$

---

## 4. Operating hours

$$
h_{\text{eff}} = 8{,}760 - 336 - 672 = 7{,}752 \text{ h/yr} \quad (88.5\%)
$$

Two downtime sources: 336 h/yr plant turnaround (2 weeks) and 672 h/yr contamination restarts (2 × 336 h, staggered). Identical to the liquid routes; all four routes use `effective_operating_hours()` from `common/operating_hours.py`.

---

## 5. CSTR reference design — `design_gas_fermentation_reactor()`

The gas fermentation reactor design uses the same 9-step chain as `design_reactor()` for liquid routes, with one key difference: S_f is fixed externally by Henry's law, so X* is solved **forward** from S_f rather than backward from a target titer. `design_gas_fermentation_reactor()` in `common/kinetics.py` implements this.

### Inputs

| Parameter | Symbol | Value | Source |
|-----------|--------|-------|--------|
| Max specific growth rate | μmax | 0.12 h⁻¹ | Framework §9.1 |
| Biomass yield on H₂ | Yxs | 2.26 g/g | Derived from molar stoichiometry §9.5a |
| Dissolved H₂ feed conc. | S_f | 0.0051 g/L | Henry's law, 4 atm, §4a |
| H₂ conversion extent | ε | 0.99 | Framework §9.2 |
| Dilution rate margin | D_margin | 0.80 | Framework §9.2 |

### Step 5 — Operating dilution rate D and HRT τ

$$
D = D_{\text{margin}} \times \mu_{\max} = 0.80 \times 0.12 = 0.096 \text{ h}^{-1}
$$

$$
\tau = \frac{1}{D} = \frac{1}{0.096} = 10.42 \text{ h}
$$

(For liquid routes, D sets the HRT which drives reactor volume. For gas fermentation, the liquid throughput Q is so large — see below — that this τ yields an enormous total volume. The perfusion section, §6, explains how the bioreactor avoids physically needing all that volume by decoupling SRT from HRT.)

### Step 2 (forward direction) — Achievable titer X*

Because S_f is fixed, X* is solved forward rather than backward:

$$
X^* = Y_{xs} \times S_f \times \varepsilon = 2.26 \times 0.0051 \times 0.99 = 0.01139 \text{ g/L}
$$

This is 2,000× lower than fructose's X* = 24.0 g/L and reflects the physical constraint of H₂ solubility at 4 atm.

### Step 3 — Residual dissolved H₂ S*

$$
S^* = S_f \times (1 - \varepsilon) = 0.0051 \times 0.01 = 0.000051 \text{ g/L}
$$

### Step 6 — Required volumetric throughput Q_design

To deliver 26,316 MT CDW/yr at X* = 0.01139 g/L:

$$
Q_{\text{design}} = \frac{26{,}316 \times 10^6}{7{,}752 \times 0.01139 \times 1{,}000} = \frac{26.316 \times 10^9}{88{,}297} \approx 298{,}000 \text{ m}^3/\text{h}
$$

This is the largest single number in the model. Liquid routes require Q = 142–432 m³/h. Gas fermentation requires Q ≈ 298,000 m³/h — roughly 1,000× more liquid per unit time — entirely because X* is so low.

### Corrected Q for DC split geometry

`design_gas_fermentation_reactor()` computes Q_design assuming all Q carries dissolved H₂ at S_f_H2. But only fraction f = 0.824 of Q passes through DC101; the remaining (1 − f) carries O₂/CO₂ only. After MX101 recombination, [H₂]_inlet = f × S_f_H2 < S_f_H2. To compensate, total process liquid Q must be increased:

$$
Q_{\text{corrected}} = \frac{Q_{\text{design}}}{f} = \frac{298{,}000}{0.824} \approx 361{,}700 \text{ m}^3/\text{h}
$$

Q_corrected drives all liquid feed sizing (water makeup, vessel throughput). Q_design remains the reference for production-proportional quantities (nutrients, NH₃ mass flows).

### Steps 7–9 — CSTR vessel count (reference only)

Using the CSTR formula:

| Quantity | Value |
|----------|-------|
| V_total (CSTR) | 298,000 × 10.42 / 0.80 = 3,882,000 m³ |
| N_capacity (CSTR) | ⌈3,882,000 / 355⌉ = 10,934 |
| N_total (CSTR) | 10,935 |

These CSTR-equivalent numbers are **not used for bioreactor costing**. They represent what would be needed without perfusion. The actual vessel count is computed by `PerfusionBioreactor._run()` using perfusion kinetics (§6). The CSTR design values are used only for pre-simulation seed-train sizing cross-checks.

---

## 6. Perfusion kinetics and operating point

Perfusion decouples the cell residence time (SRT = 1/μ) from the hydraulic residence time (HRT = 1/D_perf). By retaining cells in the reactor via an internal centrifuge, cell density can far exceed the CSTR limit at the same S_f.

### 6.1 Herbert-Pirt yield and maintenance model

The Herbert-Pirt model accounts for both growth-associated and maintenance-associated H₂ consumption. Parameters (Framework §9.5a):

$$
Y_{\text{mol}} = \frac{\text{MW}_{\text{biomass}}}{n_{\text{H}_2}} = \frac{97.20}{21.36} = 4.551 \text{ g CDW/mol H}_2
$$

$$
Y_{\text{max}} = \frac{Y_{\text{mol}}}{\text{MW}_{\text{H}_2}} = \frac{4.551}{2.016} = 2.257 \text{ g CDW/g H}_2 \approx Y_{xs} = 2.26
$$

For this route, m_s_mol = 0 (no maintenance cost assumed — Framework §9.5a). Therefore:

$$
Y_{\text{obs}} = Y_{\text{max}}, \quad q_s = \frac{\mu}{Y_{\text{max}}} = \frac{0.096}{2.257} = 0.04253 \text{ g H}_2/\text{g CDW/h}
$$

### 6.2 Perfusion dilution rates

Operating growth rate μ_op = D_margin × μmax = **0.096 h⁻¹** (same as CSTR D).

The direct bleed is a fraction of μ, removing cells without the centrifuge:

$$
D_b = \text{bleed\_fraction} \times \mu_{\text{op}} = 0.20 \times 0.096 = 0.0192 \text{ h}^{-1}
$$

The centrifuge-path (perfusion) dilution rate is derived from the steady-state cell balance (production = losses):

$$
\mu = (1 - \eta) D_{\text{perf}} + D_b
$$

$$
D_{\text{perf}} = \frac{\mu_{\text{op}} - D_b}{1 - \eta} = \frac{0.096 - 0.0192}{1 - 0.97} = \frac{0.0768}{0.03} = 2.560 \text{ h}^{-1}
$$

The perfusion HRT is therefore:

$$
\text{HRT} = \frac{1}{D_{\text{perf}}} = \frac{1}{2.560} = 0.391 \text{ h}
$$

Compared to SRT = 1/μ = 10.42 h. The ratio SRT/HRT = 26.7 represents the cell enrichment factor that perfusion achieves over a simple CSTR.

### 6.3 Achievable cell density

With S_f_inlet = 0.00420 g/L (effective after MX101) and S* ≈ 0:

$$
X_{\text{perf}} = \frac{D_{\text{perf}} \times S_{f,\text{inlet}} \times \varepsilon}{q_s} = \frac{2.560 \times 0.00420 \times 0.99}{0.04253} \approx 0.250 \text{ g/L}
$$

| Design | Cell density | Ratio |
|--------|-------------|-------|
| CSTR (S_f only) | X* = 0.0114 g/L | 1× |
| Perfusion (this model) | X ≈ 0.250 g/L | ~22× |

Perfusion achieves ~22× the CSTR cell density. This is the entire rationale for the perfusion design — without it, vessel count would be ~10,934 rather than ~499.

### 6.4 Volumetric productivity

$$
\text{Productivity} = \mu_{\text{op}} \times X_{\text{perf}} = 0.096 \times 0.250 = 0.0240 \text{ g CDW/L/h}
$$

### 6.5 Internal flow topology — the perfusion loop

`PerfusionBioreactor` models a closed cell-recycle loop. From BioSTEAM's perspective R101 has one external inlet (`combined_feed`, from MX101) and one external outlet (`harvest_slurry`). The internal centrifuge, bleed splitter, and cake return are auxiliary units within the BioSTEAM unit boundary — they are invisible to the system-level flowsheet.

Internally, per vessel at steady state:

```
combined_feed (F_in at S_f_fresh)
        │
        ├─← cake recycle (F_cake at S)   ← internal return from centrifuge
        ↓
  ┌──────────────────────────────────┐
  │  Reactor (V_max, density X,      │
  │           substrate conc. S)     │
  └──────────────────────────────────┘
        │                        │
  F (centrifuge path)         F_b (bleed path)
        ↓                        ↓
  Centrifuge            ╌╌→ harvest_slurry
  ├─ cake (F_cake, cells + water at S) → back to reactor inlet (internal)
  └─ supernatant (F_super1, no cells, at S) → harvest_slurry
```

Notation (all quantities per individual vessel):

| Symbol | Meaning | Units |
|--------|---------|-------|
| F | Centrifuge-path throughput | L/h |
| F_b | Bleed flow rate | L/h |
| F_total | Total reactor liquid throughput = F + F_b | L/h |
| F_cake | Wet-cake recycle (cells + moisture water, internal) | L/h |
| F_super1 | Centrifuge supernatant (liquid, no cells) | L/h |
| F_in | Fresh external feed = F_total − F_cake | L/h |
| F_harvest | External outlet = F_super1 + F_b = F_in | L/h |
| S_f_fresh | Fresh feed H₂ concentration (= [H₂]_inlet, §2.5) | g/L |
| S | Residual H₂ in reactor and all effluents | g/L |
| S_f_mixed | H₂ in combined reactor feed (fresh + cake recycle) | g/L |

**Flow conservation (external boundary):** F_in = F_harvest. The cake is internal — it crosses no BioSTEAM system boundary.

**Flow balance (`_solve_flow_balance()`):** At steady state the cell balance (growth = loss via supernatant + bleed) gives:

$$
F = \frac{F_{\text{total/vessel}} - \mu \cdot V_{\max}}{\eta}
$$

$$
F_b = F_{\text{total/vessel}} - F
$$

where F_total/vessel = Q_corrected × 1000 / N. Both F and F_b must be positive; `PerfusionBioreactor._run()` raises `RuntimeError` if infeasible.

For the current design (N = 499, Q_corrected = 361,700 m³/h):

$$F_{\text{total/vessel}} = \frac{361{,}700{,}000}{499} \approx 724{,}850 \text{ L/h}$$

$$F = \frac{724{,}850 - 0.096 \times 284{,}000}{0.97} = \frac{697{,}586}{0.97} \approx 719{,}160 \text{ L/h}$$

$$F_b = 724{,}850 - 719{,}160 \approx 5{,}690 \text{ L/h}$$

$$D_{\text{actual}} = F / V_{\max} \approx 2.53 \text{ h}^{-1}$$

The R101 design sheet reports D ≈ 2.54 h⁻¹ and F ≈ 720,000 L/h; the small differences from this hand calculation reflect iterative convergence of X_final within `_run()`.

### 6.6 Mixed-feed substrate concentration — S_f_mixed

The wet cake returned from the internal centrifuge carries liquid at the reactor's residual H₂ concentration S. When this cake rejoins the fresh feed, the substrate entering the reactor is diluted:

$$
S_{f,\text{mixed}} = \frac{F_{\text{in}} \times S_{f,\text{fresh}} + F_{\text{cake}} \times S}{F_{\text{total}}}
$$

Since S = S_f_mixed × (1 − ε) (residual after conversion ε), substituting and solving:

$$
S_{f,\text{mixed}} = \frac{F_{\text{in}} \times S_{f,\text{fresh}}}{F_{\text{in}} + \varepsilon \times F_{\text{cake}}}
$$

F_cake is a small biomass-concentrated flow (the cake is mostly cells, not bulk liquid), so S_f_mixed ≈ S_f_fresh. The difference is small but propagates into the final X_final and actual_conversion calculations in `_run()`.

### 6.7 Two H₂ conversion metrics — ε and actual_conversion

**ε** (`conversion` parameter, set to 0.99) defines the per-pass substrate utilization within the centrifuge circuit:

$$
S = S_{f,\text{mixed}} \times (1 - \varepsilon) \quad \text{(residual H}_2\text{ in reactor and all effluents)}
$$

This is the design intent: 99% of H₂ in the combined reactor feed (fresh + cake) is consumed on each pass through the centrifuge loop.

**`actual_conversion`** is the overall H₂ utilization relative to the total H₂ entering the full reactor circuit (F_total × S_f_mixed), computed from the mass balance:

$$
X_{\text{actual}} = \frac{H_{2,\text{consumed}}}{H_{2,\text{available}}} = \frac{H_{2,\text{consumed}}}{F_{\text{total}} \times S_{f,\text{mixed}}}
$$

Substituting the expression for H₂ consumed, with m_s = 0 so q_s = μ/Y_max = μ × g_{\text{H}_2/\text{CDW}}:

$$
H_{2,\text{consumed}} = g_{\text{H}_2/\text{CDW}} \times \mu \times X_{\text{final}} \times V_{\max}
$$

$$
X_{\text{final}} = \frac{D_{\text{actual}} \times \varepsilon \times S_{f,\text{mixed}}}{q_s}
= \frac{D_{\text{actual}} \times \varepsilon \times S_{f,\text{mixed}} \times Y_{\max}}{\mu}
$$

Since $g_{\text{H}_2/\text{CDW}} \times Y_{\max} = 1$ by definition:

$$
H_{2,\text{consumed}} = D_{\text{actual}} \times S_{f,\text{mixed}} \times \varepsilon \times V_{\max}
$$

Therefore:

$$
\boxed{X_{\text{actual}} = \varepsilon \times \frac{D_{\text{actual}} \times V_{\max}}{F_{\text{total}}} = \varepsilon \times \frac{F}{F + F_b} = \varepsilon \times \frac{D_{\text{actual}}}{D_{\text{actual}} + D_b}}
$$

For the current design (D_actual ≈ 2.54 h⁻¹, D_b = 0.0192 h⁻¹):

$$
X_{\text{actual}} = 0.99 \times \frac{2.54}{2.54 + 0.0192} = 0.99 \times 0.9925 = 0.982 = \textbf{98.2\%}
$$

This matches the "H2 conversion (%)" entry in the R101 design results exactly.

**Physical interpretation:** The bleed stream (F_b ≈ 5,690 L/h per vessel) exits the reactor at concentration S with unconsumed H₂ — it bypasses the centrifuge entirely. The bleed is required to prevent unbounded cell accumulation (a 100% recycle system is unstable). It constitutes D_b/(D_actual + D_b) = 0.0192/2.559 = 0.75% of throughput. That 0.75% exits carrying H₂ at concentration S rather than being further consumed, reducing overall H₂ utilization from 99% → 98.2%.

Changing the bleed fraction parameter changes actual_conversion: a smaller bleed fraction moves actual_conversion closer to ε but increases the sensitivity of cell density to transients. The formula above quantifies the exact trade-off.

**Note:** This formula holds exactly only when m_s_mol = 0 (the current Framework §9.5a assumption for *C. necator*). When m_s > 0 the substitution $g_{\text{H}_2/\text{CDW}} \times Y_{\max} = 1$ no longer holds, and actual_conversion depends additionally on maintenance relative to growth.

### 6.8 Outlet stream composition — R101 system-boundary mass balance

`harvest_slurry` (the external outlet) is computed in `_run()` by:

1. `copy_like(combined_feed)` — inherits the full inlet composition for every chemical species
2. Subtract consumed species, add products — scaled to all N parallel vessels:

| Component | Modification (kg/h, all N vessels) |
|-----------|-------------------------------------|
| H₂ | − H2_consumed_final × N / 1000 |
| O₂ | − O2_consumed_final × N / 1000 |
| CO₂ | − CO2_consumed_final × N / 1000 |
| NH₃ | − NH3_consumed_final × N / 1000 |
| Nutrients | − Nutrients_consumed_final × N / 1000 |
| H₂O | + H2O_produced_final × N / 1000 |
| CNecatorBiomass | + CDW_produced_final × N / 1000 |

All species not listed (dissolved minerals, etc.) pass through unchanged. `max(0, …)` guards prevent negative mass from feedstock shortfalls.

**Residual H₂ in outlet** (from design results "Residual substrate S"):

$$
[\text{H}_2]_{\text{out}} = S_{\text{mixed}} = S_{f,\text{mixed}} \times (1 - X_{\text{actual}})
\approx 0.00420 \times (1 - 0.982) = 7.6 \times 10^{-5} \text{ g/L}
$$

This matches R101 "Residual substrate S" = 7.42 × 10⁻⁵ g H₂/L in the design results.

**Harvest biomass concentration** (from design results "Harvest cell density"):

$$
X_{\text{harvest}} = \frac{\text{cell\_to\_super1} + \text{cell\_bleed}}{F_{\text{super1}} + F_b} = \frac{(1-\eta) \cdot F \cdot X + F_b \cdot X}{F_{\text{harvest}}}
$$

At the design point this gives X_harvest ≈ 0.009 g/L — very dilute, which is why C101 (the downstream centrifuge) must process the full Q_corrected to concentrate the biomass for spray drying.

---

## 7. Parallel scaling — vessel count

### 7.1 Flow-based N

Each vessel can process at most F_max = D_perf × V_max_L L/h of liquid:

$$
F_{\max} = D_{\text{perf}} \times V_{\max,L} = 2.560 \times 284{,}000 = 727{,}040 \text{ L/h per vessel}
$$

Required total flow = Q_corrected × 1000 = 361,700 m³/h × 1000 = 361,700,000 L/h:

$$
N_{\text{flow}} = \left\lceil \frac{361{,}700{,}000}{727{,}040} \right\rceil = \left\lceil 498 \right\rceil = 498
$$

### 7.2 Target-based N

Independent check: how many vessels are needed to produce 26,316 MT CDW/yr at CDW_per_vessel = μ_op × X × V_max_L?

$$
\text{CDW per vessel} = 0.096 \times 0.250 \times 284{,}000 = 6{,}816 \text{ g CDW/h}
$$

$$
\dot{m}_{\text{adj}} = \frac{26{,}316 \times 10^6}{7{,}752} = 3{,}394{,}734 \text{ g CDW/h}
$$

$$
N_{\text{target}} = \left\lceil \frac{3{,}394{,}734}{6{,}816} \right\rceil = 498
$$

### 7.3 Final vessel count with N+1 redundancy

`PerfusionBioreactor._run()` takes the maximum of flow-based and target-based N, then adds N+1 redundancy:

$$
N_{\text{capacity}} = \max(N_{\text{flow}}, N_{\text{target}}) = 498
$$

$$
N_{\text{total}} = 498 + 1 = 499
$$

The simulation output is **499** (minor differences from this hand calculation reflect floating-point arithmetic and iterative recalculation of X_final using the solved D_actual after `_solve_flow_balance()`).

**For comparison:**

| Route | N_total | Primary driver |
|-------|---------|----------------|
| Fructose | 4 | High μmax, high X* |
| Acetate | 10 | Moderate μmax, lower X* |
| Formate | **53** | Moderate μmax, inhibition-constrained X* = 1.62 g/L (S\*\_max = 3.0 g/L — Grunwald 2015) |
| Gas ferm | ~499 | Very low X* from H₂ solubility limit |

Gas fermentation needs ~9× more vessels than the next most capital-intensive liquid route (formate, N_total = 53), even with perfusion. (499 / 53 ≈ 9.4×.) Prior to the inhibition constraint, formate was ~12 vessels and the ratio was ~41×.

---

## 8. Autotrophic growth stoichiometry

Gas fermentation does not use Roels' degree-of-reduction method (which applies when the carbon source and electron donor are the same molecule). For lithoautotrophic growth on H₂ + CO₂, the stoichiometry comes directly from the literature molar equation (Framework §9.5a). The module-level constants in `common/kinetics.py`:

| Coefficient | Symbol | Value | Meaning |
|-------------|--------|-------|---------|
| GAS_FERM_N_H2 | n_H2 | 21.36 mol/mol biomass | H₂ consumed per mol CDW |
| GAS_FERM_N_O2 | n_O2 | 6.21 mol/mol biomass | O₂ consumed per mol CDW |
| GAS_FERM_N_CO2 | n_CO2 | 4.09 mol/mol biomass | CO₂ consumed per mol CDW |
| GAS_FERM_N_NH3 | n_NH3 | 0.76 mol/mol biomass | NH₃ consumed per mol CDW |
| GAS_FERM_N_H2O | n_H2O | 18.70 mol/mol biomass | H₂O produced per mol CDW |

Biomass formula: C₄.₀₉H₇.₁₃O₁.₈₉N₀.₇₆, MW = 97.20 g/mol.

### 8.1 Mass stoichiometric ratios (g per g CDW)

These are computed in `PerfusionBioreactor._calculate_stoichiometric_ratios()` and `models/gas_fermentation_model.py`:

$$
g_i/\text{CDW} = \frac{n_i \times \text{MW}_i}{\text{MW}_{\text{biomass}}}
$$

| Component | Molar n | MW (g/mol) | g / g CDW |
|-----------|---------|-----------|----------|
| H₂ (consumed) | 21.36 | 2.016 | 21.36×2.016/97.20 = **0.443** |
| O₂ (consumed) | 6.21 | 32.00 | 6.21×32.00/97.20 = **2.044** |
| CO₂ (consumed) | 4.09 | 44.01 | 4.09×44.01/97.20 = **1.852** |
| NH₃ (consumed) | 0.76 | 17.03 | 0.76×17.03/97.20 = **0.133** |
| H₂O (produced) | 18.70 | 18.02 | 18.70×18.02/97.20 = **3.467** |

### 8.2 Mass reaction equation per g H₂

The `build_autotrophic_growth_reaction()` function in `common/kinetics.py` expresses the reaction on a per-g-H₂ basis (H₂ is the BioSTEAM reactant). The Yxs check: 1 / g_H2_per_gCDW = 1 / 0.443 = 2.257 g CDW/g H₂, confirming Yxs = 2.26.

The balanced mass equation per g H₂ consumed (with X = ε = 0.99):

```
H₂ + 4.609 O₂ + 4.179 CO₂ + 0.300 NH₃ + 0.878 Nutrients
    → 2.257 CNecatorBiomass + 7.818 H₂O
```

CO₂ and O₂ appear on the reactant side (both consumed). There is no CO₂ vent from the gas fermentation bioreactor — this is the key mass balance difference from all three liquid routes.

### 8.3 Net water production

The large n_H2O = 18.70 mol/mol biomass means the autotrophic route produces substantial water:

$$
g_{\text{H}_2\text{O}} = 3.467 \text{ g H}_2\text{O per g CDW}
$$

The recycle loop must maintain a purge fraction (25% of WWT treated water) to prevent unbounded water accumulation. At 75% recycle, the recycle loop is a contraction mapping (gain = 0.75 < 1) and converges.

---

## 9. Feed stream sizing

Feed mass flows are computed before the BioSTEAM simulation to seed the recycle loop and pre-size streams.

| Stream | Derivation | Formula |
|--------|------------|---------|
| H₂ feed (kg/h) | DC101 dissolves H₂ into f×Q liquid | h2_kgh = f × Q_corr × S_f_H2 |
| O₂ feed (kg/h) | DC102 dissolves O₂ into (1−f)×Q liquid | o2_kgh = (1−f) × Q_corr × S_f_O2 |
| CO₂ feed (kg/h) | DC102 dissolves CO₂ into (1−f)×Q liquid | co2_kgh = (1−f) × Q_corr × S_f_CO2 |
| H₂ compressor (CP101) | Atm → 4.5 atm, η = 0.70 | bst.IsentropicCompressor, P = 4.5 × 101 325 Pa |
| CO₂/O₂ compressor (CP102) | Atm → 4.5 atm, η = 0.70 | bst.IsentropicCompressor, P = 4.5 × 101 325 Pa |
| H₂ aftercooler (HX101) | CP101 outlet (~250 °C) → 30 °C | bst.HXutility, cool_only=True, T = 303.15 K |
| CO₂/O₂ aftercooler (HX102) | CP102 outlet (~200 °C) → 30 °C | bst.HXutility, cool_only=True, T = 303.15 K |
| Nutrients (kg/h) | Proportional to X* at Q_design | nutrient_coeff × X* × Q_design |
| NH₃ (kg/h) | Proportional to H₂ consumed at Q_design | nh3_wt × S_f_H2 × ε × Q_design |
| Water makeup (kg/h) | Q_corr is the water throughput; water_kgh = Q_corr × 1000; makeup = water_kgh − recycle_ss | Q_corr×1000 − recycle_ss |

**Note:** Nutrients and NH₃ are proportional to Q_design (production-proportional), while the gas feeds and water are proportional to Q_corrected (water throughput). The distinction matters because Q_corrected = Q_design / f ≈ 1.196 × Q_design. Solutes (nutrients, NH₃, dissolved gases) are mass added on top of the water — `water_kgh = Q_corr × 1000` exactly, not reduced by solute masses.

The water makeup is computed from an analytical steady-state recycle estimate to seed the recycle tear stream before BioSTEAM's iterative convergence.

---

## 10. Seed train

### 10.1 Why fructose (not H₂)

The seed bioreactors (SR101–SR103) use **fructose as the carbon source** for heterotrophic seed culture, not H₂. Two reasons (user-confirmed 2026-08-07):

1. Dissolved H₂ at atmospheric pressure (≪ 0.001 g/L) is too dilute to sustain meaningful growth without pressurization.
2. `SeedBioreactor` (a `bst.AeratedBioreactor` subclass) is not a pressure vessel and cannot safely operate at 4 atm.

*C. necator* is a facultative chemolithoautotroph — it can grow heterotrophically on fructose. The seed culture transitions to autotrophic H₂-oxidizing growth at production scale.

The seed media design follows the fructose production route parameters (μmax = 0.22, Yxs = 0.32, ε = 0.90).

### 10.2 Seed stage volumes

Stage working volumes are 5% of the next larger stage (INOCULUM_RATIO = 0.05):

$$
V_{\text{work},i} = V_{\text{work,prod}} \times 0.05^{4-i}
$$

where V_work_prod = V_max × V_wf = 355 × 0.80 = 284 m³ per production vessel.

| Stage | Reactor | Volume |
|-------|---------|--------|
| 1 (smallest) | SR101 | 284 × 0.05³ = **0.0355 m³** (35.5 L) |
| 2 | SR102 | 284 × 0.05² = **0.710 m³** (710 L) |
| 3 (largest) | SR103 | 284 × 0.05¹ = **14.2 m³** |

### 10.3 Number of concurrent seed trains

With N_total ≈ 499 vessels, 2 restarts/yr each, and SEED_BATCH_DURATION_H = 72 h:

$$
N_{\text{seed\_trains}} = \left\lceil \frac{499 \times 2 \times 72}{7{,}752} \right\rceil = \left\lceil \frac{71{,}856}{7{,}752} \right\rceil = \lceil 9.27 \rceil = 10
$$

Gas fermentation requires ~10 concurrent seed trains, vs. 1 for each liquid route. This reflects the large vessel count requiring many simultaneous restart events.

### 10.4 Seed train topology and τ_seed

Identical topology to liquid routes (SM101 → SHX101 → SHP101 → SHX102 → SSP101/SSP102 → SR101/102/103). The steady-state τ_seed:

$$
\tau_{\text{seed}} = \frac{h_{\text{eff}}}{N_{\text{total}} \times \text{RESTARTS\_PER\_YEAR}} = \frac{7{,}752}{499 \times 2} = 7.77 \text{ h}
$$

This τ_seed is used in `SeedBioreactor._init()` so BioSTEAM assigns a working volume matching the batch operating volume of each stage.

---

## 11. UF sterilization

Gas fermentation uses **ultrafiltration (UF) membrane sterilization** in place of heat sterilization (HX101/HX102) used by the liquid routes. This is UF101 (`UltrafiltrationSterilizer` from `common/sterilization.py`).

Rationale: Heat sterilization requires high temperatures (134 °C) then cooling before inoculation. At gas fermentation's Q ≈ 361,700 m³/h, heat sterilization would require enormous heat exchangers. UF membranes sterilize at ambient temperature and pressure via physical size exclusion and are validated for continuous sterile media preparation at large scale (Guo et al. 2014 Water Sci. Technol.).

At the TEA level, UF101 is a pass-through unit (no reaction, no composition change). Capital and O&M costs are computed from the Guo et al. (2014) correlations and added to FOC.

---

## 12. Wastewater treatment

Identical to liquid routes (`build_wastewater_treatment()`):

- **WWT101:** inline Mixer combining centrifuge centrate + seed wastes (D101 vapor is atmospheric emission, not a WWT feed)
- **WWT102:** 99% organics removal; H₂O split to maintain 80% sludge moisture (WWT_SLUDGE_MOISTURE); remaining H₂O → treated water
- **RCY101:** 75% water recycle; 25% purge prevents unbounded H₂O accumulation

The gas fermentation route produces net H₂O from the autotrophic reaction (3.467 g H₂O per g CDW). At 75% recycle, the recycle loop is still a contraction mapping — the 25% purge removes more water per cycle than production adds, guaranteeing convergence.

---

## 13. Techno-economic analysis

Identical financial structure to liquid routes (Turton BM method: FCI = 1.18 × Σ(C_P × f_BM), WC = 17.6% FCI, 20 yr plant life, IRR 10%, income tax 35%, MACRS7 depreciation). See `SCP_Liquid_Route_Math.md §9`.

**Known limitation — centrifuge capital underestimate:** BioSTEAM's `SolidsCentrifuge` sizes capital from a solids-loading-rate correlation. At gas fermentation's harvest biomass concentration of ~0.009 g/L, the correlation extrapolates to near-zero capital (~$187K total for all centrifuges combined), which is physically meaningless at Q ≈ 361,700 m³/h. A volumetric-throughput basis (e.g., vendor disc-stack centrifuge specs) would give a substantially higher C101 cost. The centrifuge capital is a known underestimate for this route; the C101 FCI contribution in the results should be interpreted with this caveat.

---

## 14. Reading the outputs

### Key metrics — `gas_fermentation_results.xlsx` → Executive Summary

| Metric | Expected range | Notes |
|--------|---------------|-------|
| MSP ($/kg SCP) | $80.19 | Dominated by capital (WWT, vessels) |
| FCI ($M) | Very large | ~499 vessels at V_max = 355 m³ each |
| Capital charge ($/kg SCP) | Largest single OPEX category | Reflects high N_total |
| Electricity ($/kg SCP) | Very large | Aeration + cooling for ~499 vessels |

### Checking R101 design — Equipment sheet

- R101 row: N (parallel) should be ~499.
- Reactor volume per unit: V_max = 284,000 L working volume per vessel.
- Perfusion dilution rate D: ~2.56 h⁻¹ (not 0.096 h⁻¹ — the CSTR HRT is not directly reported).
- Cell density X: ~0.25 g/L (vs. CSTR X* ~0.011 g/L — perfusion enrichment visible here).

### Checking mass balance — Mass Balance sheet

- H₂: non-zero input; output = residual (S* × Q, very small). Closure < 100% (consumed).
- O₂: input from DC102; output ≈ 0 (consumed, no vent O₂).
- CO₂: non-zero input (consumed as carbon source); output ≈ 0. **No CO₂ vent** from this route.
- H₂O: large net output — autotrophic growth produces water. Closure > 100% expected.
- N₂: does not appear (no air fed; pure H₂ and O₂ are separate feeds).

### Checking year-by-year economics — Cash Flow sheet

The Cash Flow sheet (sheet 8 in `gas_fermentation_results.xlsx`) contains the full year-by-year table from `tea.get_cashflow_table()`. Key columns:

| Column | What to check |
|--------|--------------|
| Depreciable capital / Fixed capital investment | Pre-startup years only; sums to FCI × construction schedule (40%/60%) |
| Working capital | Appears in year −1 (pre-startup); recovered in final year |
| Depreciation | MACRS7 applied to FCI; front-loaded in years 1–8, then zero |
| Annual operating cost | Constant across operating years; matches Operating Costs sheet totals |
| Sales | Revenue from SCP product stream at MSP × annual production |
| Forwarded losses | Cumulative tax losses carried forward (gas fermentation capital-intensity means these persist longer than liquid routes) |
| Cash flow | Net cash each year; discount factor spot-check: year 1 ≈ 0.909 at 10% IRR |
| Cumulative NPV | Converges to ≈ 0 at end of plant life (by construction — MSP achieves this) |

---

## 15. Common questions

**Q: Why does gas fermentation have ~499 vessels when liquid routes need only 4–53?**

Two compounding factors. First, X* = 0.01139 g/L (CSTR design) is ~2,000× lower than fructose's X* = 24.0 g/L, and ~14× lower than the formate route's inhibition-constrained X* = 1.62 g/L. This means the bioreactor must process far more liquid per unit of biomass output than any liquid route. Perfusion reduces this by ~22× (to ~499 vessels) by retaining cells and achieving X ≈ 0.250 g/L. Without perfusion, the CSTR-equivalent count would be ~10,935. The remaining ~499 are irreducible at this pressure and at current H₂ electrolysis pricing — they are the consequence of physics (H₂ solubility), not biology or economics.

Note: The formate route's N_total was revised from 12 to 53 by adding a substrate inhibition constraint (S\*\_max = 3.0 g/L from Grunwald et al. 2015). The gas fermentation comparison holds: ~499 vs. 53 (formate) = ~9.4× still a large gap driven by H₂ solubility physics.

**Q: Why is there no CO₂ vent for gas fermentation when all three liquid routes produce a CO₂ vent?**

In the liquid routes, the carbon substrate (fructose, acetate, formate) is oxidized to CO₂ via aerobic respiration — CO₂ is a reaction product. In gas fermentation, CO₂ is the carbon source — it is consumed by *C. necator* via the Calvin cycle. The autotrophic stoichiometry shows n_CO2 = 4.09 mol CO₂ consumed per mol biomass. Net CO₂ balance is negative (consumed > produced at all modeled conditions).

**Q: Why is the seed train on fructose instead of H₂?**

H₂ at atmospheric pressure yields [H₂]_dissolved ≪ 0.001 g/L — effectively zero available substrate. The `SeedBioreactor` is an open aerated vessel and cannot be operated at the 4 atm required to dissolve H₂ to 0.005 g/L. Fructose seed culture is the standard industrial practice for *C. necator* — the organism grows heterotrophically during seed preparation and switches to autotrophic H₂-oxidation at production scale. Fructose kinetic parameters for the seed design come from the fructose production route entry in `common/parameters.py`.

**Q: The nutrient recipe is the same as liquid routes, but the media is almost pure water at gas fermentation's Q. Is that physically meaningful?**

The nutrients concentration entering R101 is ~0.004 g/L (nutrients_kgh / Q × 1000), compared to ~7 g/L in liquid routes. The feed is effectively dilute mineral water. This is physically consistent — the nutrient consumption rate (g/h) is proportional to the CDW production rate, which is the same 26,316 MT/yr as the liquid routes. The same grams of nutrients are consumed per gram of CDW; they are just dissolved in a much larger liquid volume.

**Q: Why does gas fermentation have 10 seed trains when liquid routes have only 1?**

N_seed_trains scales with N_total × RESTARTS_PER_YEAR × SEED_BATCH_DURATION_H / h_eff. For liquid routes (N_total = 4–12), one seed train is never "busy" with two overlapping restart events simultaneously. For gas fermentation (N_total ≈ 499), 499 × 2 = 998 restart events per year happen, averaging one restart every 7.8 h — shorter than the 72 h seed batch. Multiple concurrent restarts require multiple concurrent seed trains.

---

*All equations implemented in `common/kinetics.py` (`design_gas_fermentation_reactor`, `build_autotrophic_growth_reaction`, GAS_FERM_N_* constants), `perfusion_bioreactor/unitwithauxiliary.py` (`PerfusionBioreactor`), and `models/gas_fermentation_model.py`. Framework §4, §4a, §5, §6, §9.1, §9.2, §9.5a.*
