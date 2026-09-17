# Single-Cell Protein TEA/LCA Comparative Study — Project Framework & Assumptions Register

*Last updated: 2026-09-02*

## 1. Objective

Compare the technical and economic viability of producing single-cell protein (SCP) from
CO2-derived feedstocks (gas fermentation, formate, acetate) against a conventional sugar-fed
benchmark (fructose), using a common host organism, common battery limits, and a common
evaluation framework, such that differences in final MSP/GWP reflect real process physics
rather than inconsistent modeling assumptions.

## 2. Scope

- **Host organism:** *Cupriavidus necator* across **all four** routes, including fructose.
- **Production capacity:** fixed at **25,000 MT/yr** SCP for all four routes.
- **Battery limits:** matched to the Intelligen/SuperPro benchmark (Misailidis, Ferreira &
  Petrides, Jan 2024; Vlaeminck et al. 2023, *Fermentation* 9:771) — feedstock storage and
  sterilization, fermentation, cell mass recovery & drying, and aerobic wastewater treatment.
  All four routes carry identical battery limits. **No ammonia recovery and no anaerobic digestion
  are modeled** — deliberate scope simplifications.
  **Implementation: `common/wastewater.py`, custom 3-unit system** (not
  `bst.create_conventional_wastewater_treatment_system()`):
  - WWT101 (`bst.Mixer`): combines centrifuge centrate and seed train effluents into a single
    mixed wastewater feed. Spray-dryer vapor (D101 `outs[0]`) is a direct atmospheric emission —
    not a WWT feed. Zero capital.
  - WWT102 (`_SludgeSettler`, custom `bst.Unit` subclass): 99 % organic removal, aerobic
    treatment representation only — no anaerobic digestion, no biogas. Non-H₂O components routed
    99 % to sludge (outs[1]); H₂O split to maintain 80 % sludge moisture
    (H₂O_to_sludge = 0.80/0.20 × dry_sludge_mass). Sludge priced at −$0.066/kg wet
    (= −$0.33/kg dry organic, §9.4) so BioSTEAM deducts WWT operating cost from VOC. Zero capital.
  - RCY101 (`bst.Splitter`): 75 % of treated water recycled to process feed (M101 inlet);
    25 % discharged. Zero capital.
  Streams are manually wired per route (no `autopopulate`). Outputs: wet sludge and
  treated-water discharge only.
- **Build order:** fructose (template/validation case) → formate & acetate (parallel — structurally
  similar, soluble-intermediate routes) → gas fermentation (hardest case, dissolved-gas limited).

## 3. Common Modeling Standards

- **Economic basis:** single fixed dollar-year, CEPCI, plant location/utility rates, financing
  assumptions (IRR target, tax rate, plant life, depreciation schedule) — shared across all four
  models, actual values tracked in Section 9's Parameter Registry.
- **Costing method:** shared BioSTEAM costing correlations for common equipment types
  (centrifuges, dryers, tanks, etc.) so the same unit type isn't costed differently across models.
- **No target-fitting rule:** no parameter is adjusted to make MSP hit a preconceived number.
  A route that comes out at $200/kg is a result, not a bug to be tuned away. Auto-generated
  documentation must not assert viability/competitiveness conclusions — it reports numbers only.
- **Validation checkpoint:** before trusting any model's output, sanity-check against the
  SuperPro/Intelligen benchmark ($3.93/kg, 20,000 MT/yr gas-fed acetate-intermediate process)
  and against literature-reported titers/growth rates for the specific substrate.

## 3a. TEA Implementation

**Class: `bst.TEA` subclass, one override required.** Checked from source: `bst.TEA` is an
abstract-ish base class, but `_DPI`, `_TDC`, `_FCI` all have working default implementations
compatible with a simple Lang-factor approach, and `_fill_tax_and_incentives` also defaults
sensibly (`tax = income_tax × taxable_cashflow`). Only **`_FOC` (fixed operating cost) has no
default** and must be overridden — confirmed, not assumed.

**Decision: adopt the `ConventionalEthanolTEA` pattern** (`biorefineries/tea/conventional_ethanol_tea.py`,
citing Huang, Long & Singh 2016, *Biofuels, Bioprod. Bioref.* 10(3):299–315) as the template for our
own `SCPTEA` — a real, published, more granular structure than an invented decomposition, and it
comes with free itemized reporting (`CAPEX_table()`, `FOC_table()` methods) matching this project's
no-lumped-numbers standard. Not ethanol-specific mechanically — only its default parameter values
are tuned for a sugarcane biorefinery; the structure itself is generic:
```python
def _FOC(self, FCI):
    return (FCI*(self.property_tax + self.property_insurance
                 + self.maintenance + self.administration)
            + self.labor_cost*(1 + self.fringe_benefits + self.supplies))
```
Six cost categories, each independently sourced (Section 9) rather than blended: `labor_cost`
($/yr total), `fringe_benefits` (fraction of labor), `supplies` (fraction of labor), `property_tax`
(fraction of FCI), `property_insurance` (fraction of FCI), `maintenance` (fraction of FCI),
`administration` (fraction of FCI). The reference implementation's sugarcane-biorefinery defaults
(property_tax=0.001, property_insurance=0.005, supplies=0.20, maintenance=0.01, administration=0.005,
fringe_benefits=0.4) are a useful sanity-check starting point, not values to assume directly for
SCP production — need verification/adjustment for this context (Section 9).

**MSP solving mechanism:** `tea.solve_price(product_stream)` — finds the SCP product price that
zeroes NPV at the target IRR (Section 9.4: 10%/yr). Despite the name, this is **not** an
iterative price search. It performs a single analytical solve: (1) compute `price2cost` = total
discounted production volume Σ(F_mass × op_hours / (1+IRR)^t); (2) call `solve_sales()` to find
the additional annual revenue needed to bring NPV from its current value (at product price = 0)
to zero; (3) return `MSP = 0 + solve_sales_result / price2cost`. The product stream price is **not
modified** — it remains 0 after the call. `export.py`'s `_build_cashflow_table()` sets the stream
price to MSP temporarily before calling `tea.get_cashflow_table()` and restores it afterward, so
the Cash Flow sheet correctly reflects the MSP scenario (cumulative NPV → 0 at end of plant life).

**Shared settings, concretely:** one factory function (`common/economics.py`) takes a shared
`EconomicBasis` record (Section 9: dollar-year, CEPCI, IRR, tax rate, plant life, depreciation
schedule, and the six FOC categories above) and a route's `System` object, returning a configured
`SCPTEA` instance. All four routes call the same factory with the same `EconomicBasis` — this is
what "shared TEA settings" concretely means in code, not a single TEA object shared across routes
(each route still gets its own TEA instance, tied to its own System).

**Byproducts — anaerobic digestion / biogas:** AD is **not modeled**. The WWT subsystem
(`common/wastewater.py`) represents aerobic treatment only — the `_SludgeSettler` (WWT102)
removes 99 % of organics to a sludge stream; there is no anaerobic stage and no biogas stream
exists anywhere in any of the four models (Section 2). Adding AD would require a new unit and a
new biogas stream — it is not a pre-existing stream that could be cheaply priced in later.



## 4. Bioreactor Configuration

**Decision: continuous, single-stage (not cascaded), across all four routes.**

- Matches the SuperPro precedent (continuous airlift + continuous aerobic fermentors) and the
  perfusion framework already developed for gas fermentation (April 2026 session).
- Fructose: continuous chemostat, single-pass, no recycle.
- Acetate / formate: continuous chemostat, single-pass, no recycle. **Finalized** (supersedes the
  "TBD" framing below) — mirrors the SuperPro precedent directly: <cite index="1-1">their aerobic
  *C. necator* stage runs broth straight from the fermentors to cell mass recovery with no recycle
  stream</cite>, only their upstream CO→acetate airlift stage uses recycle. Recycle's mechanistic
  role is decoupling cell retention time from hydraulic retention time — useful when substrate
  *delivery rate* is the bottleneck. For the liquid routes the bottleneck is intracellular/
  enzymatic uptake kinetics (Monod/Haldane), not delivery, so recycle isn't the lever that manages
  inhibition — dilution rate D is (see Section 5). No recycle equipment modeled for these three
  routes.
- Gas fermentation: continuous **with cell recycle (perfusion)** — the only route using it. Feed
  gas is fully pre-saturated upstream (droplet contactors at 4 atm — full unit design in Section 4a),
  fixing the feed dissolved-H2 concentration S_f at 0.0051 g/L *before*
  the bioreactor ever sees it. **Correction (superseding the original April framing):** because
  dissolution is fully resolved upstream, the bioreactor itself has no in-situ gas-to-liquid mass
  transfer problem — no kLa/OTR physics happens inside this vessel; that engineering lives entirely
  at the droplet contactors (Section 4a). The bioreactor's kinetics are therefore structurally the *same kind* of problem
  as the three liquid routes (Section 5's extent/D-margin method applies), just run in the opposite
  direction: for the liquid routes, feed concentration S0 is a design choice solved backward from a
  target titer; here, **S_f is fixed externally by Henry's law, not a design choice**, so the
  achievable titer is solved forward instead: X\* = Yxs·S_f·ε. The real reason recycle is required
  is that S_f is so low that a single-pass reactor would yield a vanishingly small titer regardless
  of residence time — **recycle decouples cell retention time (SRT) from hydraulic residence time
  (HRT)**, allowing a high volumetric throughput of dilute feed (short HRT) while still retaining
  cells long enough (long SRT) to build useful density. This is a cleaner and more accurate
  justification than the original "can't shorten HRT without shortchanging dissolution" framing,
  which conflated the dissolver's physics with the bioreactor's.
- Known tradeoff for the three single-pass chemostats, to be stated explicitly in the writeup: a
  single well-mixed continuous stage cannot reach complete conversion (steady-state residual
  substrate S* is always > 0). Higher throughput (D → μmax) means more substrate leakage to the
  wastewater section. Accepted as consistent with the single-stage SuperPro precedent rather than
  resolved with a multi-stage cascade.

## 4a. Pre-Saturation Unit Block (Gas Fermentation Only)

**Purpose:** Dissolve H2, CO2, and O2 into liquid fermentation media before it enters the
PerfusionBioreactor. The bioreactor receives a liquid stream with pre-dissolved gases — no in-situ
gas sparging occurs inside the vessel (Section 4). All units from the contactor inlets through the
centrifuge (C101) operate at 4 atm.

**Process order (gas fermentation route only):**
```
nutrients/NH3/water feeds
    → storage tanks → M101 (MixTank)
    → UF101 (UltrafiltrationSterilizer — membrane sterilization, Guo et al. 2014)
    → P101 (pump, atmospheric → 4 atm)
    → SP101 (Splitter — fraction f to H2 contactor set; (1−f) to CO2/O2 contactor set)
        ┌────────────────────────────────────────────────────────────────────────────────────────┐
        CP101 (H2 compressor, atm → 4.5 atm)      CP102 (CO2/O2 compressor, atm → 4.5 atm)
        HX101 (H2 aftercooler, ~250 °C → 30 °C)   HX102 (CO2/O2 aftercooler, ~200 °C → 30 °C)
        DC101 set (H2 contactors)                  DC102 set (CO2/O2 contactors)
        └────────────────────────────────────────────────────────────────────────────────────────┘
    → MX101 (Mixer — inline blending, zero capital)
    → PerfusionBioreactor(s)
```

**Sterilization design — gas fermentation route uses UF, not heat (UF101):**
The gas fermentation route replaces the HX101/HX102 heat sterilization block (used in the
fructose, acetate, and formate routes and the seed train) with an ultrafiltration membrane
sterilizer (UF101, `UltrafiltrationSterilizer`). Rationale: at the very high volumetric
throughputs (Q on the order of thousands of m³/h) driven by the low dissolved-H2 titer,
heating this entire liquid stream to 134 °C and cooling it back to 30 °C would impose a
disproportionate steam and cooling-water utility burden and large heat exchanger capital,
neither of which is appropriate as a sterilization instrument at the scale forced by Henry's
law constraints. UF membrane sterilization achieves equivalent sterility assurance (bacteria
and endospores removed by size exclusion through 0.1–0.2 µm membranes) without the thermal
duty. Capital and annual O&M are costed from Guo, Englehardt & Wu (2014) *Water Sci. Technol.*
WST-EM13819R1, Table 1 / §2.5 (power-law regressions as a function of capacity in m³/d, in
2012 USD). The unit numbers up at Q_max = 378,500 m³/d per module (top of the Guo et al.
validated capacity range). Capital cost is CEPCI-escalated to the project dollar year and
divided by `contingency_fee_factor` (= 1.18; BM factor = 1.0 for a plain `bst.Unit`) so that
the TEA's FCI contribution = 1.18 × installed_cost = 1.18 × (purchase_cost × 1.0) recovers the
Guo et al. total installed capital. Annual O&M is similarly CEPCI-escalated and added to
the fixed operating cost via `SCPTEA._FOC()` (the `uf_om` term, summed over all units with
an `annual_om_usd` attribute — zero for the three liquid routes and seed train).

**Caveats:** (1) Guo et al. data are from municipal and industrial water/wastewater reuse
applications — not bioprocess media sterilization. The unit processes (cross-flow UF,
polysulfone or PVDF membranes, CIP-able skids) are physically identical, but capital/O&M
norms for pharmaceutical-grade bioprocess UF skids may differ. This is stated as a
recognized extrapolation, not a validated bioprocess design. (2) The gas fermentation
route's corrected Q (≈ Q_CSTR / f ≈ several thousand m³/h) substantially exceeds the
378,500 m³/d validated range top for a single module, so N_UF_units will be large; the
numbered-up design is consistent with distributed modular UF skid arrangements but
represents a large capital concentration that should be flagged in any writeup.

UF101 operates at atmospheric pressure before P101, consistent with the liquid routes'
sterilization placement. P101 pressurizes to 4 atm (`_P_PRE_SAT_ATM = 4.0`), matching the
droplet column operating pressure.

CP101 and CP102 compress the H2 and CO2/O2 feeds from atmospheric (assumed on-site generation
exit pressure) to 4.5 atm — 0.5 atm above the 4 atm column operating pressure, sufficient
to drive gas into the pressurised liquid. η = 0.70 (BioSTEAM IsentropicCompressor default).

HX101 and HX102 (bst.HXutility, cool_only=True) cool the compressed gases from compressor
outlet temperature (~250 °C for H2, ~200 °C for CO2/O2 at η = 0.70) back to T_FERMENTATION_K
= 30 °C before entering the droplet columns. BioSTEAM assigns chilled water utility (target
T = 30 °C < cooling water supply T = 32.2 °C). T_FERMENTATION_K is the existing Framework
§9.2 constant — no new parameter introduced.

**Why two separate contactor sets:** H2 and O2 must not contact each other in the gas phase
(explosion hazard). H2 is dissolved in a dedicated column set; O2 and CO2 are dissolved together
in a separate set. Mixing of the two dissolved-gas streams occurs only in the liquid phase (MX101),
where no ignition risk exists.

**Column design (both sets — same vessel dimensions):**

| Parameter | Value |
|---|---|
| Type | Droplet column (liquid dispersed in gas phase) |
| Height | 4 m |
| Diameter | 10 m |
| Operating pressure | 4 atm |
| Max liquid throughput per column | 0.58 m³/s |
| Costing method | Vertical pressure vessel (not packed-tower or absorber correlations) |

**Gas balance — closed vessel, no vent:** each column is sealed. The only exit for gas is dissolved
in the liquid-phase outlet. Gas feed flow rate (kg/h) = dissolved gas flow rate in the liquid outlet
(outlet concentration × liquid flow rate). No recirculation loop; no purge stream.

**H2 contactor set (DC101):**
- Gas feed: H2 at 4 atm partial pressure; price = $4.83/kg (Section 9.4)
- Dissolved H2 in liquid outlet: **S_f(H2) = 0.0051 g/L**
- H2 feed rate (kg/h) = 0.0051 [g/L] × Q_H2_side [m³/s] × 3600 [s/h] × (1 m³ = 1000 L) / 1000 [g/kg]
  = 0.0051 × Q_H2_side × 3.6 kg/h [with Q in m³/s]

**CO2/O2 contactor set (DC102):**
- Gas feed: CO2 at 0.1 atm partial pressure + O2 at 3.9 atm partial pressure = 4 atm total
- Dissolved O2 in liquid outlet: **S_f(O2) = 0.11 g/L** (DC102 design target); price = $0/kg (Section 9.4)
- Dissolved CO2 in liquid outlet: **S_f(CO2) ≈ 0.0996 g/L** (computed from stoich ratio × S_f(O2); see §9.5a); price = $0/kg (Section 9.4)
- CO2 feed rate = 0.0996 × Q_CO2O2_side × 3.6 kg/h; O2 feed rate = 0.11 × Q_CO2O2_side × 3.6 kg/h

**Flow split — always computed, never hardcoded:**

Total liquid media flow Q (from `design_gas_fermentation_reactor`, Section 5) is split between the
two contactor sets in the ratio determined by the growth reaction's stoichiometric mass consumption
coefficients. Let f = fraction of Q routed to the H2 contactor set:

```
f = (S_f(O2) × g_H2_per_gCDW) / (S_f(H2) × g_O2_per_gCDW + S_f(O2) × g_H2_per_gCDW)
  = (0.11 × 0.4430) / (0.0051 × 2.044 + 0.11 × 0.4430)  ≈ 0.824

Q_H2_side    = f × Q      (m³/s)
Q_CO2O2_side = (1 − f) × Q
```

The split targets stoichiometric H2:O2 delivery parity — O2 is the binding constraint at DC102
because S_f(CO2) is set by construction to the stoichiometric ratio × S_f(O2), so CO2 and O2
are always delivered in exact stoichiometric proportion (see CO2:O2 check below). Values of
`g_H2_per_gCDW` (= 0.4430) and `g_O2_per_gCDW` (= 2.044) are derived from the literature molar
equation (Section 9.5a).

**Q sizing correction — DC split dilutes H2 at the reactor inlet:**

`design_gas_fermentation_reactor` (Section 5) sizes Q using S_f(H2) = 0.0051 g/L as if the full
liquid flow enters the bioreactor at that H2 concentration. In practice, after MX101 recombines the
two contactor streams:

```
[H2]_reactor_inlet = f × S_f(H2) = 0.824 × 0.0051 ≈ 0.00420 g/L
```

The (1−f) fraction carries O2/CO2 only — no H2. This dilution means the reactor delivers less H2
per unit Q than the CSTR sizing assumed. The model builder (`gas_fermentation_model.py`, step 5c-i)
applies a correction factor before all volumetric sizing:

```
Q_design  = Q_CSTR                    (CSTR basis — proportional to production target)
Q         = Q_design / f              (corrected total process liquid; ≈ 1.214 × Q_CSTR for f = 0.824)
```

This restores the H2 delivery rate and ensures each perfusion vessel receives sufficient liquid to
operate at D_perf. Q is used for all volumetric sizing (vessel counts, water makeup feed,
gas feed to DC101/DC102); Q_design is retained as the reference for production-proportional
quantities (nutrients and NH3 feed rates, which scale with CDW output, not total liquid flow).

**CO2:O2 stoichiometric ratio — satisfied by construction:** S_f(CO2) is computed as
`stoich_ratio × S_f(O2)` where stoich_ratio = g_CO2_per_gCDW / g_O2_per_gCDW = 1.851 / 2.044 =
**0.906** (§9.5a). The DC102 dissolved CO2:O2 mass ratio is therefore 0.0996 / 0.11 = 0.906 —
identically equal to the stoichiometric requirement, by construction. CO2 and O2 are delivered in
exact stoichiometric proportion; neither is in excess. O2 is the binding constraint for the flow
split (DC101 supplies H2; DC102 supplies the O2 that limits f). If a future revision changes S_f(O2)
independently of this derived relationship, S_f(CO2) must remain computed (not hardcoded) from the
same stoich_ratio to preserve consistency.

**Number of parallel columns — computed at build time:**

```
N_H2     = ceil(Q_H2_side    / 0.58)   [Q in m³/s]
N_CO2O2  = ceil(Q_CO2O2_side / 0.58)
```

Each set of N parallel columns is costed as N pressure vessels of the stated geometry using
BioSTEAM's pressure vessel cost correlations.

**Post-saturation mixing (MX101):** a `bst.Mixer` (inline blending, zero capital) combines the
dissolved-H2 stream and the dissolved-CO2/O2 stream before the perfusion bioreactor. At gas
fermentation throughput (Q ≈ 357,000 m³/h), blending two fully-miscible liquid streams is
instantaneous. A MixTank at this Q would require thousands of parallel 30 m³ vessels
(BioSTEAM MixTank V_max limit) — not a realistic plant design.

**Autotrophic growth reaction stoichiometry — resolved (Section 9.5a):** derived mass coefficients
per g CDW: g_H2 = 0.4430, g_O2 = 2.044, g_CO2 = 1.851, g_NH3 = 0.1331. Implementation requires
a dedicated `build_autotrophic_growth_reaction` function in `common/kinetics.py` (separate from
`compute_O2_CO2_H2O_coefficients`, which applies Roels' degree-of-reduction method and is
heterotrophic-only — it raises `ValueError` for substrates with no carbon). See §9.5a for the
full molar equation and derivation.

## 5. Growth Rate Data & Reactor Design

**Principle:** full Monod/Haldane kinetics (requiring Ks, and Ki for the inhibited substrates) is
**not used** as the default methodology. Reliable Ks values are not available even for fructose —
the best-supported substrate — as established in conversation: two independent batch datasets both
produced unidentifiable or nonphysical Ks fits when regressed, and SuperPro's own benchmark also
asserts conversion outright with no kinetic derivation at all for either of its fermentation
stages. Chasing a fully resolved kinetic model is not a viable default given what data actually
exists in the literature for this organism.

**What's actually used instead — only two numbers per route, both realistically sourceable:**
- **μmax** — sets the dilution rate via a conservative margin, not a precise operating point.
- **Yxs (biomass yield on substrate)** — does double duty, described below. Not just a check value.

Ks and Ki are **not required** for the default design method. If either ever turns up from a
reliable source for a given route, that route alone can be upgraded to a full μ(S\*)=D kinetic
solve without touching the other three routes' methodology — this is an optional upgrade path, not
a requirement, and not pursued further in this document.

Reported maximum titer (a third, separately-sourced number, not a kinetic parameter) is used only
as a validation ceiling — see step 2 below — not as a design input.

**Yxs's role is not just a sanity check — it directly sets the reaction stoichiometry.** Once
target titer and conversion extent fix the substrate feed concentration (step 3 below), Yxs *is*
the biomass:substrate mass ratio that goes straight into the `Reaction`/elemental-balance object
already established for the CHNO core growth reaction (Section 7) — the same coefficient used to
size the stoichiometric consumption of carbon source and, downstream of that, ammonia and O2. This
is the one piece of "kinetic" data that the mass-balance layer actually consumes directly; μmax
never enters the stoichiometry at all, it only sets D.

### Downstream Recovery Chain (backward pass, run before the forward design chain)

**The problem this solves:** 25,000 MT/yr (Section 2) is a target on *final packaged SCP product*
— after cell mass recovery, drying, and any other downstream losses — not on fermenter output.
Feeding 25,000 MT/yr directly into the forward design chain below as if it were the fermenter's
target would under-build the fermenter, since downstream battery-limit steps (Section 2) discard
some mass before the product is done.

**This is not the same problem as the old models' feed/production-target conflict, and does not
need an iterative solve.** The April `PerfusionBioreactor`'s `_apply_production_target_scaling`
patched two independently-computed vessel counts together with `max()` because feed rate and
production target were derived separately and reconciled after the fact — a real circularity. Our
forward design chain below doesn't have that problem structurally, since target production is the
*starting input* and everything else is derived forward from it in one pass. The residual issue is
narrower: the *target itself* needs adjusting for a fixed downstream recovery factor before the
forward chain runs, not solved iteratively against it.

**Why a closed-form backward pass is sufficient:** every downstream loss in the battery limits
(centrifuge/cell-separation recovery efficiency, drying moisture spec, any other fixed-efficiency
step) is an asserted, flow-rate-independent efficiency — not a function of scale. That makes total
downstream recovery a fixed multiplicative factor, computable once, upfront, by walking the
battery limits backward from final product to fermenter output:

```
required_fermenter_CDW_output = target_final_product (25,000 MT/yr)
                                  ÷ η_centrifuge_recovery
                                  ÷ (1 − drying_moisture_loss_fraction)
                                  ÷ (any other fixed downstream recovery step, per route)
```

That adjusted number — not the raw 25,000 MT/yr — is what feeds into step 6 of the forward chain
below (Q = target mass rate ÷ X\*). Implemented once as a shared utility function, called
identically by all four models, since the backward-pass logic itself doesn't vary by route (only
the specific chain of downstream units and their efficiencies does).

**Expected, one-directional overshoot — not a sign of the same problem:** rounding vessel count N
up to the next integer (Section: Reactor Design Chain, step 8) means built capacity lands slightly
*above* the adjusted target. This composes cleanly with N+1 redundancy (Section 5a) and is not
circularity — just expected rounding.

**Only genuine case requiring an iterative solve (not expected, but worth checking per unit as
each model is built):** if any downstream unit's efficiency is itself a function of scale or flow
rate, rather than a flat asserted fraction. All downstream efficiencies specified so far in this
framework are flat/asserted, so this shouldn't arise — flag immediately if it does.

### Reactor Design Chain (conservative-D, extent-based)

1. **Conversion extent (ε), chosen directly, not derived.** A single explicit assumption
   (e.g. ε = 0.85–0.95), logged with its justification per route. ε is the *only* knob governing
   conversion — residual substrate is a consequence of it, not a second independent assumption
   layered on top (an earlier draft of this section did exactly that, inconsistently — corrected).
2. **Target titer (X\*)**, chosen as a defensible fraction of the best literature-reported titer
   for that substrate/organism — a validation ceiling, not an input derived from kinetics.
   **Fed-batch titers are preferred over batch titers as the reference, when available** — batch
   titer is capped by single-dose substrate exposure (the same exposure pattern that drives the
   inhibition seen in the acetate/formate literature), a strategy this design doesn't use; fed-batch
   avoids that by metering substrate in over time, closer in spirit to the low standing
   concentration our chemostat design maintains. Fed-batch titers can still run somewhat higher than
   an equivalent continuous steady state would sustain (no continuous outflow removing biomass), so
   treat it as a ceiling to fraction down from, not a guaranteed achievable target — see Section 9
   for detailed guidance on sourcing this correctly from batch vs. fed-batch vs. continuous data.

   **Step 2 (inhibition branch):** If `S_star_max` is defined for the route (§9.1 validation
   reference table; code: `RouteParams.S_star_max`), also compute
   X\*\_inhibition = Yxs × ε × S\*\_max / (1−ε) — the maximum titer compatible with
   S\* ≤ S\*\_max in a perfectly mixed CSTR. Use X\* = min(X\*\_titer, X\*\_inhibition).
   When the ceiling is binding, S0 and S\* back-calculate from the chosen X\* (steps 3–4
   algebra unchanged). When not binding (e.g. acetate: X\*\_inhibition = 12.15 g/L >
   X\*\_titer = 11.25 g/L), the titer-forward result stands and S\* < S\*\_max is
   automatically satisfied. For the formate route, the ceiling is binding:
   X\*\_inhibition = 1.62 g/L < X\*\_titer = 7.875 g/L, so formate uses X\* = 1.62 g/L
   and S\* = 3.0 g/L (= S\*\_max exactly). Implemented in `design_reactor()` — §5.

3. **Feed concentration, consistent with both 1 and 2:** S0 = X\* / (Yxs·ε).
4. **Residual substrate falls out automatically:** S\* = S0·(1−ε) — feeds the wastewater-treatment
   load (Section 2 battery limits) as a real consequence of ε, not an independently asserted number.
5. **Dilution rate (D) — final decision: 0.8·μmax.** Sourced from a chemostat productivity-margin
   reference (bioprocesstools.com, cited in Section 9.2), which states 70–85% of μmax as the
   optimal range for maximum biomass productivity — 0.8 sits in the middle of that range. **Closed
   decision, not open for re-litigation:** an earlier draft of this section cited "0.3–0.5·μmax"
   to an unverifiable Bailey & Ollis reference and argued for a more conservative margin given
   uncertain μmax values; that citation was retracted as unverifiable, the tradeoff was explicitly
   discussed, and 0.8·μmax was deliberately chosen and confirmed by the user regardless. Logged
   here so this doesn't get re-argued from stale text elsewhere in the document.
6. **Required throughput (Q):** adjusted fermenter-output target (from the Downstream Recovery
   Chain above, *not* the raw 25,000 MT/yr) ÷ 7,752 h/yr effective operating hours
   (Section 5a-Operating-Hours below) ÷ X\*.
7. **Reactor volume:** D = Q/V by definition, so V_total = Q/D directly — residence time τ = 1/D
   is already fixed by this same relationship, not a second constraint to reconcile.
8. **Vessel count from practical size limits — genuinely automatic inside BioSTEAM, verified from
   source (`abstract_stirred_tank_reactor.py`).** When `self.N` is left `None`, `_design()` solves
   N_capacity = ceil(V_total/V_max) itself, from the unit's actual inlet flow rate and `tau` — a
   single deterministic pass each time `_design()` runs, not an iterative resimulation. `V_total`
   here is computed by BioSTEAM as `F_vol · tau / V_wf`; we only need to supply the correct total
   feed flow rate (from Q, step 6) and `tau = 1/D` (step 5). No vessel-counting logic needs to be
   hand-coded on our end for this part.
9. **N+1 redundancy is a separate, explicit override — not something BioSTEAM knows about or
   solves.** Confirmed from the same source: if `self.N` is manually set (not left `None`),
   `_design()` skips the auto-solve entirely and just uses `V_reactor = V_total/self.N` directly,
   with no V_max check in that branch. Correct sequence: let (or replicate) the auto-solve to get
   N_capacity, then **explicitly set `self.N = N_capacity + 1`** before the real `_design()` call —
   one literal additional whole vessel of spare capacity, not a percentage inflation of volume.
   This is the reliability/uptime decision (Section 5a-Operating-Hours/Section 6, contamination-
   restart coverage) layered on top of BioSTEAM's own sizing math, using BioSTEAM's own supported
   mechanism for it (manual `N` override) rather than custom logic.
10. **Validation check: S\* (residual/standing substrate concentration, step 4) against
    literature-reported safe/inhibitory concentration — not S0.** S0 is a nominal feed strength;
    S\* is the concentration cells actually experience continuously, the physiologically relevant
    number. Compare S\* against whatever concentration range the literature shows the organism
    actually tolerates for that substrate (Section 9's guidance on what counts as a usable
    reference number for this check, given how differently batch/fed-batch/continuous studies
    report concentration). If S\* falls outside a demonstrated-safe range, the ε assumption (step 1)
    is suspect and should be revisited — this is the same category of check that raised skepticism
    about SuperPro's 14 g/L acetate titer originally, now made an explicit, required step rather
    than something done ad hoc.

**What this honestly gives up:** exact predictive power over residual substrate and conversion at
a given D — that precision genuinely requires Ks. **What it gains:** every number in the chain
derives consistently from one small set of stated assumptions (ε, X* margin, D margin), rather
than three independent, unrelated constants (residence time, conversion efficiency, titer) with no
relationship between them — the actual defect being corrected from the old models.

**Implementation:** the reactor subclass's `_run()` (built on `AeratedBioreactor`, Section 5b) sets
conversion = ε directly and asserts D = margin·μmax — same class structure originally planned,
different internal method, no Monod/Haldane function inside it.

**Batch-derived μmax/Yxs carried over to continuous design is itself an assumption, not a
guarantee** — log this per route; batch culture history/byproduct accumulation can differ from
continuous steady-state behavior (already flagged for fructose specifically in conversation).

**Gas fermentation is no longer a full exception, following the pre-dissolution correction
(Section 4)** — since in-situ mass transfer isn't a bioreactor-level problem here (it's resolved
upstream at the droplet contactors, Section 4a), this route uses the *same* extent/D-margin design method as the three
liquid routes, just run in the opposite direction: S_f (feed dissolved-H2 concentration) is fixed
externally by Henry's law, not a design choice, so achievable titer is solved forward instead of
feed concentration being solved backward from a target titer — X\* = Yxs·S_f·ε rather than
S0 = X\*/(Yxs·ε). Still uses the perfusion/CSPR-based sizing framework built in April 2026, and
still needs its own μmax (autotrophic H2-oxidizing growth) and Yxs sourced independently — not
assumed equal to any liquid-route value. Full governing equations for the perfusion bioreactor are
documented separately (see companion document, `SCP_Perfusion_Bioreactor_Math.md`).

**Sourcing note:** all μmax/Yxs/titer values and citations are sourced and verified by the user
directly, not by Claude — an earlier pass in this conversation included a confirmed citation error
(Belfares et al. 1995 was mischaracterized as an acetate-inhibition source; it is not), so no
AI-sourced numeric value should be treated as verified anywhere in this document.

## 5a. Operating Hours & Redundancy

Two distinct, non-overlapping downtime sources, derived from first principles rather than a
generic "350 operating days/yr" default (our derived number **replaces** that convention — it is
not stacked on top of it):

- **Plant-wide turnaround:** all lines down simultaneously for periodic inspection/cleaning at
  scale, independent of any contamination event. Assumed 2 weeks/yr = 336 h/yr.
- **Per-line contamination restart:** independent/uncorrelated across lines (Section 6), staggered
  rather than coincident with the plant turnaround. **Updated to match the finalized restart-
  frequency decision (Section 6/9.2): 2 restarts/yr (6-month campaigns, Cauldron-based), each
  costing 336 h — i.e. 672 h/yr per line, not the earlier 336 h/yr placeholder this section
  originally used before that decision was made.** (Section 6's seed-train formula was already
  correctly updated to this 2-restarts/yr basis; this operating-hours figure had not been —
  corrected here so the two stay consistent.)

Effective per-line operating hours: 8,760 − 336 − 672 = **7,752 h/yr (~88.5% uptime)**.

**Redundancy decision: N+1.** Since 25,000 MT/yr is a fixed hard target across all four routes
(Section 2), production capacity is sized so that aggregate output holds at 25,000 MT/yr even
while one line is down for its contamination restart — i.e., one additional production line beyond
what the average-smoothed 88.5% math alone would require. This is consistent with the standby-unit
precedent already present in the SuperPro benchmark (e.g., its ion exchanger is specified with a
standby unit, "1/0/1" quantity notation).

**Implication for line count:** the number of parallel production lines must be resolved jointly
from (a) single-line volumetric capacity from the kinetics (Section 5) at 7,752 h/yr effective
operation, and (b) +1 line for redundancy — not simply target production ÷ single-line nameplate
capacity ÷ 8,760 h.

### 5b. Oxygen Transfer — `bst.AeratedBioreactor`

All three single-pass chemostat routes (fructose, acetate, formate) use `bst.AeratedBioreactor`
as the production reactor base class, not plain `bst.CSTR`. Confirmed from source
(`biosteam.units.stirred_tank_reactor`): this class exists specifically to satisfy the oxygen
mass-transfer requirement of the reaction's mass balance — it solves for required air flow and
agitator/compressor power (via a real, citable kLa correlation, default `method='Riet'` for
stirred tanks) given the reaction's O2 demand, defaults to continuous operation, and **fails
loudly (`ValueError`) rather than silently if the required OTR is physically unreachable at any
air flow rate** (e.g., titer too high for the vessel/correlation to support) — consistent with the
fail-loud principle already required for the Haldane low-S-root/max-D check.

**Division of responsibility, extending the Reactor Design Chain (Section 5):**
- **Kinetics/conversion layer (corrected — was stale):** custom `_run()` override sets
  conversion = ε directly and asserts D = margin·μmax (the extent-based default method,
  Section 5) — **not** a μ(S\*)=D Monod/Haldane solve. An earlier draft of this bullet still
  described the abandoned Ks-dependent method; corrected here to match Section 5's actual default.
  The optional Ks-based upgrade path (Section 5) remains available per-route if reliable Ks/Ki
  values are ever found, but is not the default assumed anywhere in this document.
- **O2 demand:** *not* a separate kinetic model — confirmed directly from source, OUR is computed
  straight from the reaction's stoichiometric O2 consumption (`OUR = -effluent.get_flow('mol/s',
  'O2')`) once conversion is known. This is where the CHNO degree-of-reduction O2 coefficient
  (Section 7) actually gets used.
- **O2 delivery design (new, inherited from BioSTEAM):** `AeratedBioreactor`'s design routine
  solves for air flow / agitator power to meet that OUR via the kLa correlation, and costs the
  compressor/air-cooler auxiliary units automatically. `theta_O2` (target dissolved-O2 saturation
  fraction, default 0.5) is the O2-side analog of choosing D on the substrate side — a real design
  lever, not left at default without checking it against literature.

**Required joint-feasibility check (not automatic):** since OUR scales with biomass concentration
X, a D chosen purely to satisfy substrate-side inhibition constraints (Section 5) could still be
infeasible for O2 delivery at scale. The two layers must be checked together per route/scale, not
assumed to resolve independently.

**Scope:** applies only to the three liquid-substrate routes. Gas fermentation's O2 (along with
H2/CO2) is already dissolved into the feed upstream at the pre-saturation dissolver (Section 4) —
the `PerfusionBioreactor` does not sparge air and does not use this class.

**Decision (closed, not an open item): `theta_O2` left at the BioSTEAM default (0.5).** A literature
critical-DO2 value for *C. necator* to formally validate this setpoint was not pursued — a
deliberate scope decision, not an unexamined gap left standing. If O2 limitation is ever suspected
in a route's results (e.g. an implausible titer or a joint-feasibility failure per the
`AeratedBioreactor` fail-loud check above), this is the first assumption to revisit.

## 6. Seed Train / Startup Accounting (continuous system)

Contamination risk in continuous fermentation is a documented, real phenomenon — not modeled
in the SuperPro benchmark or in most published continuous-fermentation TEAs, which apply a
blanket scheduled-maintenance operating-hours discount (~330–350 days/yr) that does not
distinguish planned CIP downtime from contamination-driven restarts.

**Working assumption (flagged as engineering judgment, not a measured value for this specific
process — no literature source exists for *C. necator* SCP campaign length specifically):**
- ~1 contamination-driven restart **per production line** per year, anchored loosely to general
  industrial fermentation failure-rate literature (~2%/yr batch loss rate; ~1 batch lost per
  40–51 weeks at commercial biopharma scale; 1-in-10 bioreactors contaminated over a 15-yr
  industrial dataset).
- Each restart: 1–2 week (336 h) reacclimation/production-loss window on the affected line.

**Ordering dependency (new — corrects an under-specified assumption):** seed train sizing must run
*after* Section 5's forward design chain produces N_total (the total production line count,
including the N+1 redundancy line — redundancy does not exempt a line from contamination risk, it
only means another line covers output while the affected one restarts). Seed train accounting
cannot be computed independently of Section 5's output.

**Corrected total annual seed-train operating time — final basis: real continuous-fermentation
operational data, superseding both the earlier deterministic placeholder and the batch-
failure-rate probability (Section 9.2 tracks this history).** The BioPlan Associates batch-failure
survey was tried and rejected as a basis: it measures per-batch failure rates in batch-oriented
biopharma manufacturing, and — as directly confirmed — its facility-level "one batch lost every
40–51 weeks" statistic says nothing about how long a *continuous* fermentation campaign can run;
applying it here required an unsupported reinterpretation. Replaced with an actual continuous-
fermentation operating data point: Cauldron (Stansfield, reported in AgFunderNews, March 2024)
ran a 10,000 L continuous production system for over eight months without contamination or
genetic drift — real, industrially-relevant-scale evidence, not a survey average. Locked-in
assumption: **6-month campaign length (a stated margin below the 8-month achieved result), giving
2 restarts/year per line** — deterministic, not probabilistic:
```
restarts_per_year_per_line = 12 / 6 = 2
total_annual_restart_events = N_total × 2
seed_train_operating_hours  = N_total × 2 × 336 h/yr
```
**Caveats, stated explicitly rather than silently accepted:** this is a single company's best
publicized result, not a statistical average across many facilities/runs — real risk of survivorship/
PR bias in what gets reported. Product/organism context isn't specified in the source, so
transferring the duration to *C. necator* SCP production is an assumption, not a proven match.
Given that no *C. necator*-specific or SCP-specific continuous-campaign data exists, this is the
best available anchor, not a fully validated number — the 6-month (vs. 8-month) choice is the
stated hedge against that uncertainty.

**Accounting treatment:**
1. **Capital:** seed train (shake flask → seed fermenter → pilot stage) sized once, capable of
   serially inoculating multiple parallel production reactors (staggered starts) — not one seed
   train per production line as in the old batch models.
2. **Seed train opex:** annual operating hours = N_total × 2 × 336 h/yr (corrected above), a
   deterministic assumption from real operational data, not an arbitrary placeholder — media/
   utility/labor consumption scaled accordingly.
3. **Production derate:** affected production reactor's effective annual operating hours reduced
   by the reacclimation window, per restart event (expected value, same probability basis).

**Open item, not yet resolved:** as N_total grows, the probability of two lines' independent,
randomly-timed restarts overlapping stops being negligible — either extending one line's downtime
via queuing for the seed train, or requiring some parallel seed-train capacity. Low-probability
edge case at small N_total; revisit once real N_total is known from Section 5, not resolved by the
simple multiplication above alone.

## 7. Feed Composition / Nutrients

**Core growth reaction (CHNO):** carbon source, ammonia, and O2 as reactants; biomass, CO2, and
H2O as products — a full elemental balance in the same style as the SuperPro stoichiometries
(e.g. `60.05 Acetic Acid + 3.58 Ammonia + 26.88 O2 → 27.14 C. Necator + 40.05 CO2 + 24.32 Water`).
Ammonia is not a "nutrient" in the costing-table sense — it's a reactant fixed by elemental balance
against the `CNecatorBiomass` formula (C4.09H7.13O1.89N0.76), the carbon source's formula, and the
conversion computed by the Reactor Design Chain (Section 5, ε-based). The O2 coefficient is not fixed by atom
counting alone — it requires a degree-of-reduction balance (Roels' method) across the carbon
source, biomass, and O2/H2O, since different carbon sources arrive with different degrees of
reduction per carbon even at equal biomass yield. **Resolved — see §9.5:** O2 stoichiometry is computed via Roels' degree-of-reduction
balance in `compute_O2_CO2_H2O_coefficients` (`common/kinetics.py`), not sourced as a separate
parameter. The aerated-bioreactor design uses this computed coefficient directly.

**Implementation:** modeled as a single `Nutrients` pseudo-`Chemical` (mass basis, `basis='wt'`),
consistent with SuperPro's own "Mass stoichiometry" labeling for their Nutrients term — "Nutrients"
isn't a real molecule, so a mol/mol coefficient would require an invented MW with no physical
meaning. Molecular weight is not invented: build a reference `Stream` mixed at the recipe's real
component ratios (AmmoniumSulfate, K2SO4, MgCl2, FeCl3, CoCl2, etc., each a properly defined
`bst.Chemical`), read `.MW` off that stream (BioSTEAM computes the mass-weighted average
automatically), and instantiate `Nutrients` with that value — precedented by how pseudo-components
are handled elsewhere in the BioSTEAM/petroleum-fraction ecosystem, not a workaround.
- **Stoichiometric coefficient (g Nutrients / g biomass):** as before — sum of the recipe's
  non-CHNO component concentrations (g/L) divided by the biomass titer that recipe was validated
  at. **User sourcing this reference directly.**
- **Costing:** a single composite price assigned directly to `Nutrients.price`, computed as the
  **mass-weighted** average of individually-sourced literature component prices, using the same
  mass fractions already used to derive MW and the stoichiometric coefficient above. This is
  mathematically equivalent to summing itemized component costs (composite_price × total_mass =
  Σ price_i × mass_i, given consistent mass-weighting) and is simpler to implement — BioSTEAM's
  native `stream.cost = price × mass_flow` handles the rest, no separate summation utility needed.
  Kept as its own clearly-labeled function (fed by the component-price table) so it can be rerun
  if any individual component price is updated later, rather than a static number that silently
  goes stale.
- **The itemized fractions (same ones used for MW/price/coefficient) are reused directly for the
  LCI export (Section 8)** — total simulated Nutrients mass flow × fixed fractions → itemized
  component flows for openLCA. Separate consumer of the same fractions table, independent of which
  pricing method is used.

**Known simplification, logged not hidden:** lumping assumes the recipe's relative component
ratios hold as the process scales — no visibility into whether one specific trace element becomes
individually limiting or cost-dominant. Acceptable since none of these are the
substrate/inhibition-limiting species the kinetics work (Section 5) is concerned with.

**Why this replaces both earlier drafts of this section:** unlike SuperPro's version, the
coefficient and price are derived from a real cited source rather than asserted; unlike the old
model's itemized-but-unmechanistic version, consumption is tied to a reaction that actually
removes nutrients from the broth (closing the mass balance correctly, including what's excess and
reports to wastewater treatment) rather than a media-volume split with no consumption term at all.

## 8. LCA / LCIA Method

**Decision: LCA is out of scope for the BioSTEAM models.** LCIA will be conducted separately in
**openLCA** (user has existing database access/expertise — no dependency on this project).
BioSTEAM's role is limited to generating the process design, mass/energy balances, and TEA;
it also supplies the life cycle inventory (LCI) that feeds the openLCA foreground model.

**Rationale (superseding the earlier TRACI-2.1-in-BioSTEAM plan):** BioSTEAM's native LCA
tooling only characterizes operational flows (feedstocks, utilities) against manually-defined
characterization factors — it does not include capital goods/embodied equipment impacts.
openLCA + a full background database (e.g., ecoinvent) provides built-in infrastructure/capital-
goods datasets, complete CF libraries (TRACI 2.1 and ReCiPe2016 both, not a forced choice), and
proper upstream supply-chain linkage for purchased inputs — all better-sourced than anything
hand-built inside BioSteam for this project.

**Deliverable requirement from each BioSTEAM model (for openLCA import):** a clear, itemized
equipment list per route, to make LCI construction straightforward — at minimum:
- Equipment ID, type, and key sizing parameter (volume, area, power, etc.) per unit
- **N (parallel vessel count, including N+1 redundancy — Section 5, step 9).** Required, not
  optional: since N_capacity+1 identical vessels are represented in BioSTEAM as a single unit with
  a cost/utility multiplier (`self.N`/`.parallel['self']`), omitting N from the export would make
  openLCA see only "one vessel" and undercount capital-goods impact by a factor of N.
- Material of construction (assume stainless steel unless a unit specifies otherwise) — needed to
  link to the correct ecoinvent infrastructure dataset
- Installed equipment cost (already produced by the TEA) — useful cross-check, not a substitute
  for mass-based linkage
- Full foreground stream table: all inlet material/energy flows and outlet product/waste/emission
  flows, on a per-kg-SCP (functional unit) basis, for each unit and for the system as a whole.
  **Nutrients must appear itemized, not as one lumped flow** — reuse the same fixed-fraction
  breakdown already established in Section 7 for TEA costing (total simulated `Nutrients` mass
  flow × fixed mass fractions → individual salts/trace metals); this is the same table computed
  once and consumed by both TEA costing and this export, not a separate calculation.

This should be a standard, consistently-formatted export (e.g., one Excel/CSV per route) generated
by each model — not something assembled ad hoc after the fact — so equipment/stream naming stays
consistent across the four routes and the openLCA build doesn't have to reverse-engineer BioSTEAM
internals.

**Decision: built into the pipeline.** Each model's results-export step (successor to the old
`export_all_results()` pattern) will automatically generate this equipment list + foreground
stream table as one of its standard outputs, run every time the model is simulated — not a manual
post-hoc data-pull. Same export function/format shared across all four route models.

**Implementation (2026-08-12):** The automated LCI export is implemented as `common/lca_export.py`
(accessor interpreter and Excel writer) and `common/lca_config.py` (NAICS allocation, elementary
flow strings, and per-route row specifications). `run_models.py` calls
`export_lca_inventory(system, route, ECONOMICS)` for each route after `system.simulate()`,
writing `lca/{RouteTitle}_InventoryAssessment.xlsx`. See `lca/README.md` for full details on sheet
structure, NAICS mapping, and unit conventions.

## 9. Parameter Registry (Values, Citations, and SA Ranges)

**This section is the single source of truth for every sourced/chosen numeric parameter in the
project** — the evolution of what started as an open-items checklist. As values come in, they're
filled into this table rather than tracked separately from the SA ranges (Section 11) or left to
live only inside `parameters.py` (Section 10) with no framework-level record. `parameters.py`
should read from this table (or a structured file derived from it), not maintain a parallel copy.

**Columns:** Parameter | Route | Value | Citation | SA range | Range justification. Rows below are
templates — populate as sourcing happens. "User sourcing/verifying directly" rows are not to be
filled by Claude, per the standing sourcing-trust decision established earlier in this project.

### 9.0 Sourcing Guide — What Kind of Data Gives You What, Best to OK

**What each culture mode reliably gives you, and what it doesn't:**

| Culture mode reported | μmax | Yxs | Titer (for X\* ceiling) | S\* validation (residual/standing concentration) |
|---|---|---|---|---|
| **Continuous/chemostat** | Best — direct, if measured near washout or via a D-sweep | Good | Good, but see note below (no continuous outflow removing biomass in batch/fed-batch, so continuous titer is usually the *most conservative*, not the highest) | **Best.** The chemostat's own residual/steady-state concentration *is* S\* — directly comparable, no interpretation needed |
| **Fed-batch, continuous/dripped feeding** | OK — only if exponential-phase data is isolated and clearly labeled as such (Section: specific vs. maximum growth rate) | Good | **Best available titer reference** (see Section 5 step 2) | OK, only if the paper reports *residual* concentration over time, not just cumulative substrate added — see warning below |
| **Fed-batch, pulse feeding** | OK, same caveat as above | Good | Good, same caveat as continuous-feed fed-batch (ceiling to fraction down from) | **Least reliable — read carefully.** See dedicated warning below |
| **Batch (single initial charge)** | OK, if exponential-phase slope is isolated | Good | **Weakest reference** (Section 5 step 2 — single-dose exposure, not representative of this design) | S0 (starting concentration) is precisely known, but is the *least useful* number for S\* validation — see below |

**The specific problem with batch data, since you raised it directly:** a batch run gives you three
clean numbers — μmax, final titer, and starting substrate concentration S0. What it does *not* give
you is anything resembling S\* (standing/residual concentration), because in a batch run substrate
concentration is monotonically declining from S0 to ~0 over the whole run — there's no steady value
to point to. S0 itself is the *worst* number to treat as a stand-in for S\*: it's the single highest,
single-dose-exposure concentration the culture ever saw, essentially the opposite of what our design
(continuous, low standing concentration) is trying to achieve. If a source only offers batch data,
treat μmax and titer as usable (with the caveats already noted), but do **not** use S0 for the S\*
validation check (Section 5, step 10) — either find a separate source with fed-batch/continuous
concentration data for that same substrate, or skip the validation check for that route and flag it
as unverified rather than validating against the wrong number.

**The specific problem with pulse-fed data — read this before trusting a reported concentration
number from a pulse-feeding study:** pulse feeding means substrate is added in discrete boluses,
not continuously — so the *instantaneous* concentration spikes right after each pulse (often much
higher than a "nominal" or average concentration would suggest) and then falls as cells consume it,
until the next pulse. A single reported "substrate concentration" from a pulse-fed study could mean
the peak (right after a pulse), the trough (right before the next pulse — the physiologically
relevant one, closest to our S\* concept), or an average across the cycle — and papers don't always
specify which. **Only the trough/pre-pulse concentration is usable for the S\* validation check**;
if the paper doesn't distinguish, don't guess which one is being reported — treat it as unusable for
that specific check rather than risk comparing our S\* against a peak concentration that looks
artificially permissive.

**Bottom line for prioritizing your search effort:** continuous/chemostat data is best for
everything and hardest to find; fed-batch (continuous feed, not pulsed) is the best realistic
target for titer specifically; batch data is fine for μmax but should not be trusted for the S\*
check. If you can only find batch data for a route, that's still enough to proceed with steps 1–9
of the design chain — just log the S\* check as unverified for that route rather than skip it
silently.

### 9.1 Biological / Kinetic Parameters

| Parameter | Route | Value | Citation | SA range | Range justification |
|---|---|---|---|---|---|
| μmax | Fructose | 0.22 h-1 | Boy, C., Lesage, J., Alfenore, S., Guillouet, S. E., & Gorret, N. (2021). Investigation of the robustness of Cupriavidus necator engineered strains during fed ‑ batch cultures. AMB Express. https://doi.org/10.1186/s13568-021-01307-4 | n/a | n/a |
| Yxs | Fructose | 0.32 gx/gs | Boy, C., Lesage, J., Alfenore, S., Guillouet, S. E., & Gorret, N. (2021). Investigation of the robustness of Cupriavidus necator engineered strains during fed ‑ batch cultures. AMB Express. https://doi.org/10.1186/s13568-021-01307-4 | n/a | n/a |
| Max reported titer | Fructose | 32 g/L | Nygaard, D., Yashchuk, O., Noseda, D. G., & Araoz, B. (2021). Improved fermentation strategies in a bioreactor for enhancing poly(3-hydroxybutyrate) (PHB) production by wild type Cupriavidus necator from fructose. Heliyon, 7(January). https://doi.org/10.1016/j.heliyon.2021.e05979 | n/a | n/a |
| S\* validation reference (safe/max tolerated standing concentration) | Fructose | 20 g/L | Boy et al. (2021), AMB Express, https://doi.org/10.1186/s13568-021-01307-4 — **not an inhibition threshold** (verified: paper doesn't report one; 20 g/L is an operational feeding setpoint, unrelated to toxicity). Retained as the working value on separate empirical grounds: fructose is pulsed up to 50 g/L in this and other fed-batch studies (e.g. Nygaard/Santolin, Section 9.1 titer rows) with no reported growth inhibition or toxicity at that concentration — absence of any reported inhibition up to 50 g/L is the actual basis for treating fructose as effectively non-inhibitory in the operating range this design uses, not a specific measured threshold. | n/a | n/a |
| μmax | Acetate | 0.15 h-1 | Garcia-Gonzalez, L., & de Wever, H. (2018). Acetic acid as an indirect sink of CO2 for the synthesis of polyhydroxyalkanoates (PHA): Comparison with PHA production processes directly using CO2 as feedstock. Applied Sciences (Switzerland), 8(9). https://doi.org/10.3390/app8091416 | n/a | n/a |
| Yxs | Acetate | 0.45 | Garcia-Gonzalez, L., & de Wever, H. (2018). Acetic acid as an indirect sink of CO2 for the synthesis of polyhydroxyalkanoates (PHA): Comparison with PHA production processes directly using CO2 as feedstock. Applied Sciences (Switzerland), 8(9). https://doi.org/10.3390/app8091416  | n/a | n/a |
| Max reported titer | Acetate | 15 g/L | Garcia-Gonzalez, L., & de Wever, H. (2018). Acetic acid as an indirect sink of CO2 for the synthesis of polyhydroxyalkanoates (PHA): Comparison with PHA production processes directly using CO2 as feedstock. Applied Sciences (Switzerland), 8(9). https://doi.org/10.3390/app8091416 | n/a | n/a |
| S\* validation reference (safe/max tolerated standing concentration) | Acetate | 3 g/L | Garcia-Gonzalez, L., & de Wever, H. (2018). Acetic acid as an indirect sink of CO2 for the synthesis of polyhydroxyalkanoates (PHA): Comparison with PHA production processes directly using CO2 as feedstock. Applied Sciences (Switzerland), 8(9). https://doi.org/10.3390/app8091416 — see Section 9.0 sourcing guide; must be trough/residual value, not S0 or a pulse peak. (code: `RouteParams.S_star_max`; activates inhibition branch in `design_reactor()` — §5; not binding for acetate: X\*\_titer = 11.25 g/L < X\*\_inhibition = 12.15 g/L) | n/a | n/a |
| μmax | Formate | 0.18 h-1 | Grunwald, S., Mottet, A., Grousseau, E., Plassmeier, J. K., Popović, M. K., Uribelarrea, J. L., Gorret, N., Guillouet, S. E., & Sinskey, A. (2015). Kinetic and stoichiometric characterization of organoautotrophic growth of Ralstonia eutropha on formic acid in fed-batch and continuous cultures. Microbial Biotechnology, 8(1), 155–163. https://doi.org/10.1111/1751-7915.12149 | n/a | n/a |
| Yxs | Formate | 0.06 g/g | Claassens, N. J., Bordanaba-Florit, G., Cotton, C. A. R., de Maria, A., Finger-Bou, M., Friedeheim, L., Giner-Laguarda, N., Munar-Palmer, M., Newell, W., Scarinci, G., Verbunt, J., de Vries, S. T., Yilmaz, S., & Bar-Even, A. (2020). Replacing the Calvin cycle with the reductive glycine pathway in Cupriavidus necator. Metabolic Engineering, 62, 30–41. https://doi.org/10.1016/j.ymben.2020.08.004 | n/a | n/a |
| Max reported titer | Formate | 10.5 g/L | Grunwald, S., Mottet, A., Grousseau, E., Plassmeier, J. K., Popović, M. K., Uribelarrea, J. L., Gorret, N., Guillouet, S. E., & Sinskey, A. (2015). Kinetic and stoichiometric characterization of organoautotrophic growth of Ralstonia eutropha on formic acid in fed-batch and continuous cultures. Microbial Biotechnology, 8(1), 155–163. https://doi.org/10.1111/1751-7915.12149 | n/a | n/a |
| S\* validation reference (safe/max tolerated standing concentration) | Formate | ~3–4 g/L (extrapolated); **`S_star_max` = 3.0 g/L (conservative lower end)** | Grunwald, S., Mottet, A., Grousseau, E., Plassmeier, J. K., Popović, M. K., Uribelarrea, J. L., Gorret, N., Guillouet, S. E., & Sinskey, A. (2015). Kinetic and stoichiometric characterization of organoautotrophic growth of Ralstonia eutropha on formic acid in fed-batch and continuous cultures. Microbial Biotechnology, 8(1), 155–163. https://doi.org/10.1111/1751-7915.12149 — Biomass yield declines **linearly** with increasing residual formate over the measured range (0–1.5 g/L residual; pH-stat fed-batch, pH 6.7). Extrapolating the linear fit to zero yield gives ~3.0–4.1 g/L; that extrapolated range — not a directly observed zero-growth point — is the basis for this value. No Andrews/Haldane Ki was reported. **Important caveat:** yield begins declining from any positive residual concentration; this parameter is therefore an absolute upper bound, not a threshold below which inhibition is absent. See Section 9.0 sourcing guide; must be a trough/residual value, not S0 or a pulse peak. (code: `RouteParams.S_star_max`; activates inhibition branch in `design_reactor()` — §5; **binding** for formate: X\*\_inhibition = 1.62 g/L < X\*\_titer = 7.875 g/L → X\* = 1.62 g/L, ~4.9× more reactor volume than the unconstrained titer-forward design) | n/a | n/a |
| μmax (autotrophic H2) | Gas fermentation | 0.12 h-1 | Yu, J., & Lu, Y. (2019). Carbon dioxide fixation by a hydrogen-oxidizing bacterium: Biomass yield, reversal respiratory quotient, stoichiometric equations and bioenergetics. Biochemical Engineering Journal, 152. https://doi.org/10.1016/j.bej.2019.107369 | n/a | n/a |
| Yxs (H2 basis) | Gas fermentation | **2.26 g CDW/g H2** | Derived from molar growth equation (§9.5a): MW_biomass / (21.36 × MW_H2) = 97.20 / 43.06 = 2.26. The molar equation is the stoichiometric anchor; Yxs is computed from it rather than independently sourced. Supersedes 1.56 g CDW/g H2 (Yu & Lu 2019, *Biochem. Eng. J.* 152:107369), which reflects a different experimental condition inconsistent with the adopted molar equation. | n/a | n/a |
| Max reported titer | Gas fermentation | 7 g/L | Yu, J., & Lu, Y. (2019). Carbon dioxide fixation by a hydrogen-oxidizing bacterium: Biomass yield, reversal respiratory quotient, stoichiometric equations and bioenergetics. Biochemical Engineering Journal, 152. https://doi.org/10.1016/j.bej.2019.107369 | n/a | n/a |

### 9.2 Design-Choice & Engineering-Judgment Parameters

| Parameter | Route | Value | Citation | SA range | Range justification |
|---|---|---|---|---|---|
| ε (conversion extent) | All 4 | 0.9 | engineering judgment, not literature | 0.8 - 0.95 | Section 5 |
| D-margin fraction | All 4 | 0.8 umax | https://bioprocesstools.com/blog/fermentation-yield-calculation/ | 0.7-0.85 | Section 5 |
| target_titer_fraction (X* = fraction × max_titer) | 3 liquid routes (shared) | 0.75 | Engineering judgment: literature max titers are batch/fed-batch results rarely sustained in steady-state continuous culture; 75% provides a conservative operating margin. Same value for all three liquid routes — no route-specific evidence for different margins. | 0.60 - 0.90 | Engineering judgment |
| Centrifuge recovery (eta_centrifuge) | All 4 (shared) | 0.95 | Engineering judgment: standard conservative assumption for industrial disc-stack or scroll centrifuge on bacterial biomass. Same downstream unit operation regardless of carbon source. | 0.90 - 0.98 | Engineering judgment |
| Dryer solids recovery | All 4 (shared) | 1.00 (modeled as 100%) | SprayDryer modeled as moisture removal only; all inlet solids exit with the product. Biomass loss in the dryer is not modeled — centrifuge recovery (0.95) is the only downstream yield parameter. Acceptable simplification for a first-pass TEA. | n/a | n/a |
| theta_O2 setpoint | 3 liquid routes | 0.5 (BioSTEAM default) | **Decision, not a gap** (Section 5b): kept at default deliberately, not literature-validated — revisit only if a route's results look O2-limited (implausible titer, or an `AeratedBioreactor` feasibility failure) | n/a | n/a |
| Restart frequency | All 4 (per line) | 2 restarts/yr (6-month campaigns) | Stansfield/Cauldron, reported in AgFunderNews (March 2024), https://agfundernews.com/brief-cauldron-raises-6-25m-series-a-to-scale-continuous-fermentation-technology — verified: 10,000 L continuous system ran 8+ months without contamination/genetic drift. 6-month campaign is a stated margin below the achieved 8 months. **Supersedes the BioPlan batch-failure-rate basis**, rejected because it measures per-batch failure in batch-oriented manufacturing and says nothing about continuous-campaign duration — see Section 6. Caveat: single company's best result, not a statistical average; product/organism unspecified in source. | 1.5 - 2.5 restarts/yr | Section 6 |
| Critical dissolved-O2 concentration | 3 liquid routes | Not pursued | **Decision, not a gap** (Section 5b): validation against theta_O2 deliberately not done — see theta_O2 row above | n/a | n/a |
| H2 maintenance coefficient (m_s_mol) | Gas fermentation only | 0.0 mol H2/g CDW/h (**maintenance neglected**) | **Decision, not a sourced parameter.** Yu & Lu (2019) report Y_obs = 1.56 g CDW/g H2 at μ_max = 0.12 h⁻¹ — one equation, two unknowns in the Herbert-Pirt model (Y_max, m_s). No primary source for m_s for *C. necator* lithoautotrophic H2 oxidation was located. Setting m_s = 0 collapses Herbert-Pirt to a constant-yield model: Y_obs = Y_max = 1.56 at all μ. This is mathematically stable and equivalent to the three liquid routes' fixed-yield assumption. Y_mol is then derived (not independently sourced): Y_mol = Yxs × MW_H2 = 1.56 × 2.016 = 3.145 g CDW/mol H2. Limitation: maintenance is a real phenomenon for H2-oxidizers and will cause actual yield to decrease at μ < μ_max; this simplification slightly overestimates yield at the design operating point (μ = 0.8 × μ_max). Revisit if a primary m_s measurement for *C. necator* H2 growth is found. | n/a — decision | n/a |
| Production target (PRODUCTION_TARGET_MT_YR) | All 4 (shared) | 25,000 MT/yr final packaged SCP | Engineering judgment: a plant size large enough to capture economies of scale while remaining consistent with order-of-magnitude estimates for commercial SCP production (Ritala et al. 2017, *Front. Microbiol.* 8:1695). This is the target on *final* product (post-centrifuge, post-dryer), not fermenter output — downstream recovery losses are applied before sizing. | n/a | n/a |
| Media sterilization temperature (T_STERILIZATION_K) | Fructose, acetate, formate routes + seed train (not gas fermentation) | 407.15 K (134 °C) | Standard temperature for continuous heat sterilization of liquid fermentation media (Doran, *Bioprocess Engineering Principles*, 2nd ed. (2012), §12.3; EN 285 standard). At 134 °C, continuous sterilization provides equivalent sterility assurance to 121 °C / 15 min batch autoclave with a shorter hold time, which is industrially preferred at this throughput. Sterilization block: HX101 heats to 134 °C → HP101 holds 2.44 min → HX102 cools to 30 °C; seed train: SHX101 → SHP101 → SHX102. Heat recovery not modeled (conservative). **Not used in gas fermentation route — replaced by UF membrane sterilization (UF101) — see §4a.** | n/a | n/a |
| Continuous sterilization hold time (STERILIZATION_HOLD_TAU_MIN) | Fructose, acetate, formate routes + seed train (HP101 / SHP101) | 2.44 min | Hold time at 134 °C for continuous heat sterilization. Stanbury, Whitaker & Hall (2017) *Principles of Fermentation Technology* (3rd ed.) §Sterilization. Implemented as `HoldPipe` (pass-through `bst.Unit` subclass) between HX101 and HX102 (production) / SHX101 and SHX102 (seed). Capital cost excluded: < 0.01 % FCI at design flows for all three liquid routes — standard conceptual-TEA omission for items below 0.1 % FCI. | n/a | n/a |
| UF sterilizer capital cost (Guo et al. 2014, log-log fit) | Gas fermentation only | `log(y) = 1.003·(log(x))^0.830 + 3.832` (2012 USD) | Guo, Englehardt & Wu (2014) *Water Sci. Technol.* WST-EM13819R1, Table 1 (UF, total installed capital, x = capacity in m³/d). CEPCI-escalated from 2012 (CEPCI = 585) to project dollar year (2025, CEPCI = 809.3). CEPCI-escalated cost is divided by `contingency_fee_factor` = 1.18 (BM factor = 1.0 for a plain `bst.Unit`) so that the TEA FCI contribution recovers Guo et al. total installed capital. Each unit numbered up at Q_max = 378,500 m³/d (top of validated range). Implemented in `common/sterilization.py`. | n/a | n/a |
| UF sterilizer annual O&M (Guo et al. 2014, log-log fit) | Gas fermentation only | `log(y) = 1.828·(log(x))^0.598 + 1.876` (2012 USD/yr) | Guo, Englehardt & Wu (2014) *Water Sci. Technol.* WST-EM13819R1, Table 1 (UF O&M, x = capacity in m³/d). CEPCI-escalated to project dollar year. Added to FOC as a separate line item in `SCPTEA._FOC()` (sum of `unit.annual_om_usd` for all `UltrafiltrationSterilizer` units). | n/a | n/a |
| UF sterilizer max capacity per unit (Q_max) | Gas fermentation only | 378,500 m³/d | Guo et al. (2014) top of validated capacity range. Units numbered up: N = ceil(Q_m3d / Q_max). | n/a | n/a |
| UF capital/O&M CEPCI base year | Gas fermentation only | 585 (2012) | `bst.units.design_tools.CEPCI_by_year[2012]`. CEPCI ratio = bst.CE / 585 applied in `_cost()` and `_design()` to escalate Guo et al. 2012 USD to the project dollar year. | n/a | n/a |
| Fermentation temperature (T_FERMENTATION_K) | All 4 (shared) | 303.15 K (30 °C) | Optimal growth temperature for *C. necator* — Boy et al. (2021) *AMB Express* 11:166; Yu & Lu (2019) *Biochem. Eng. J.* 148:44–52. Passed to `ExtentBasedBioreactor(T=303.15)` and `PerfusionBioreactor` so BioSTEAM computes metabolic heat removal duty at the correct operating point. | n/a | n/a |
| Centrifuge cake moisture content (CENTRIFUGE_CAKE_MOISTURE) | All 4 (shared) | 0.75 (75 wt% water) | Engineering judgment: representative of commercial scroll or disc-stack centrifuge performance on bacterial biomass slurries. Implemented via `bst.SolidsCentrifuge(moisture_content=0.75)` — BioSTEAM resolves the water split fraction internally to meet this target. | n/a | n/a |
| SprayDryer final product moisture (SPRAY_DRYER_MOISTURE) | All 4 (shared) | 0.05 (5 wt% water) | Industry standard specification for microbial SCP powder suitable for animal-feed formulation (Ugalde & Castrillo 2002, *Appl. Microbiol. Biotechnol.* 59:363–375). Implemented via `bst.SprayDryer(moisture_content=0.05)` — BioSTEAM evaporates the difference between cake moisture and this target. | n/a | n/a |
| WWT organic removal efficiency (WWT_ORGANIC_REMOVAL) | All 4 (shared) | 0.99 (99 wt% non-water removal) | Engineering judgment consistent with activated sludge / aerobic digestion performance at industrial scale — 95–99% BOD removal is standard for well-operated systems (Metcalf & Eddy, *Wastewater Engineering*, 5th ed., Table 10-1). Implemented in `_SludgeSettler` (WWT102): step 1 routes 99% of each non-water chemical to sludge; step 2 routes enough H₂O to sludge to meet the WWT_SLUDGE_MOISTURE = 80% moisture target (H₂O_to_sludge = (0.80/0.20) × dry_sludge_mass); remaining H₂O passes to the treated-water stream. | n/a | n/a |
| WWT sludge moisture (WWT_SLUDGE_MOISTURE) | All 4 (shared) | 0.80 (80 wt% H₂O) | Moisture fraction of dewatered sludge cake. 80 wt% H₂O is characteristic of centrifuge- or belt-filter-press-dewatered sludge — Metcalf & Eddy, *Wastewater Engineering*, 5th ed., Table 22-10. Governs the water split at WWT102 and scales the sludge stream price: `sludge.price = −wwt_organic_removal_cost × (1 − WWT_SLUDGE_MOISTURE) = −$0.066/kg wet sludge`, recovering $0.33/kg dry organic removed. | n/a | n/a |
| WWT treated-water recycle fraction (WWT_WATER_RECYCLE_FRACTION) | All 4 (shared) | 0.75 (75% recycled, 25% discharged) | Engineering judgment: a fraction less than 1 is required to close the water mass balance — aerobic fermentation produces net water (C. necator metabolism generates H2O stoichiometrically), so 100% recycle would cause unbounded accumulation. 75% recycle returns the majority of process water to the feed while the 25% discharge provides the outlet that absorbs reaction-produced water. Implemented as a second splitter (RCY101) downstream of WWT102 with `split = WWT_WATER_RECYCLE_FRACTION` applied uniformly to all components in the treated-water stream. The BioSTEAM recycle loop converges because 0.75 < 1 (contraction mapping). | n/a | n/a |
| NH3 and Nutrients feed supplement (NH3_NUTRIENTS_EXCESS) | All 4 (shared) | 0.05 (5 %) | Engineering judgment: continuous fermenters are operated with a small excess of N-source and mineral nutrients to ensure growth is never limited by co-reactants. 5 % is standard practice for mineral-salt media in continuous culture — Doran, *Bioprocess Engineering Principles*, 2nd ed. (2012), §12. Applied as `× (1.0 + NH3_NUTRIENTS_EXCESS)` to both `nutrients_kgh` and `nh3_kgh` feeds in all four route model builders and `common/seed_train.py`. Note: BioSTEAM's VLE routes residual free-NH3 to the reactor gas vent (Psat >> P at 30 °C), so the supplement has limited effect on liquid NH3 balance; an effluent floor in `ExtentBasedBioreactor._run_vent()` provides the primary numerical fix for near-zero effluent NH3. The Nutrients supplement (phase='l', non-volatile) fully resolves the Nutrients liquid effluent. | n/a | — |
| Feed mixer tau (MIX_TANK_TAU) | Fructose, acetate, formate M101 | 1 h | BioSTEAM MixTank default; standard hold-up time for continuous-feed mixing of g/L-concentration mineral salts media (Doran, *Bioprocess Engineering Principles*, 2nd ed.). | n/a | — |
| Feed mixer — gas fermentation M101 | Gas fermentation M101 only | bst.Mixer (inline blending, zero capital) | At Q ≈ 357,000 m³/h and feed concentration of 0.004 g/L nutrients (2103× more dilute than fructose), the feed is near-pure water; turbulent blending of miscible streams is instantaneous. A MixTank at this Q would require ~2,500 parallel 30 m³ vessels (BioSTEAM MixTank V_max limit), which is not a realistic plant design. Inline static mixing modeled as bst.Mixer with no capital cost. User-confirmed 2026-08-07. | n/a | — |
| WWT stream combiner — WWT101 | All 4 (WWT101) | bst.Mixer (inline blending, zero capital) | WWT101 combines centrifuge centrate and seed train effluents before WWT102. Note: D101 (SprayDryer) `outs[0]` is evaporated water vapor discharged directly to atmosphere — it is not a WWT feed. WWT101 is a pure stream combiner with no reaction, dissolution, or equalization kinetics — zero capital, consistent with WWT102 (`_SludgeSettler`, zero capital) and RCY101 (`bst.Splitter`, zero capital). Gas fermentation Q ≈ 370,000 m³/h made a MixTank infeasible (BioSTEAM V_max=30 m³ → ~2,500 parallel tanks, $454 M). User-confirmed 2026-08-07. | n/a | — |
| Feedstock / product storage tank residence time (STORAGE_TANK_TAU) | All 4 (shared) | 168 h (7 days) | Engineering judgment: one week of buffer inventory is a standard design assumption for continuous bioprocesses with reliable logistics (Towler & Sinnott, *Chemical Engineering Design*, 2nd ed.). Applied to fructose, nutrients, ammonia, and dried SCP product storage tanks (ST101–ST104). | n/a | — |
| Seed batch duration (SEED_BATCH_DURATION_H) | All 4 (seed train) | 72 h (3 stages × 24 h/stage) | Engineering judgment: each stage grows from 5 % inoculum (INOCULUM_RATIO) to working density. For fructose mu_max = 0.22 h⁻¹, growth time ≈ ln(20)/(0.8 × 0.22) = 17 h; 24 h/stage includes a ~7 h margin for lag phase (Doran, *Bioprocess Engineering Principles*, 2nd ed., §14.4). Governs N_seed_trains = ceil(N_total × RESTARTS_PER_YEAR × SEED_BATCH_DURATION_H / op_hours): ≈ 9 for gas fermentation (N_total ≈ 493), 1 for liquid routes (N_total ≈ 6–39). User-confirmed 2026-08-07. | n/a | — |
| Gas fermentation seed substrate | Gas fermentation seed train only | Fructose (heterotrophic) | C. necator is grown on fructose for seed culture before transitioning to autotrophic H2-oxidation at production scale. H2 is physically unsuitable for seed culture: (a) dissolved H2 at ambient pressure ≪ 0.001 g/L (pressurization to 4 atm required for S_f = 0.0051 g/L); (b) SeedBioreactor is not a pressure vessel. Fructose seed parameters sourced from fructose RouteParams (S0 from §5 step 3, nh3_wt from Roels stoichiometry). User-confirmed 2026-08-07. | n/a | — |

### 9.3 Nutrients — Recipe, Coefficient, and Prices (Section 7)

**Gap identified:** the table previously listed only the derived coefficient, not the underlying
recipe it's derived from. The recipe itself — individual component identities and concentrations
(g/L) — is a separate, prior input needed for three things: the coefficient (g Nutrients/g
biomass), the reference-stream MW (Section 7's pseudo-component construction), and the composite
price below. All three need the same recipe; none of them can be filled in without it.

**Recipe, verified:** Yu, J.; Munasinghe, P. (2018). Gas Fermentation Enhancement for
Chemolithotrophic Growth of *Cupriavidus necator* on Carbon Dioxide. *Fermentation* 4(3):63.
https://doi.org/10.3390/fermentation4030063 — confirmed real, confirmed titer (18 g/L CDW) is
reported in the same paper as the recipe (resolves the earlier cross-paper mismatch). **Decision:
applied to all four routes** (not gas-fermentation-specific), on the stated basis that mineral
salts media compositions are broadly similar across bacterial fermentation contexts generally —
this specific instance measured under autotrophic conditions, but the core components (phosphate
buffer, ammonium salt, Mg/trace metals) are standard across heterotrophic media too, differing
mainly in concentration/titer scale rather than composition. Logged as an explicit, deliberate
simplification, not an unexamined default.

**Note on possible citation overlap:** this paper's own reported result — μmax = 0.12 h⁻¹,
titer = 18 g/L CDW — is an exact match to the gas fermentation kinetics values in Section 9.1,
currently attributed there to "Yu & Lu 2019." Worth confirming which paper those Section 9.1 values
actually belong to; this research group has several closely related papers, so it may be
legitimate reuse, but the attribution should be checked, not assumed.

Recipe (minerals — **(NH4)2SO4 is lumped into the Nutrients stream** as an ordinary mass component
like the phosphate buffer or trace metals, not elementally decomposed for its nitrogen content —
consistent with how every other Nutrients component is handled. NH3 (co-fed separately) remains the
*sole* nitrogen source entering the growth reaction stoichiometry, Section 7 — no double-counting,
since (NH4)2SO4's contribution here is mass-only):
- Na2HPO4·2H2O: 2.5 g/L
- KH2PO4: 2.4 g/L
- (NH4)2SO4: 2.0 g/L  *(corrected from NH4Cl 1.0 g/L — source uses ammonium sulfate)*
- MgSO4·7H2O: 0.5 g/L
- NaHCO3: 0.5 g/L
- Ferric ammonium citrate: 0.1 g/L
- Trace element solution, 1 mL/L: H3BO3 0.6, CoCl2·6H2O 0.4, ZnSO4·7H2O 0.2, MnCl2·4H2O 0.06,
  Na2MoO4·2H2O 0.06, NiCl2·6H2O 0.04, CuSO4 0.02 (g/L of stock; ×0.001 dilution into final media —
  negligible mass contribution, ~0.0014 g/L)

Total nutrients ≈ 8.0 g/L.
**Coefficient = 8.0014 g/L ÷ 18 g/L CDW titer ≈ 0.445 g Nutrients/g biomass.** Compared to SuperPro's
own implied lumped-nutrients ratio (~0.04–0.08 g/g): ~5–10x higher — same reasoning as before
(research-grade media formulated generously/in excess, not economically optimized) — logged
explicitly, not silently accepted.

| Parameter | Route | Value | Citation | SA range | Range justification |
|---|---|---|---|---|---|
| Defined medium recipe (component identities + g/L concentrations) | All 4 (shared) | See recipe above | Yu & Munasinghe (2018), *Fermentation* 4(3):63 | n/a (recipe composition, not swept in SA — its *derived outputs* below are what get varied) | — |
| Achieved CDW titer (basis for Nutrients stoichiometric coefficient) | All 4 (shared) | 18.0 g/L CDW | Yu & Munasinghe (2018), *Fermentation* 4(3):63 — same paper as recipe; μmax = 0.12 h⁻¹ and titer = 18 g/L reported together | n/a | — |
| Lumped-Nutrients stoichiometric coefficient (g Nutrients/g biomass) | All 4 | 0.445 g/g | Derived: sum(recipe g/L) / achieved_titer = 8.0014 / 18.0 ≈ 0.445 g/g — computed in common/nutrients.py, not hardcoded | 0.22 – 0.67 g/g (±50%) | Engineering judgment: the source recipe (Yu & Munasinghe 2018) is explicitly research-grade media formulated generously/in excess, not economically optimized. An industrially-optimized mineral salts recipe could plausibly require 50% less nutrients at the same titer; conversely, a more conservative recipe or a lower-titer operating point could require up to 50% more. ±50% reflects the wide practical range between research-grade and industrially-minimized mineral media. User-confirmed 2026-08-07. |
**Component prices — expanded from a single placeholder row into an actual place to put each
value**, split by whether individual sourcing is worth the effort (the six bulk components, ~99.98%
of recipe mass) vs. not (the seven trace metals, ~0.02% combined — a single rough placeholder is
sufficient per the mass-fraction analysis above):

**Not for copying into code as literals.** The mass fractions shown in this section (35.7%, 34.3%,
etc.) are a static, point-in-time snapshot for human review only — computed here once so the
recipe's composition is easy to sanity-check on the page. The actual implementation
(`common/nutrients.py`, per `SCP_Implementation_Spec.md`) takes the raw `recipe` dict (g/L per
component) as its only real input and derives mass fractions, MW, the coefficient, and the
composite price from it live, on every call — nothing about composition is hardcoded as a separate
number anywhere in code. If the recipe in this section is ever edited, every downstream value
(fractions, MW, coefficient, price, LCI export breakdown) is expected to update automatically from
that single source when the model is rebuilt — this table is not where that recomputation happens,
`common/nutrients.py` is.

*taken as 1% of the price available from Sigma Aldrich (industrial bulk discount — updated from 10%; 10% of lab price was inconsistent with the $1.74/kg composite stated below, which was always computed at 1%)*

| Component | Mass fraction | Value ($/kg) | Citation |
|---|---|---|---|
| Na2HPO4·2H2O | 31.2% | $2.10/kg | https://www.sigmaaldrich.com/US/en/product/sigma/71643 |
| KH2PO4 | 30.0% | $1.70/kg | https://www.sigmaaldrich.com/US/en/product/sigald/p0662 |
| (NH4)2SO4 | 25.0% | $1.50/kg | https://www.sigmaaldrich.com/US/en/product/mm/168356 |
| MgSO4·7H2O | 6.2% | $1.70/kg | https://www.sigmaaldrich.com/US/en/product/sigald/230391?srsltid=AfmBOoqiyFdCh8NC4tmFhKwrHKpn6ecSab7oUgajPYTGy7CANWhUzLTo |
| NaHCO3 | 6.2% | $1.00/kg | https://www.sigmaaldrich.com/US/en/product/sigald/s6014 |
| Ferric ammonium citrate | 1.2% | $5.00/kg | https://www.sigmaaldrich.com/US/en/product/sigma/res20400a7 |
| All 7 trace metals combined (H3BO3, CoCl2·6H2O, ZnSO4·7H2O, MnCl2·4H2O, Na2MoO4·2H2O, NiCl2·6H2O, CuSO4) | ~0.02% | $6.00/kg | based on near mean price of individual metals |

**Composite Nutrients price = $1.78/kg** (mass-weighted average of the discounted prices above).

### 9.4 Feedstock, Utility, and Economic Parameters (Section 3) — Not Previously Itemized

**Gap identified:** Section 3 establishes that a common economic basis (dollar-year, CEPCI,
financing) is required, and Section 11 names "economic" as a sensitivity category, but no row ever
requested actual values for any of these — an oversight, corrected here.

**SA range scope — closed decision, not an oversight:** rows below with SA range = "n/a" are
deliberate — user selected which TEA parameters warrant a sensitivity range and left the rest
unswept. Not a gap to fill in later; don't re-flag these as missing.

| Parameter | Route | Value | Citation | SA range | Range justification |
|---|---|---|---|---|---|
| Fructose feedstock price ($/kg) | Fructose | $1.16/kg | https://www.selinawamucii.com/insights/prices/united-states-of-america/fructose/ | +-50% | — |
| Acetate/acetic acid feedstock price ($/kg) | Acetate | $0.65/kg | Crandall, B. S., Overa, S., Shin, H., & Jiao, F. (2023). Turning Carbon Dioxide into Sustainable Food and Chemicals: How Electrosynthesized Acetate Is Paving the Way for Fermentation Innovation. Accounts of Chemical Research, 56(12), 1505–1516. https://doi.org/10.1021/acs.accounts.3c00098 — electrochemical conversion of CO2 | +-50% | — |
| Formate/formic acid feedstock price ($/kg) | Formate | $0.35/kg formic acid | Jouny, M., Luc, W., & Jiao, F. (2018). General Techno-Economic Analysis of CO2 Electrolysis Systems. Industrial and Engineering Chemistry Research, 57(6), 2165–2177. https://doi.org/10.1021/acs.iecr.7b03514 — electrochemical conversion of CO2 | +-50% | — |
| H2 feedstock price (or production cost, if on-site) ($/kg) | Gas fermentation | $4.83/kg | Peterson, D., Vickers, J., Desantis, D., Ayers, K., Hamdan, M., Harrison, K., Randolph, K., Miller, E., & Satyapal, S. (2019). DOE Hydrogen and Fuel Cells Program Record: Hydrogen Production Cost From PEM Electrolysis — 2019. http://www.hydrogen.energy.gov/h2a_prod_studies.html — central-scale PEM water electrolysis. Supersedes Christensen (2020) ICCT value of $8.81/kg. | +-50% | — |
| CO2 feedstock price ($/kg) | Gas fermentation | $0/kg | Treated as a waste stream — zero cost basis. CO2 is assumed to be available as an industrial byproduct or flue gas at no feedstock cost. Decision, not a sourced market price. | n/a | — |
| O2 co-reactant price ($/kg) | Gas fermentation | $0/kg | Water electrolysis byproduct; all capital and operating costs allocated to H2 per standard co-product allocation convention in electrolysis TEA. O2 is a free byproduct in this cost allocation framework — consistent with H2 price source (Christensen 2020, which reports H2-allocated costs). Decision, not a sourced market price. | n/a | — |
| Electricity rate ($/kWh) | All 4 (shared) | $0.032/kWh | Department of Energy Wind Energy Technologies Office, U. (2023). Land-Based Wind Market Report: 2023 Edition. http://www.osti.gov — 2022 average wind PPA price, **used as the assumed full delivered rate** (not just energy-commodity price). **Stated assumption, not the conservative case:** this assumes favorable large-industrial-load wind PPA procurement with delivery bundled in — real, but on the optimistic end versus standard industrial grid pricing (~$0.08/kWh, see SA range). Explicitly not modeling self-owned wind generation (would require separate turbine CAPEX and a reliability/backup provision for wind's intermittency against continuous fermentation's uninterruptible demand — out of scope, not equivalent to this PPA assumption despite surface similarity). | $0.020/kWh - $0.087/kWh | lowest market value of wind - US industrial price (April 2026) |
| Steam / cooling water rates | All 4 (shared) | $13/GJ; $0.015/m3 | Turton textbook | n/a | — |
| Chilled water rate | All 4 (shared) | $5.00/GJ | Seider et al. Table 8.3 | n/a | — |
| Process water price ($/m³) | All 4 (shared) | $0.27/m³ | Seider, Widagdo, Seader, Lewin & Ng, *Product and Process Design Principles*, Table 8.3 (process water utility cost). Stored as $/m³; converted to $/kg at point of use via water density = 1000 kg/m³ → $0.00027/kg applied to feed stream price. | n/a | — |
| CEPCI year / cost basis | All 4 (shared) | 809.3 | Section 3 requires this be fixed; 2025 Average | n/a | — |
| IRR target, tax rate, plant life, depreciation schedule | All 4 (shared) | 10%/yr, 35%, 20yrs, MACRS7| Section 3 requires these be fixed; based on El-Halwagi. **Tax rate note:** 35% is a deliberate combined federal+state approximation (current US federal rate is 21%; 35% represents a conservative federal+state total), not the outdated pre-2018 federal-only rate — clarified to avoid future misreading. | n/a (IRR target especially) | — |
| Labor cost ($/yr, total) | All 4 (shared or per route) | 3.6M/yr | Turton textbook - based on EX 17.8; similar scale and requirements; sugarcane-biorefinery reference default was $2.5M/yr (Section 3a) — not directly usable for SCP, needs its own basis | n/a | — |
| Fringe benefits (fraction of labor) | All 4 (shared) | 0 | reference default 0.40 (Section 3a) — included in labor cost in Turton reference | n/a | — |
| Supplies (fraction of labor) | All 4 (shared) | 0 | reference default 0.20 (Section 3a) — included in labor cost in Turton reference | n/a | — |
| Property tax (fraction of FCI) | All 4 (shared) | 1% | Turton | n/a | — |
| Property insurance (fraction of FCI) | All 4 (shared) | 1% | Turton | n/a | — |
| Maintenance (fraction of FCI) | All 4 (shared) | 10% | Turton, for solid/fluids-handling system. **Comprehensive figure** — includes maintenance materials, maintenance labor, and maintenance supplies together (broader scope than the 1% sugarcane-biorefinery reference default cited elsewhere, which covers materials only) — consistent with fringe_benefits=0/supplies=0 above, since both operating and maintenance labor are already fully-loaded in their respective lines, not double-counted. | n/a | — |
| Administration (fraction of FCI) | All 4 (shared) | 5% | Turton | n/a | — |
| Biogas fuel/byproduct value | All 4 | **N/A — no anaerobic digestion modeled; no biogas stream exists in any route (Section 3a)** | n/a | n/a | not modeled |
| Contingency + fees factor (`contingency_fee_factor`) | All 4 (shared) | 1.18 | Turton, Bailie, Whiting & Shaeiwitz, *Analysis, Synthesis and Design of Chemical Processes* (7th ed.) Table 16.1 — contingency (15%) + contractor fees (3%) applied to Σ(C_BM). Note: the per-unit f_BM factors (1.65–3.21 in this model, purchase-cost-weighted average 2.034) are not parameters here — they are properties of BioSTEAM's unit classes sourced from Turton Tables A.1–A.8 and Seider. Effective total multiplier from Σ(purchase_cost) to FCI: 1.18 × 2.034 ≈ 2.40× (vs. previous Lang factor 4.28×). | ×0.65 – ×1.35 | Turton BM method accuracy ±35%; FCI = 1.18 × IEC scales linearly, so this directly represents TCI uncertainty |
| Working capital (fraction of FCI) | All 4 (shared) | 0.176 | Seider et al., *Product and Process Design Principles* | n/a | — |
| Construction schedule | All 4 (shared) | (0.40, 0.60) — 40 %/60 % over 2 pre-startup years | Huang, Long & Singh (2016), *Biofuels, Bioprod. Bioref.* 10(3):299–315 (ConventionalEthanolTEA default) | n/a | — |
| Ammonia price ($/kg) | All 4 (shared) | $0.50/kg | BusinessAnalytiq Ammonia Price Index, https://businessanalytiq.com/procurementanalytics/index/ammonia-price-index/ | ±50% | Consistent with other feedstock/co-reactant price SA ranges |
| WWT organic removal cost (wwt_organic_removal_cost, $/kg organic removed) | All 4 (shared) | $0.33/kg organic removed | Seider, Widagdo, Seader, Lewin & Ng, *Product and Process Design Principles* — activated sludge / aerobic digestion unit cost. Cost basis is per kg **dry** organic removed. Implementation: `sludge.price = −wwt_organic_removal_cost × (1 − WWT_SLUDGE_MOISTURE) = −$0.33 × 0.20 = −$0.066/kg wet sludge`. BioSTEAM multiplies this price by the total sludge mass flow; since sludge is 20% dry solids, the product = $0.066/kg × (dry_mass/0.20) × 0.20 = $0.33/kg dry organic, which is the intended basis. | n/a | — |

### 9.5 Oxygen Stoichiometry — Computed, Not a Registry Parameter

**Not a value to source — removed from the registry table format entirely.** O2 (and the CO2/H2O
split) cannot be pinned down by atom balance alone once C, H, and N are closed via the carbon
source formula, `CNecatorBiomass`, and Yxs (Section 9.1) — one degree of freedom remains (how much
oxygen ends up in CO2 vs. H2O vs. how much O2 is consumed), resolved by a degree-of-reduction
(electron) balance, not by sourcing another number.

**Method (Roels'):** degree of reduction per C-mol of any compound CHₕOₒNₙ:
```
γ = 4 + h − 2o − 3n
```
Compute γ_S (carbon source) and γ_X (biomass) this way, then:
```
O2 coefficient (mol O2 / C-mol substrate) = (γ_S − Yxs_Cmol · γ_X) / 4
```
Every input already exists elsewhere in the registry (substrate formula, biomass formula, Yxs) —
nothing new to source.

**Implementation:** one shared function, `common/kinetics.py` (or a dedicated
`common/stoichiometry.py` if cleaner) —
`compute_O2_CO2_H2O_coefficients(substrate_formula, biomass_formula, Yxs)` — called once per route
at model-build time, automatically recomputed whenever ε, Yxs, or the substrate changes upstream.
Same "compute, don't assert" principle Section 5 already established for the biomass:substrate
coefficient (driven live by Yxs) — this is a direct extension of that architecture, not a new one.

**Note:** the equipment-list/LCI export format item from the earlier checklist is resolved (Section
8/11) and removed from this table — it was a format decision, not a numeric parameter, and doesn't
belong in a parameter registry.

### 9.5a Autotrophic Growth Reaction Stoichiometry (Gas Fermentation)

**Unlike the heterotrophic routes, this stoichiometry is not derived via Roels' degree-of-reduction
method** — H2 has no carbon, and CO2 is a reactant consumed rather than produced. The molar
equation is taken directly from the literature as a representative knallgas growth stoichiometry
for *C. necator*, and the Nutrients term is appended per Section 7.

**Molar growth equation (per mol C4.09H7.13O1.89N0.76 biomass):**
```
21.36 H2 + 6.21 O2 + 4.09 CO2 + 0.76 NH3 + [Nutrients] → C4.09H7.13O1.89N0.76 + 18.70 H2O
```
The `[Nutrients]` term is appended on a mass (wt-basis) coefficient of 0.39 g Nutrients/g CDW
(Section 9.3), consistent with the liquid-route growth reactions.

**Biomass molecular weight:**
```
MW_biomass = 4.09×12.011 + 7.13×1.008 + 1.89×15.999 + 0.76×14.007 = 97.20 g/mol
```

**Derived mass coefficients (g per g CDW produced):**

| Species | Role | mol/mol biomass | MW (g/mol) | g/g CDW |
|---|---|---|---|---|
| H2 | electron donor (consumed) | 21.36 | 2.016 | **0.4430** |
| O2 | co-reactant (consumed) | 6.21 | 32.00 | **2.044** |
| CO2 | carbon source (consumed) | 4.09 | 44.01 | **1.851** |
| NH3 | nitrogen source (consumed) | 0.76 | 17.03 | **0.1331** |
| Nutrients | macro/trace minerals (consumed) | — | — | **0.389** (§9.3) |
| H2O | product | 18.70 | 18.015 | 3.466 |

**Yxs implied by this equation** (the stoichiometric anchor — Section 9.1):
```
Yxs_H2 = MW_biomass / (21.36 × MW_H2) = 97.20 / 43.06 = 2.26 g CDW / g H2
```
This is the value used in `design_gas_fermentation_reactor`. The previously-entered §9.1 value
of 1.56 g CDW/g H2 (Yu & Lu 2019) is superseded — it reflected a different experimental
condition and is not consistent with the molar equation adopted here.

**CO2:O2 stoichiometric ratio (mass):** 1.851 / 2.044 = **0.906** — see §4a for the design
check against the DC102 dissolved ratio (0.906 = 0.906, satisfied by construction).

**Implementation:** `build_autotrophic_growth_reaction(nutrients_mass_fractions)` in
`common/kinetics.py`. Uses the molar coefficients above directly (not a balance solve — the
equation is the source, Yxs is derived from it). Appends the Nutrients term the same way
`build_growth_reaction` does for liquid routes. Separate from `compute_O2_CO2_H2O_coefficients`,
which is heterotrophic-only.

## 10. File Structure & Cross-Model Consistency

**Principle: route-specific files contain almost no logic of their own — just route-specific
numbers, wired into shared functions/classes.** This is the mechanism that prevents the old files'
core failure mode (independently-hardcoded, silently-inconsistent constants per route) from
recurring — there's only one place a bug or assumption can live, fixed once for all four routes,
rather than four separately-written near-duplicates that can quietly diverge.

**Proposed layout:**
**Build/run separation — each model file exposes a parameterized builder function, not a script
that executes as a side effect.** `models/fructose_model.py` (and the other three) define a
function like `build_fructose_system(params: RouteParams, economics: EconomicBasis) -> tuple[bst.System, dict[str, float]]`
that constructs and returns the flowsheet and the nutrients mass-fractions dict (needed by the
exporter to unlump the Nutrients stream) — it does not call `.simulate()`, run the TEA, or export
results itself. A separate top-level driver (`run_models.py`) imports each builder, pulls
parameters from `parameters.py` (Section 9's registry), simulates, builds the TEA (shared settings,
`economics.py`), and calls the shared export (`export.py`) — uniformly, once, for all four routes.

This separation isn't just style — it's required by three things already committed to elsewhere in
this document: **Section 11's OAT sensitivity analysis** needs to call each builder repeatedly with
one parameter perturbed at a time, which is straightforward with a parameterized function and
awkward with a script that runs top-to-bottom on import; **Section 10's own cross-model consistency
check** can import and inspect all four builders from one script rather than scraping side effects
from four separately-run scripts; and **Section 8's export** is guaranteed to run the same way for
every route, since the driver — not each model file individually — is responsible for calling it.

```
scp_project/
├── common/
│   ├── chemicals.py       # CNecatorBiomass, Nutrients pseudo-chemical, custom chemical defs
│   ├── economics.py       # Section 3: SCPTEA subclass, build_tea() factory, configure_utility_prices()
│   ├── operating_hours.py # Section 5a: 7,752 h/yr derivation, seed_train_operating_hours()
│   ├── kinetics.py        # Section 5: design_reactor(), design_gas_fermentation_reactor(),
│   │                      #   compute_O2_CO2_H2O_coefficients(), build_growth_reaction(),
│   │                      #   build_autotrophic_growth_reaction(), required_fermenter_output()
│   ├── reactors.py        # Section 5b: ExtentBasedBioreactor (liquid routes) + SeedBioreactor
│   ├── nutrients.py       # Section 7: build_nutrients_properties() — price, coeff, mass fractions
│   ├── seed_train.py      # Section 6: build_seed_train() — 3-stage seed train + sterilization
│   ├── sterilization.py   # HoldPipe (liquid routes) + UltrafiltrationSterilizer (gas fermentation)
│   ├── wastewater.py      # build_wastewater_treatment() — WWT101/WWT102/_SludgeSettler/RCY101
│   ├── export.py          # Section 8: export_results() and supporting per-sheet builders
│   ├── lca_export.py      # Section 8: export_lca_inventory() — LCI Excel writer for openLCA
│   ├── lca_config.py      # Section 8: NAICS allocation, elementary flow strings, row specs
│   └── parameters.py      # Section 9: RouteParams, EconomicBasis, NutrientsRecipe, all constants
├── perfusion_bioreactor/
│   ├── droplet_column.py      # DropletColumn unit — closed H2/CO2+O2 pre-saturation vessels
│   └── unitwithauxiliary.py   # PerfusionBioreactor — gas fermentation production reactor
├── models/
│   ├── fructose_model.py       # build_fructose_system(params, economics) -> (bst.System, dict)
│   ├── acetate_model.py        # build_acetate_system(params, economics) -> (bst.System, dict)
│   ├── formate_model.py        # build_formate_system(params, economics) -> (bst.System, dict)
│   └── gas_fermentation_model.py  # build_gas_fermentation_system(params, economics) -> (bst.System, dict)
├── lca/
│   └── (route InventoryAssessment xlsx files — written by export_lca_inventory())
├── run_models.py           # driver: imports builders, simulates, runs TEA, calls export — for all 4 routes
├── sensitivity_analysis.py # Section 11: OAT sweep, calls each builder repeatedly with perturbed params
├── additional_analyses.py  # Section 11: cost breakdown, cross-route tornado, 2D heatmaps
└── outputs/
    └── (one results file per route, same schema — Section 8)
```

**What each shared module guarantees, concretely:**
- `parameters.py` is the single source of truth for every literature-sourced number — no model
  file ever hardcodes a μmax/Yxs/titer/ε locally.
- `reactors.py`'s single class means the extent/D-margin design method (Section 5) is implemented
  exactly once — fructose, acetate, and formate run the same code with different parameter inputs,
  not three independently-written implementations that could diverge.
- `economics.py` guarantees all four TEAs share the same dollar-year/CEPCI/financing basis — this
  is what makes the four final MSPs comparable at all; a silently different CEPCI year in one model
  would invalidate the cross-route comparison without anyone noticing.
- `export.py` guarantees an identical equipment-list/stream-table schema across all four routes,
  per Section 8's requirements.

**Automated cross-model consistency check, on top of the shared-module structure — not a
substitute for it.** Shared modules prevent drift *by construction*, but don't catch a case where
someone hardcodes something locally during active development instead of importing it. A short
check (script or test suite), run after all four models are built, asserting: all four TEA objects
reference the same dollar-year/CEPCI; all four use the same operating-hours figure (Section 5a);
all four equipment exports share the same column schema (Section 8). Catches accidental drift
rather than relying on the structure alone to prevent it.

**Resolved (2026-08-10):** all four route models are implemented and working. Modules import from
`common/` via relative imports (e.g., `from common.parameters import ...`). No editable package
install is required.

## 11. Sensitivity Analysis

**Method: one-at-a-time (OAT) tornado analysis, Monte Carlo not pursued for now.** Vary each
parameter individually across a defined range while holding all others at base-case value; record
the resulting swing in MSP (and CAPEX/OPEX components); rank by impact. Run identically across all
four routes — same method, same range-setting convention per Section 10's consistency principle —
so tornado diagrams are comparable route-to-route, not just internally consistent within one route.

**Scope boundary:** BioSTEAM-side sensitivity covers MSP/CAPEX/OPEX only. GWP/impact-category
sensitivity is openLCA's job (Section 8) — openLCA has its own Monte Carlo/uncertainty tooling;
duplicating it inside BioSTEAM would be redundant work outside this project's boundary.

**Decision: no SA on biological/kinetic parameters** (μmax, Yxs, titer) — excluded per user decision.
These are treated as fixed, sourced inputs (Section 9), not swept. SA is scoped to design-choice,
reliability, and economic/TEA parameters instead.

**Implemented SA parameters (11 total, as of 2026-08-10):**

| # | Label | Category | Lo | Hi | Rel? | Justification | §9 ref |
|---|-------|----------|----|----|------|---------------|--------|
| 1 | Substrate conversion (ε) | route | 0.80 | 0.95 | abs | Engineering judgment; gas_fermentation base=0.99, lo omitted (see note below) | §9.2 |
| 2 | Dilution rate (fraction of μmax) | route | 0.70 | 0.85 | abs | Engineering judgment | §9.2 |
| 3 | Target titer (fraction of max) | route | 0.60 | 0.90 | abs | Engineering judgment | §9.2 |
| 4 | Centrifuge recovery (% biomass) | global | 0.90 | 0.98 | abs | Engineering judgment | §9.2 |
| 5 | Restart frequency (per line/yr) | global | 1.0 | 4.0 | abs | 12-month campaigns (1/yr) to 90-day campaigns (4/yr) | §9.2 |
| 6 | Nutrient recipe scaling (×base) | global_recipe_conc | ×0.50 | ×1.50 | rel | §9.3 range 0.20–0.59 g/g at ×0.50/×1.50 of recipe | §9.3 |
| 7 | Feedstock price ($/kg) | route | ×0.50 | ×1.50 | rel | ±50% — commodity market uncertainty | §9.4 |
| 8 | Electricity price ($/kWh) | economics | 0.020 | 0.087 | abs | DOE Wind PPA floor to US industrial grid (Apr 2026) | §9.4 |
| 9 | Capital cost (TCI ±35%) | economics | ×0.65 | ×1.35 | rel | Turton BM method accuracy ±35%; FCI = 1.18 × IEC scales linearly | §9.4 |
| 10 | Water recycle fraction | global | 0.50 | 0.90 | abs | Engineering range; base 0.75 keeps recycle loop a contraction mapping; lower → more fresh-water makeup; upper bound avoids accumulation risk | §9.2 |

**Notes on closed §9.4 decisions:** parameters marked "n/a" in the §9.4 registry (theta_O2,
fringe_benefits, supplies, IRR, labor_cost, and all other fixed FOC fractions not listed above)
are closed decisions — sourced and fixed; sensitivity on them was deemed not warranted.

**Gas-fermentation ε note:** base ε = 0.99; the lo perturbation (ε = 0.80) is so far below the
base that it does not constitute a useful one-at-a-time perturbation and is omitted. Only the
value ε = 0.95 (stored in the `hi` slot of `_SAParam` because the `lo` slot is skipped for this
route) is run. Because 0.95 < 0.99 (base), the output labels this perturbation "low" — direction
is assigned by comparing the actual perturbed value to the base, not by which `_SAParam` slot
the value came from. This general rule ensures correct labeling whenever the base falls outside
the nominal lo/hi range.

**Global-parameter patching:** global parameters require patching every module that bound the name
at import time — not just `common.parameters`. Patch targets per parameter:

- `CENTRIFUGE_RECOVERY` — `common.parameters` + all four model modules (5 targets)
- `RESTART_FREQUENCY_PER_LINE` — `common.parameters` + `common.operating_hours` (as
  `CONTAMINATION_RESTART_H = val × RESTART_DURATION_H`) + `common.seed_train` (same derived value); 3 targets
- `NUTRIENTS_RECIPE` — `common.parameters` + all four model modules + `common.chemicals` (6 targets)
- `WWT_WATER_RECYCLE_FRACTION` — `common.parameters` + `common.wastewater` + all four model modules (6 targets);
  model files use it to compute the recycle-water convergence seed at build time, `common.wastewater`
  reads it at call time inside `build_wastewater_treatment()`

The `_patch_attrs` / `_global_patches` helpers in `sensitivity_analysis.py` implement this.

**Output files from `sensitivity_analysis.py`** (written to `outputs/`):
- `sensitivity_results.xlsx` — three sheets:
  - *OAT Results* — one row per (route × parameter × direction); columns include Base/Perturbed
    MSP, MSP swing ($/kg and %), design variables (op_hours, FCI, N_reactors, N_seed_trains,
    Q m³/h), and a full per-run OPEX breakdown: Feedstock, Ammonia, Nutrients, Electricity,
    Other utilities, Waste disposal, Labor, Maintenance, Other FOC, Capital charge — each in
    both $/kg and $MM/yr. Capital charge is the MSP residual (= depreciation + tax + required
    return), ensuring every row sums exactly to the perturbed MSP.
  - *Tornado Summary* — one row per parameter, sorted descending by max |swing| across all
    routes and directions; includes lo/hi swing and range columns per route.
  - *Base Case Design* — one row per route: base MSP, design variables, and the full OPEX
    breakdown at base conditions — the "control" reference for interpreting OAT rows.
- `sensitivity_tornado_{route}.png` — one per route (4 files for a full run).

**Additional analyses** (`additional_analyses.py` — run after `sensitivity_analysis.py`,
89 simulations):
- *Cost breakdown* (`cost_breakdown.png`, `cost_breakdown.xlsx`) — MSP decomposed into the same
  10 OPEX categories as OAT Results, shown as a stacked-bar chart per route and tabulated with
  $/yr, $/kg SCP, and % of MSP columns.
- *Cross-route tornado* (`cross_route_tornado.png`) — grouped horizontal bar chart comparing
  each parameter's total MSP swing range across all four routes on a shared log-scale x-axis;
  reads `sensitivity_results.xlsx` only, no new simulations.
- *2D sensitivity heatmaps* (`2d_sa_{route}.png`, `2d_sa_results.xlsx`) — MSP surfaces over
  two dominant parameters simultaneously: electricity price × TCI for gas fermentation (25 runs),
  feedstock price × ε for each liquid route (20 runs × 3 routes = 60 runs). Base-case cell
  highlighted; MSP annotated per cell.

**Why this matters beyond just reporting a diagram:** this is also the mechanism for deciding how
much further literature effort a given assumption deserves — if MSP barely moves across a
parameter's reasonable range, that's a legitimate reason to stop refining it (as discussed for
fructose's unresolved Ks); if it swings MSP substantially, that's where more sourcing effort or a
tighter design margin is actually warranted, rather than treating every open item in Section 9 as
equally worth chasing.
