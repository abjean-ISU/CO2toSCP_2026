"""Closed droplet column for gas fermentation pre-saturation.

Liquid media is dispersed as droplets in a gas-filled pressure vessel; all gas
feed dissolves into the liquid outlet (no vent, no gas outlet stream).  Two
sets are used in series: DC101 (H2) and DC102 (CO2 + O2 mixture), kept
separate to prevent H2/O2 contact in the gas phase.  Framework §4a.

Costed as vertical pressure vessel (Stainless steel 316) using BioSTEAM's
PressureVessel mixin — same correlations as the ExtentBasedBioreactor vessels.

Public class
------------
DropletColumn — one class, instantiated twice with different gas feeds.

Framework §4a / Spec §perfusion_bioreactor/droplet_column.py.
"""

from __future__ import annotations
import math

import biosteam as bst
from biosteam.units.design_tools import PressureVessel


class DropletColumn(bst.Unit, PressureVessel):
    """Closed droplet column for pre-saturating liquid media with dissolved gas.

    Liquid is dispersed as droplets in the gas phase inside a sealed pressure
    vessel.  The gas feed stream is sized by the caller so that its total mass
    flow equals the dissolved-gas mass flow leaving in the liquid outlet
    (Framework §4a "gas feed = dissolved gas rate").  No gas outlet stream.

    Fixed vessel geometry (Framework §4a — both DC101 and DC102):

    ============ ========
    Height       4 m
    Diameter     10 m
    Pressure     4 atm
    Max liq. Q   q_max_m3s (default 0.577 m³/s) per column
    Material     SS316
    ============ ========

    Number of parallel columns N = ceil(Q_liquid / q_max_m3s).
    Costed as N vertical pressure vessels via BioSTEAM's PressureVessel mixin.

    Parameters
    ----------
    dissolved_species : dict[str, float]
        Chemical ID → design dissolved concentration (g/L) in liquid outlet.
        Stored in design_results for export and cross-check; the caller is
        responsible for sizing the gas feed stream to match these values.

    Ins
    ---
    [0] liquid_feed  — pressurised sterile media (4 atm, liquid phase)
    [1] gas_feed     — gas to be dissolved (H2 for DC101; CO2+O2 for DC102);
                       caller sets imass to match dissolved-gas demand

    Outs
    ----
    [0] liquid_out   — media with dissolved gas, forced liquid phase, 4 atm
    """

    # Fixed vessel geometry — Framework §4a
    _HEIGHT_M    = 4.0    # m
    _DIAMETER_M  = 10.0   # m
    _P_ATM       = 4.0    # atm (operating and design pressure)

    # PressureVessel mixin settings (confirmed: SS316 factor = 2.1, rho = 499.4 lb/ft³)
    # vessel_type as a class attribute shadows the PressureVessel property descriptor,
    # which is fine — the mixin's _vessel_design() reads self.vessel_type and gets 'Vertical'.
    vessel_type = 'Vertical'

    # _F_BM_default must be defined here so Unit.__init__ copies it to self.F_BM.
    # Without this, Unit._F_BM_default = {} is found first in the MRO (Unit precedes
    # PressureVessel), and self.F_BM ends up empty — _load_costs() then defaults to 1.
    # Values from PressureVessel._F_BM_default (vertical vessel = 4.16, ladders = 1.0).
    _F_BM_default = {'Vertical pressure vessel': 4.16, 'Platform and ladders': 1.0}

    _N_ins  = 2   # (liquid_feed, gas_feed)
    _N_outs = 1   # (liquid_out,)

    # Merge PressureVessel unit labels (Weight, Diameter, etc.) with ours
    _units = {
        **PressureVessel._units,
        'Number of columns':      '',
        'Liquid flow per column': 'm³/s',
    }

    def __init__(self, ID='', ins=None, outs=(), thermo=None,
                 dissolved_species=None, q_max_m3s: float = 0.577):
        super().__init__(ID, ins, outs, thermo)
        # Use the property setter so F_M is populated correctly (SS316 = 2.1).
        # Setting _vessel_material as a class attribute bypasses the setter and
        # leaves self.F_M empty, causing _load_costs() to apply no material factor.
        self.vessel_material = 'Stainless steel 316'
        if dissolved_species is None:
            raise ValueError(
                "dissolved_species (dict: chem_id → g/L) is required — Framework §4a"
            )
        self.dissolved_species = dissolved_species
        self.q_max_m3s = q_max_m3s  # m³/s per column — Framework §4a; SA-patchable

    # ------------------------------------------------------------------
    # Core simulation
    # ------------------------------------------------------------------

    def _run(self):
        liquid_feed, gas_feed = self.ins
        liquid_out = self.outs[0]

        # Closed vessel — all gas dissolves into liquid (Framework §4a)
        liquid_out.mix_from([liquid_feed, gas_feed])
        liquid_out.phase = 'l'                  # dissolved gas, not headspace
        liquid_out.T = liquid_feed.T
        liquid_out.P = self._P_ATM * 101325     # atm → Pa

    # ------------------------------------------------------------------
    # Design
    # ------------------------------------------------------------------

    def _design(self):
        liquid_feed = self.ins[0]
        Q_m3s = liquid_feed.F_vol / 3600.0      # m³/h → m³/s

        N = max(1, math.ceil(Q_m3s / self.q_max_m3s))

        # Convert to PressureVessel expected units (ft, psia)
        D_ft  = self._DIAMETER_M * 3.28084      # m → ft
        L_ft  = self._HEIGHT_M   * 3.28084      # m → ft
        P_psi = self._P_ATM      * 14.6959      # atm → psia

        self.design_results.update({
            'Number of columns':      N,
            'Liquid flow per column': Q_m3s / N,   # m³/s; ≤ self.q_max_m3s by construction
        })
        # _vessel_design returns a dict; merge into design_results
        self.design_results.update(
            self._vessel_design(float(P_psi), float(D_ft), float(L_ft))
        )

        # N parallel vessels — BioSTEAM multiplies baseline_purchase_costs by N
        self.parallel['self'] = N

    # ------------------------------------------------------------------
    # Costing
    # ------------------------------------------------------------------

    def _cost(self):
        D = self.design_results
        # Returns {'Vertical pressure vessel': cost, 'Platform and ladders': cost}
        # F_M (SS316 = 2.1) and F_BM (vertical = 4.16) applied automatically
        self.baseline_purchase_costs.update(
            self._vessel_purchase_cost(D['Weight'], D['Diameter'], D['Length'])
        )
