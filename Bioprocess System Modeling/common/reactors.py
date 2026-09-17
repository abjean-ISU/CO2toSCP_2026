"""ExtentBasedBioreactor: single AeratedBioreactor subclass for all three
liquid-substrate SCP routes (fructose, acetate, formate).

Public class
------------
ExtentBasedBioreactor — continuous chemostat with extent-based conversion.

Gas fermentation does NOT use this class — see
perfusion_bioreactor/unitwithauxiliary.py and SCP_Perfusion_Bioreactor_Math.md.

Framework §5b / Spec §common/reactors.py.
"""

from __future__ import annotations
import biosteam as bst

from common.parameters import THETA_O2


class ExtentBasedBioreactor(bst.AeratedBioreactor):
    """Continuous aerated bioreactor using extent-based conversion (Framework §5).

    Implements the Framework §5 chemostat design method:
      - tau = 1 / (D_margin × mu_max) set at construction — Framework §5 step 5
      - Conversion = epsilon, encoded in the reactions object (X=epsilon) and
        enforced by the parent's _run_reactions() → reactions.force_reaction().
        No Monod/Haldane solve; no _run() override.
      - N+1 redundancy vessel added in _design() after the auto-solve for
        N_capacity — Framework §5 step 9.

    Key BioSTEAM defaults overridden here (confirmed from installed source):
      - batch=False  (AeratedBioreactor.batch_default = True; chemostat is continuous)
      - theta_O2=THETA_O2  (0.5; same as BioSTEAM default but set explicitly per
        Framework §5b / §9.2 — not left at default without stating the decision)

    _design() N+1 mechanism: super()._design() auto-solves N_capacity and stores
    design_results['Reactor volume'] = V_total / N_capacity.  Incrementing
    self.parallel['self'] after that call causes BioSTEAM's cost model to price
    N_capacity+1 vessels each at V_total/N_capacity — one additional full-capacity
    spare, which is the Framework §5 intent.

    Parameters
    ----------
    reactions : bst.Reaction
        Growth reaction built by the route model builder from
        common.kinetics.compute_O2_CO2_H2O_coefficients() coefficients and
        X=epsilon.  Yxs sets the biomass stoichiometric coefficient directly.
    mu_max : h⁻¹
        Maximum specific growth rate (Framework §9.1).
    D_margin : float
        Fraction of mu_max used as dilution-rate setpoint (Framework §9.2).
    **kwargs
        Forwarded to AeratedBioreactor._init() (e.g. V_max, vessel_material).
    """

    def _init(
        self,
        reactions: bst.Reaction,
        mu_max: float,
        D_margin: float,
        **kwargs,
    ) -> None:
        self.mu_max = mu_max
        self.D_margin = D_margin
        tau = 1.0 / (D_margin * mu_max)      # h — Framework §5 step 5
        super()._init(
            reactions=reactions,
            tau=tau,
            theta_O2=THETA_O2,               # 0.5 — Framework §9.2 / §5b decision
            batch=False,                     # continuous chemostat; AeratedBioreactor.batch_default=True
            **kwargs,
        )

    def _run_vent(self, vent, effluent) -> None:
        super()._run_vent(vent, effluent)
        # receive_vent (thermosteam) clips negative *liquid* flows and moves them
        # to the vapor side, but has no corresponding fix for negative *vapor*
        # flows.  Two components hit this:
        #   NH3: Psat >> P at 30°C, so receive_vent assigns all NH3 to vapor
        #     initially, then the VLE correction at x[NH3]≈0 produces a negative
        #     mol_v — numerical artifact of near-zero liquid concentration.
        #   Nutrients (phase='l' pseudo-component): Psat() raises an exception
        #     inside receive_vent's assignment loop so the component is skipped;
        #     the subsequent VLE step gives it a spurious negative gas-phase flow.
        # Fix: mirror receive_vent's own liquid-side correction on the vapor side.
        negative = vent.mol < 0.0
        if negative.any():
            effluent.mol[negative] += vent.mol[negative]
            vent.mol[negative] = 0.0
        # Safety floor: even with the 5 % NH3/Nutrients supplement
        # (NH3_NUTRIENTS_EXCESS — Framework §9.2), BioSTEAM's VLE routes residual
        # free-NH3 to the vent (Psat >> P at 30 °C), so the effluent NH3 can still
        # reach near-zero and cross negative after the vent fix above.  Floor here
        # as a belt-and-suspenders measure; mass balance error ≤ convergence
        # tolerance — negligible for TEA/LCA.
        neg_liq = effluent.mol < 0.0
        if neg_liq.any():
            effluent.mol[neg_liq] = 0.0

    def _design(self) -> None:
        super()._design()                    # auto-solves N_capacity → self.parallel['self']
        self.parallel['self'] += 1          # N+1 redundancy vessel — Framework §5 step 9


class SeedBioreactor(bst.AeratedBioreactor):
    """Periodic-batch seed bioreactor modeled in steady-state for TEA.

    Each seed stage is sized so that V_vessel = V_work_i / V_wf, achieved by
    setting tau = op_hours / (N_prod_total × RESTARTS_PER_YEAR).  The effective
    feed flow Q_seed_i = V_work_i × N_total × RESTARTS_PER_YEAR / op_hours then
    gives V = Q × tau = V_work_i, which is the correct batch working volume.

    No N+1 redundancy vessel — seed vessels can be rescheduled without a spare.
    Includes the same _run_vent numerical fix as ExtentBasedBioreactor.

    Parameters
    ----------
    reactions : bst.Reaction
        Same growth reaction as the production bioreactor.
    tau : float
        Residence time = op_hours / (N_prod_total × RESTARTS_PER_YEAR); computed
        by build_seed_train() from operating_hours and N_total — Framework §6.
    N_seed_trains : int
        Number of parallel seed trains required to cover all concurrent restart
        events.  Computed in build_seed_train() from N_prod_total,
        RESTARTS_PER_YEAR, and SEED_BATCH_DURATION_H — Framework §9.2.
        Defaults to 1 (correct for all three liquid routes; gas fermentation
        passes ~9).
    **kwargs
        Forwarded to AeratedBioreactor._init() (e.g. T, V_max).
    """

    def _init(
        self,
        reactions: bst.Reaction,
        tau: float,
        N_seed_trains: int = 1,
        **kwargs,
    ) -> None:
        self.N_seed_trains = N_seed_trains
        super()._init(
            reactions=reactions,
            tau=tau,
            theta_O2=THETA_O2,
            batch=False,
            **kwargs,
        )

    def _run_vent(self, vent, effluent) -> None:
        super()._run_vent(vent, effluent)
        # Same VLE numerical artifact fix as ExtentBasedBioreactor — see
        # ExtentBasedBioreactor._run_vent() docstring for root-cause analysis.
        negative = vent.mol < 0.0
        if negative.any():
            effluent.mol[negative] += vent.mol[negative]
            vent.mol[negative] = 0.0
        # Same safety floor as ExtentBasedBioreactor._run_vent() — see that
        # method for the full explanation.
        neg_liq = effluent.mol < 0.0
        if neg_liq.any():
            effluent.mol[neg_liq] = 0.0

    def _design(self) -> None:
        super()._design()   # auto-solves N_capacity → self.parallel['self'] = N_capacity
        # N_seed_trains parallel physical sets of seed vessels are required to cover
        # all concurrent restart events (Framework §9.2).  Override N_capacity
        # (which is 1 for all seed stage volumes) with N_seed_trains.
        self.parallel['self'] = max(1, self.N_seed_trains)
