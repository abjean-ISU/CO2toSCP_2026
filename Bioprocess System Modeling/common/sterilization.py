"""UltrafiltrationSterilizer — pass-through media sterilization unit costed from
Guo, Englehardt & Wu (2014) Water Sci. Technol. WST-EM13819.

Used only in the gas fermentation route (Framework §4a). Numbers up at
Q_max = 378,500 m³/d (top of validated range). Capital / O&M in 2012 USD,
CEPCI-escalated to the project dollar year.
"""
import math
import biosteam as bst

# Guo et al. (2014) Table 1 — UF, constant 2012 USD, x = capacity (m³/d)
_CAP_ALPHA, _CAP_BETA, _CAP_C = 1.003, 0.830, 3.832   # capital
_OM_ALPHA,  _OM_BETA,  _OM_C  = 1.828, 0.598, 1.876   # annual O&M
_Q_MAX_M3D  = 378_500.0   # m³/d — upper bound of Guo et al. validated range
_CEPCI_2012 = 585.0       # bst.units.design_tools.CEPCI_by_year[2012]


class UltrafiltrationSterilizer(bst.Unit):
    """Ultrafiltration media sterilizer — gas fermentation route.

    Pass-through: liquid composition unchanged at TEA level (microbial removal
    not tracked in chemical component space). Numbered up at Q_max per unit.
    Capital and O&M: Guo et al. (2014) Table 1, CEPCI-escalated.

    Parameters
    ----------
    contingency_fee_factor : float
        Turton contingency + contractor fees multiplier (Framework §9.4 = 1.18).
        Guo et al. capital cost treated as total installed capital → divided by
        contingency_fee_factor (× BM=1.0) so that TEA FCI contribution recovers
        Guo et al. capital: FCI_contrib = contingency_fee_factor × installed_cost
        = contingency_fee_factor × (purchase_cost × BM) = contingency_fee_factor
        × (Guo_capital / contingency_fee_factor × 1.0) = Guo_capital.
    """
    _N_ins = 1
    _N_outs = 1

    def __init__(self, ID='', ins=None, outs=(), contingency_fee_factor: float = 1.18, **kwargs):
        super().__init__(ID, ins, outs, **kwargs)
        self._contingency_fee_factor = contingency_fee_factor

    def _run(self):
        # Pass-through — UF removes microbial contaminants; media composition
        # unchanged at TEA resolution (Framework §4a)
        self.outs[0].copy_like(self.ins[0])

    def _design(self):
        Q_m3h = self.ins[0].F_vol             # m³/h volumetric flow
        Q_m3d = Q_m3h * 24.0                  # convert to m³/d
        N = max(1, math.ceil(Q_m3d / _Q_MAX_M3D))
        self.design_results['N_UF_units'] = N
        # 'Number of parallel reactors' is the key read by export._build_equipment_list()
        # to populate the N (parallel) column and split per-unit costs correctly.
        self.design_results['Number of parallel reactors'] = N
        self.design_results['Q_per_unit_m3d'] = Q_m3d / N   # actual throughput per unit
        # Annual O&M stored for SCPTEA._FOC pickup — Guo et al. (2014), CEPCI-escalated
        cepci_ratio = bst.CE / _CEPCI_2012    # bst.CE == bst.settings.CEPCI (same object)
        om_2012 = N * 10 ** (_OM_ALPHA * math.log10(_Q_MAX_M3D) ** _OM_BETA + _OM_C)
        self.annual_om_usd = om_2012 * cepci_ratio    # $/yr, current-year USD

    def _cost(self):
        N = self.design_results['N_UF_units']
        cepci_ratio = bst.CE / _CEPCI_2012
        cap_2012 = N * 10 ** (_CAP_ALPHA * math.log10(_Q_MAX_M3D) ** _CAP_BETA + _CAP_C)
        cap_current = cap_2012 * cepci_ratio
        # Divide by contingency_fee_factor (× BM=1.0) so FCI contribution = Guo et al. capital.
        # (Guo et al. 2014 cost = total installed; Framework §4a UF sterilization)
        self.baseline_purchase_costs['UF membrane system'] = (
            cap_current / self._contingency_fee_factor
        )


class HoldPipe(bst.Unit):
    """Hold section for continuous heat sterilization.

    Insulated pipe between the sterilization heater (HX101/SHX101) and the
    cooling heat exchanger (HX102/SHX102). Stream passes through at
    T_STERILIZATION_K = 134 °C for tau_min minutes.
    Stanbury, Whitaker & Hall (2017) §Sterilization: 2.44 min at 134 °C.

    Capital cost: not included — negligible relative to FCI for all routes
    (< 0.01 % FCI at design flows; extrapolates bst.MixTank cost correlation).
    Standard conceptual-TEA omission. Framework §9.2.

    Parameters
    ----------
    tau_min : float
        Hold time [minutes]. Default 2.44 (Stanbury et al. 2017 §Sterilization).
    """
    _N_ins = 1
    _N_outs = 1

    def __init__(self, ID='', ins=None, outs=(), tau_min: float = 2.44, **kwargs):
        super().__init__(ID, ins, outs, **kwargs)
        self.tau_min = tau_min   # minutes — Stanbury et al. (2017) §Sterilization

    def _run(self):
        # Pass-through: temperature held by insulation (set upstream by HXutility).
        self.outs[0].copy_like(self.ins[0])

    def _design(self):
        # Expose hold time in design results for system reports.
        self.design_results['Hold time (min)'] = self.tau_min
