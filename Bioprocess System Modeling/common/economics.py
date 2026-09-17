"""SCPTEA class and build_tea / solve_msp factory functions.

Public items
------------
SCPTEA      — bst.TEA subclass; defines _FOC and _FCI, inherits _DPI / _TDC
              defaults from bst.TEA.
build_tea() — one factory call, same EconomicBasis, different System per route.
solve_msp() — thin wrapper around tea.solve_price(product_stream).

Modeled directly on biorefineries.tea.ConventionalEthanolTEA (Huang, Long &
Singh 2016), confirmed from installed source: that class also defines only
_FOC and _FCI and zeros out startup ramp-up and project financing.

Framework §3a / §9.4 / Spec §common/economics.py.
"""

from __future__ import annotations
import biosteam as bst

from common.operating_hours import effective_operating_hours
from common.parameters import EconomicBasis


class SCPTEA(bst.TEA):
    """BioSTEAM TEA subclass shared by all four SCP routes.

    Only _FOC and _FCI are overridden; _DPI and _TDC inherit bst.TEA defaults
    (same as ConventionalEthanolTEA).  All six fixed-operating-cost categories
    are independently sourced in Framework §9.4 — not collapsed to a single
    blended overhead factor.

    Startup ramp-up and project debt financing are both zeroed, following the
    ConventionalEthanolTEA convention and Framework §9.4.
    """

    def __init__(
        self,
        system: bst.System,
        economics: EconomicBasis,
    ) -> None:
        # Store FOC line items for _FOC() — Framework §9.4
        self.property_tax       = economics.property_tax
        self.property_insurance = economics.property_insurance
        self.maintenance        = economics.maintenance
        self.administration     = economics.administration
        self.labor_cost         = economics.labor_cost
        self.fringe_benefits    = economics.fringe_benefits
        self.supplies           = economics.supplies
        # Turton BM method — Framework §9.4
        self.contingency_fee_factor = economics.contingency_fee_factor

        super().__init__(
            system=system,
            IRR=economics.IRR,
            duration=economics.duration,
            depreciation=economics.depreciation,
            income_tax=economics.income_tax,
            operating_days=effective_operating_hours() / 24.0,   # Framework §5a
            lang_factor=None,   # None → system.installed_equipment_cost = Σ(u.installed_cost) = Σ(C_P × f_BM)
            construction_schedule=economics.construction_schedule,
            WC_over_FCI=economics.WC_over_FCI,
            # Startup ramp-up — zeroed per ConventionalEthanolTEA / Framework §9.4
            startup_months=0.0,
            startup_FOCfrac=0.0,
            startup_VOCfrac=0.0,
            startup_salesfrac=0.0,
            # Project debt financing — zeroed per ConventionalEthanolTEA / Framework §9.4
            finance_interest=0.0,
            finance_years=0,
            finance_fraction=0.0,
        )

    def _FCI(self, TDC: float) -> float:
        # Turton (7th ed.) Table 16.1: FCI = Σ(C_BM) × (1 + contingency + fees).
        # TDC = DPI = installed_equipment_cost = Σ(u.installed_cost) = Σ(C_P × f_BM).
        # contingency_fee_factor = 1.18 (Framework §9.4).
        return self.contingency_fee_factor * TDC

    def _FOC(self, FCI: float) -> float:
        # Six independently-sourced categories — Framework §9.4.
        # Structure mirrors ConventionalEthanolTEA._FOC() exactly.
        # Sum annual_om_usd from any UltrafiltrationSterilizer units (gas ferm only)
        uf_om = sum(getattr(u, 'annual_om_usd', 0.0) for u in self.system.units)
        return (
            FCI * (self.property_tax + self.property_insurance
                   + self.maintenance + self.administration)
            + self.labor_cost * (1.0 + self.fringe_benefits + self.supplies)
            + uf_om       # Guo et al. (2014) UF O&M — Framework §4a, gas ferm only
        )


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def build_tea(system: bst.System, economics: EconomicBasis) -> SCPTEA:
    """Build and return an SCPTEA for a fully simulated system.

    CEPCI is set by configure_utility_prices() before simulate(), which is the
    correct point — BioSTEAM caches unit purchase costs during simulation.
    The assignment here is retained as belt-and-suspenders for callers that
    construct a TEA without going through a model builder (e.g. test scripts).

    Called identically for all four routes — same EconomicBasis, different System.
    Framework §3a / Spec §run_models.py call pattern.
    """
    bst.settings.CEPCI = economics.CEPCI    # belt-and-suspenders; authoritative set is in configure_utility_prices()
    return SCPTEA(system=system, economics=economics)


def configure_utility_prices(economics: EconomicBasis) -> None:
    """Apply Framework §9.4 utility prices and CEPCI to BioSTEAM's global settings.

    Must be called after bst.settings.set_thermo() and before system.simulate().
    BioSTEAM utility agents and CEPCI are module-level singletons; this function
    sets them so simulation costs reflect Framework §9.4 values rather than
    BioSTEAM package defaults.

    CEPCI (Framework §9.4):
        bst.settings.CEPCI must be set BEFORE simulate() because BioSTEAM caches
        unit purchase costs during simulation using whatever CEPCI is current at
        that moment.  build_tea() is called after simulate(), so setting CEPCI
        there is too late — unit costs would reflect BioSTEAM's built-in reference
        year (567.3, 2017) instead of the project dollar year (809.3, 2025).
        Setting it here guarantees the correct escalation regardless of whether
        this route runs in isolation or after other routes.

    Pricing mechanism (confirmed from installed bst.HeatUtility source):
        cost [$/h] = heat_transfer_price [$/kJ] * |duty| [kJ/h]
                   + regeneration_price [$/kmol] * F_mol [kmol/h]

    Electricity (Framework §9.4):
        bst.PowerUtility.price set to economics.electricity_price ($/kWh).

    Steam — all steam agents (LP/MP/HP) set to economics.steam_price ($/GJ):
        heat_transfer_price = steam_price / 1e6  [$/kJ]  (price per GJ of heat)
        regeneration_price  = 0.0  (zeroed — pricing via heat duty, not steam flow)
        natural_gas agent left at default — different pricing basis, not used here.

    Cooling water (Framework §9.4):
        regeneration_price = cooling_water_price / 1000 * cw.MW  [$/kmol]
        Converts from $/m3 assuming liquid water density = 1000 kg/m3.
        heat_transfer_price left at 0.0 (volume-based pricing is correct for CW).

    Chilled water (Framework §9.4):
        heat_transfer_price = chilled_water_price / 1e6  [$/kJ]
        BioSTEAM selects chilled water when the process target T is below cooling
        water's T_supply (32.2 °C); e.g. fermentation at 30 °C.  Seider et al.
        Table 8.3: $5/GJ.  regeneration_price zeroed — pricing via duty, not flow.

    Framework §9.4.
    """
    bst.settings.CEPCI = economics.CEPCI       # dollar-year escalation — must precede simulate()
    # Electricity — Framework §9.4
    bst.PowerUtility.price = economics.electricity_price           # $/kWh

    # Steam (LP, MP, HP) — Framework §9.4: single $/GJ price for all grades
    steam_price_per_kJ = economics.steam_price / 1e6              # $/GJ → $/kJ
    for agent in bst.HeatUtility.heating_agents:
        if 'steam' in agent.ID:
            agent.heat_transfer_price = steam_price_per_kJ
            agent.regeneration_price  = 0.0

    # Cooling water — Framework §9.4: $/m³ → $/kmol via water density and MW
    cw = next(a for a in bst.HeatUtility.cooling_agents
              if a.ID == 'cooling_water')
    cw.regeneration_price  = economics.cooling_water_price / 1000.0 * cw.MW
    cw.heat_transfer_price = 0.0

    # Chilled water — Framework §9.4: $/GJ → $/kJ
    # BioSTEAM selects chilled water when cooling target < cooling_water T_supply
    # (e.g. fermentation at 30 °C).  Seider et al. Table 8.3: $5/GJ.
    chw = next(a for a in bst.HeatUtility.cooling_agents
               if a.ID == 'chilled_water')
    chw.heat_transfer_price = economics.chilled_water_price / 1e6  # $/GJ → $/kJ
    chw.regeneration_price  = 0.0


def solve_msp(tea: SCPTEA, product_stream: bst.Stream) -> float:
    """Return minimum selling price ($/kg) for product_stream.

    The single consistent MSP mechanism across all four routes.
    Thin wrapper around bst.TEA.solve_price() — Framework §3a.
    """
    return tea.solve_price(product_stream)
