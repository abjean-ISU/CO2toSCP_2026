# CLAUDE.md — SCP TEA/LCA Modeling Project

## Project

BioSTEAM techno-economic and life-cycle models comparing four single-cell protein (SCP)
production routes: fructose, acetate, formate, gas fermentation. Same host organism
(*C. necator*), same battery limits, same evaluation framework across all four — the point of
the project is that differences between routes reflect real process physics, not inconsistent
modeling choices between them.

## Authoritative sources — read before writing any code

- `docs/SCP_Project_Framework.md` — architecture, decisions, and reasoning for every choice
- `docs/SCP_Implementation_Spec.md` — function signatures, equations, pseudocode
- `docs/SCP_Perfusion_Bioreactor_Math.md` — full governing equations for the gas fermentation
  bioreactor

These are the single source of truth. Do not deviate from the architecture, equations, file
structure, or numeric methodology they specify without asking first. If something needed for
the current task isn't covered in these docs, stop and ask rather than inferring or improvising
a reasonable-sounding approach.

## Hard rules

**No invented values.** Never fill in a numeric parameter (kinetics, prices, economic
assumptions, design margins) that isn't already in the Framework's Section 9 parameter registry.
If a value is marked `*pending*` or missing, stop and ask — do not estimate, guess, or use a
plausible-sounding placeholder "just to get something running."

**No narrative self-assessment.** Generated docs, READMEs, and code comments report numbers and
methodology. Never add language asserting a result is "ECONOMICALLY VIABLE," "MARKET
COMPETITIVE," or similar — that pattern caused real problems in an earlier version of this
project and must not recur.

**Compute, don't assert — this is the project's core methodological principle.** Wherever a
quantity can be derived from other values already in the model, derive it live; never hardcode
a value that should be computed. Concrete examples already established in the framework:
- Nutrients mass fractions, MW, and composite price are computed from the raw recipe dict, not
  stored as separate literals (`common/nutrients.py`)
- O2/CO2/H2O stoichiometric coefficients are computed from the degree-of-reduction balance, not
  looked up (`common/kinetics.py`) — there is no "O2 parameter" to source
- Yxs sets the biomass:substrate `Reaction` coefficient directly; it is not a separate check
  value
If you're about to hardcode something that could instead be derived from existing inputs, don't
— ask if you're unsure whether it should be computed or is a genuine independent parameter.

**No unrequested restructuring.** Don't change the file layout, rename modules, or refactor
working code as a side effect of an unrelated task. Propose changes to structure separately and
wait for confirmation.

**One shared implementation per concern.** Logic that's common across routes lives once in
`common/` and gets imported, per the shared-module architecture in Framework Section 10. Route
model files (`models/*.py`) contain route-specific *parameters* wired into shared functions/
classes — not duplicated or route-specific reimplementations of the same logic.

**Build/run separation.** `models/*.py` files expose a `build_{route}_system()` function that
constructs and returns a `bst.System`. They do not call `.simulate()`, build a TEA, or run
exports themselves — that's `run_models.py`'s job, per the Implementation Spec.

**Cite reasoning, not just results.** When implementing something derived from the framework
docs (a design decision, a formula, a citation), leave a comment pointing at the relevant
Framework section — same standard the framework docs themselves hold to.

## Workflow

- Work in small increments: one `common/` module, or one route model, at a time. Stop after each
  and let it be reviewed before moving to the next.
- Use plan mode for anything touching more than one file.
- Build order: `common/chemicals.py` and `common/parameters.py` first (least dependent on
  anything else) → `common/kinetics.py` → `common/reactors.py` → `common/nutrients.py` →
  `common/economics.py` → `common/export.py`/`common/seed_train.py` → fructose model → acetate/
  formate models → gas fermentation model, per the Framework's stated build order.
- Verify BioSTEAM API behavior against the installed package (`inspect.getsource`, or the actual
  docs) rather than assuming from training data before relying on a specific method or default —
  this project has already caught real BioSTEAM behavior that didn't match assumption (e.g.
  `AeratedBioreactor`'s `N` auto-solve, `bst.TEA`'s default method coverage).
- When a change to a shared assumption is made, state which downstream values it affects —
  mirror how the framework docs cross-reference themselves rather than leaving a change isolated.

## When in doubt

Stop and ask. A clarifying question costs little; an invented value or an unrequested change
that has to be found and unwound later costs a lot — that's exactly the failure mode this project
has been built from the ground up to avoid.
