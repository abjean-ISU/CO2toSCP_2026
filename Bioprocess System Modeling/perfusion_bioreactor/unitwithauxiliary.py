"""
PerfusionBioreactor v2: Custom BioSTEAM unit for autotrophic C. necator cultivation.

This module implements a perfusion bioreactor unit operation for BioSTEAM that models
autotrophic Cupriavidus necator cultivation using proper auxiliary sub-units for
costing and sizing while preserving all validated perfusion kinetics.
"""

import biosteam as bst
import math

from common.operating_hours import effective_operating_hours


class PerfusionBioreactor(bst.Unit):
    """
    Perfusion bioreactor for autotrophic Cupriavidus necator cultivation.

    Models a perfusion bioreactor with internal auxiliary units:
    - Feed mixer (external feed + cell recycle)
    - CSTR (pressurized cell growth reactor)
    - Bleed splitter (perfusion vs bleed flow)
    - Cell separator (centrifuge for cell retention)
    - Harvest mixer (supernatant + bleed combination)

    All perfusion kinetics are computed manually (validated). Sub-units handle costing.

    Parameters
    ----------
    ID : str
        Unit ID string.
    ins : tuple
        Input streams: (combined_feed,) - contains dissolved H₂, O₂, CO₂, NH₃, and water.
    outs : tuple
        Output streams: (harvest_slurry,).
    V_max : float
        Reactor working volume, L.
    mu : float
        Specific growth rate, h⁻¹.
    S_f : float
        Feed H₂ concentration, g/L (updated dynamically in _run).
    n_CO2 : float
        Stoichiometric coefficient for CO₂, mol/mol biomass.
    n_NH3 : float
        Stoichiometric coefficient for NH₃, mol/mol biomass.
    n_H2 : float
        Stoichiometric coefficient for H₂, mol/mol biomass.
    n_O2 : float
        Stoichiometric coefficient for O₂, mol/mol biomass.
    n_H2O : float
        Stoichiometric coefficient for H₂O, mol/mol biomass.
    MW_biomass : float
        Molecular weight of biomass, g/mol.
    Y_mol : float
        Maximum yield on molar basis, g CDW/mol H₂.
    m_s_mol : float
        Maintenance coefficient on molar basis, mol H₂/g CDW/h.
    conversion : float, optional
        Fractional H₂ conversion (ε). Default: 0.9 — matches Framework §9.2
        epsilon for all four routes; was 0.99 (unjustified) in earlier version.
    eta : float, optional
        Cell retention efficiency of centrifuge. Default: 0.97.
    bleed_fraction : float, optional
        Bleed dilution rate as fraction of mu. Default: 0.20.
    moisture : float, optional
        Wet cake moisture content, mass fraction water. Default: 0.75.
    P_operating : float, optional
        Reactor operating pressure, atm. Default: 4.0.
    T_operating : float, optional
        Operating temperature, K. Default: 293.15.
    target_annual_biomass_MT : float, optional
        Annual biomass production target for scaling, MT/year.
    downstream_reactor : PerfusionBioreactor, optional
        Downstream reactor for inoculum-based scaling.
    target_inoculum_ratio : float, optional
        Inoculum ratio for pilot reactor scaling. Default: 0.10.
    biomass_id : str, optional
        Biomass component ID. Default: 'CNecatorBiomass'.
    h2_id : str, optional
        H₂ component ID. Default: 'H2'.
    o2_id : str, optional
        O₂ component ID. Default: 'O2'.
    co2_id : str, optional
        CO₂ component ID. Default: 'CO2'.
    nh3_id : str, optional
        NH₃ component ID. Default: 'NH3'.
    water_id : str, optional
        Water component ID. Default: 'H2O' — matches common/chemicals.py registry.
    ammonium_sulfate_id : str, optional
        Ammonium sulfate component ID. Default: 'AmmoniumSulfate'.
    sulfate_id : str, optional
        Sulfate component ID. Default: 'SO4'.
    nitrogen_source : str, optional
        Nitrogen source type: 'ammonia' or 'ammonium_sulfate'. Default: 'ammonia' —
        matches common/chemicals.py (NH3 present; AmmoniumSulfate not registered).
    kW_per_m3 : float, optional
        CSTR agitation power, kW/m³. Default: 2.0.
    vessel_material : str, optional
        Vessel material for costing. Default: 'Stainless steel 316'.
    heat_exchanger_configuration : str, optional
        Heat exchanger configuration. Default: 'recirculation loop'.
    centrifuge_type : str, optional
        Centrifuge type for costing. Default: 'scroll_solid_bowl'.
    debug : bool, optional
        Enable debug output. Default: False.

    Notes
    -----
    The reactor contains five internal sub-units:
    - Feed mixer for combining external feed and cell recycle
    - Pressurized CSTR for cell growth
    - Splitter for bleed stream control
    - SolidsCentrifuge for cell retention
    - Mixer for combining supernatant and bleed streams
    """

    _N_ins = 1
    _N_outs = 1

    auxiliary_unit_names = (
        'feed_mixer', 'cstr', 'bleed_splitter', 'cell_separator', 'harvest_mixer',
    )

    _units = {
        'Number of parallel reactors': '',
        'Reactor volume per unit (L)': 'L',
        'Total reactor volume (L)': 'L',
        'Cell density X': 'g/L',
        'Volumetric productivity': 'g/L/h',
        'Perfusion flow rate F': 'L/h',
        'Bleed flow rate Fb': 'L/h',
        'Dilution rate D': '1/h',
        'Residual substrate S': 'g/L',
        'Harvest cell density': 'g/L',
    }

    def __init__(self, ID='', ins=None, outs=(), thermo=None,
                 # Required parameters
                 V_max=None, mu=None, S_f=None,
                 # Stoichiometric coefficients (mol per mol biomass)
                 n_CO2=None, n_NH3=None, n_H2=None, n_O2=None, n_H2O=None,
                 MW_biomass=None,
                 # Kinetic parameters (mol basis, Siegel & Ollis 1984)
                 Y_mol=None, m_s_mol=None,
                 # Perfusion design
                 conversion=0.9, eta=0.97, bleed_fraction=0.20, moisture=0.75,  # conversion = ε, Framework §9.2
                 # Operating conditions
                 P_operating=4.0, T_operating=293.15,
                 # Parallel scaling (PRESERVED from validated code)
                 target_annual_biomass_MT=None,
                 downstream_reactor=None,
                 target_inoculum_ratio=0.10,
                 # Nutrients stoichiometry (Framework §9.3 / §9.5a)
                 nutrient_coefficient=None,  # g Nutrients / g biomass; required
                 # Component IDs
                 biomass_id='CNecatorBiomass', h2_id='H2', o2_id='O2',
                 co2_id='CO2', nh3_id='NH3', water_id='H2O',  # 'H2O' matches common/chemicals.py
                 nutrients_id='Nutrients',
                 ammonium_sulfate_id='AmmoniumSulfate', sulfate_id='SO4',
                 nitrogen_source='ammonia',  # NH3 is in chemicals registry; AmmoniumSulfate is not
                 # CSTR sub-unit parameters [NEW v2]
                 kW_per_m3=2.0,
                 vessel_material='Stainless steel 316',
                 heat_exchanger_configuration='recirculation loop',
                 centrifuge_type='scroll_solid_bowl',
                 # Debug
                 debug=False):

        super().__init__(ID, ins, outs, thermo)

        # Required parameters - raise errors if not provided
        if V_max is None:
            raise ValueError("V_max (reactor working volume, L) is required")
        if mu is None:
            raise ValueError("mu (specific growth rate, h⁻¹) is required")
        if S_f is None:
            raise ValueError("S_f (feed H₂ concentration, g/L) is required")
        if n_CO2 is None or n_NH3 is None or n_H2 is None or n_O2 is None or n_H2O is None:
            raise ValueError("All stoichiometric coefficients (n_CO2, n_NH3, n_H2, n_O2, n_H2O) are required")
        if MW_biomass is None:
            raise ValueError("MW_biomass (molecular weight of biomass, g/mol) is required")
        if Y_mol is None:
            raise ValueError("Y_mol (maximum yield, g CDW/mol H₂) is required")
        if m_s_mol is None:
            raise ValueError("m_s_mol (maintenance coefficient, mol H₂/g CDW/h) is required")
        if nutrient_coefficient is None:
            raise ValueError("nutrient_coefficient (g Nutrients/g biomass) is required — §9.3")

        # Store parameters
        self.V_max = V_max
        self.mu = mu
        self.S_f = S_f
        self.n_CO2 = n_CO2
        self.n_NH3 = n_NH3
        self.n_H2 = n_H2
        self.n_O2 = n_O2
        self.n_H2O = n_H2O
        self.MW_biomass = MW_biomass
        self.Y_mol = Y_mol
        self.m_s_mol = m_s_mol
        self.conversion = conversion
        self.eta = eta
        self.bleed_fraction = bleed_fraction
        self.moisture = moisture
        self.P_operating = P_operating
        self.T_operating = T_operating
        self.target_annual_biomass_MT = target_annual_biomass_MT
        self.downstream_reactor = downstream_reactor
        self.target_inoculum_ratio = target_inoculum_ratio
        self.debug = debug

        # Nutrients stoichiometry — Framework §9.3 / §9.5a
        self.nutrient_coefficient = nutrient_coefficient

        # Component IDs
        self.biomass_id = biomass_id
        self.h2_id = h2_id
        self.o2_id = o2_id
        self.co2_id = co2_id
        self.nh3_id = nh3_id
        self.water_id = water_id
        self.nutrients_id = nutrients_id

        # Nitrogen source configuration
        if nitrogen_source not in ['ammonia', 'ammonium_sulfate']:
            raise ValueError("nitrogen_source must be 'ammonia' or 'ammonium_sulfate'")
        self.nitrogen_source = nitrogen_source
        self.ammonium_sulfate_id = ammonium_sulfate_id
        self.sulfate_id = sulfate_id

        # CSTR sub-unit parameters
        self.kW_per_m3 = kW_per_m3
        self.vessel_material = vessel_material
        self.heat_exchanger_configuration = heat_exchanger_configuration
        self.centrifuge_type = centrifuge_type

        # Molecular weights (g/mol)
        self.MW_H2 = 2.016
        self.MW_CO2 = 44.01
        self.MW_O2 = 32.00
        self.MW_NH3 = 17.03
        self.MW_H2O = 18.02
        self.MW_AmmoniumSulfate = 132.14  # (NH4)2SO4
        self.MW_Sulfate = 96.06           # SO4²⁻

        # Initialize derived parameters
        self._calculate_stoichiometric_ratios()
        self._calculate_kinetic_parameters()
        self.load_auxiliaries()

    def _calculate_stoichiometric_ratios(self):
        """Calculate stoichiometric mass ratios from molar coefficients."""
        self.g_H2_per_gCDW  = (self.n_H2  * self.MW_H2)  / self.MW_biomass
        self.g_CO2_per_gCDW = (self.n_CO2 * self.MW_CO2) / self.MW_biomass
        self.g_O2_per_gCDW  = (self.n_O2  * self.MW_O2)  / self.MW_biomass
        self.g_NH3_per_gCDW = (self.n_NH3 * self.MW_NH3) / self.MW_biomass
        self.g_H2O_per_gCDW = (self.n_H2O * self.MW_H2O) / self.MW_biomass
        # Nutrients: coefficient already in g Nutrients / g CDW — Framework §9.3
        self.g_Nutrients_per_gCDW = self.nutrient_coefficient

    def _calculate_kinetic_parameters(self):
        """Convert molar kinetic parameters to mass basis."""
        self.Y_max = self.Y_mol / self.MW_H2  # g CDW / g H₂
        self.m_s = self.m_s_mol * self.MW_H2  # g H₂ / g CDW / h


    def load_auxiliaries(self):
        """Load auxiliary units for perfusion bioreactor."""

        self.auxiliary('feed_mixer', bst.Mixer, ins=(), outs=())
        self.auxiliary(
            'cstr', bst.CSTR, ins=(), outs=(),
            V_max=self.V_max / 1000.0,   # L → m³ for CSTR
            tau=1.0,                      # placeholder; updated in _run()
            T=self.T_operating,
            P=self.P_operating * 101325,
        )
        self.auxiliary('bleed_splitter', bst.Splitter, ins=(), outs=(), split=0.8)  # Default, updated in _run()
        self.auxiliary(
            'cell_separator', bst.SolidsCentrifuge,
            ins=(), outs=(),
            moisture_content=self.moisture,
            split={self.biomass_id: self.eta, self.water_id: 0.05},  # eta to cake (0th output)
        )
        self.auxiliary('harvest_mixer', bst.Mixer, ins=(), outs=())

    def _calculate_inlet_S_f(self):
        """Calculate actual S_f from inlet stream composition."""
        inlet = self.ins[0]
        total_vol_flow = inlet.F_vol * 1000   # m³/h → L/h
        if total_vol_flow > 1e-6:
            self.S_f = (inlet.imass[self.h2_id] * 1000) / total_vol_flow  # g H₂/L

    def _update_mass_flows(self):
        """Calculate all stoichiometric mass flows based on current CDW production."""
        self.CDW_produced       = self.mu * self.X * self.V_max
        self.H2_consumed        = self.g_H2_per_gCDW        * self.CDW_produced
        self.CO2_consumed       = self.g_CO2_per_gCDW       * self.CDW_produced
        self.O2_consumed        = self.g_O2_per_gCDW        * self.CDW_produced
        self.NH3_consumed       = self.g_NH3_per_gCDW       * self.CDW_produced
        self.H2O_produced       = self.g_H2O_per_gCDW       * self.CDW_produced
        self.Nutrients_consumed = self.g_Nutrients_per_gCDW * self.CDW_produced

    def _calculate_cell_densities(self, D_actual, S_f_used=None):
        """Calculate cell densities X and X_max based on dilution rate and substrate concentration."""
        if S_f_used is None:
            S_f_used = self.S_f
        self.X = D_actual * (S_f_used - self.S) / self.q_s
        self.X_max = D_actual * S_f_used / self.q_s

    def _calculate_parallel_scaling(self, required_flow_rate):
        """Calculate number of parallel reactor units needed."""
        flow_based_N = max(1, math.ceil(required_flow_rate / self.F_max_per_unit)) if required_flow_rate > 0 else 1
        N = flow_based_N

        if self.target_annual_biomass_MT is not None:
            N = self._apply_production_target_scaling(N, flow_based_N)
        elif self.downstream_reactor is not None:
            N = self._apply_inoculum_based_scaling(N, flow_based_N)

        return N

    def _apply_production_target_scaling(self, current_N, flow_based_N):
        """Apply production target scaling constraint."""
        target_biomass_rate_g_hr = self.target_annual_biomass_MT * 1000000 / effective_operating_hours()  # Framework §5a

        if self.CDW_produced > 0:
            target_based_N = max(1, math.ceil(target_biomass_rate_g_hr / self.CDW_produced))
            N = max(flow_based_N, target_based_N)
            if self.debug:
                print(f"DEBUG - {self.ID} scaling: Flow-based N={flow_based_N}, Target-based N={target_based_N}, Final N={N}")
        else:
            N = flow_based_N

        return N

    def _apply_inoculum_based_scaling(self, current_N, flow_based_N):
        """Apply inoculum-based scaling constraint."""
        try:
            if self.debug:
                print(f"DEBUG - {self.ID} inoculum scaling:")
                print(f"  Downstream reactor: {self.downstream_reactor.ID}")

            downstream_target_g_hr = self._get_downstream_target_production()
            required_inoculum_g_hr = downstream_target_g_hr * self.target_inoculum_ratio
            if self.debug:
                print(f"  Required inoculum: {required_inoculum_g_hr:.1f} g/h ({self.target_inoculum_ratio*100:.0f}%)")
                print(f"  My single reactor production: {self.CDW_produced:.1f} g/h")

            if self.CDW_produced > 0:
                calculated_N = required_inoculum_g_hr / self.CDW_produced
                inoculum_based_N = max(1, math.ceil(calculated_N))

                if inoculum_based_N > flow_based_N:
                    print(f"  WARNING: Inoculum requires {inoculum_based_N} units but flow only supports {flow_based_N}")
                    print(f"  Using flow-limited N={flow_based_N} (may not meet inoculum target)")
                    N = flow_based_N
                else:
                    N = inoculum_based_N

                if self.debug:
                    print(f"  Calculated N: {calculated_N:.1f} -> Inoculum N={inoculum_based_N}, Final N={N}")
            else:
                N = flow_based_N
                if self.debug:
                    print(f"  Zero production, using flow-based N={N}")

        except Exception as e:
            print(f"  Error in {self.ID} inoculum scaling: {e}")
            N = flow_based_N

        return N

    def _get_downstream_target_production(self):
        """Get downstream reactor's target production rate."""
        if hasattr(self.downstream_reactor, 'target_annual_biomass_MT') and self.downstream_reactor.target_annual_biomass_MT is not None:
            downstream_target_g_hr = self.downstream_reactor.target_annual_biomass_MT * 1000000 / effective_operating_hours()  # Framework §5a
            if self.debug:
                print(f"  Downstream target (from annual): {downstream_target_g_hr:.1f} g/h")
        elif hasattr(self.downstream_reactor, 'downstream_reactor') and self.downstream_reactor.downstream_reactor is not None:
            if hasattr(self.downstream_reactor.downstream_reactor, 'target_annual_biomass_MT') and self.downstream_reactor.downstream_reactor.target_annual_biomass_MT is not None:
                final_target_g_hr = self.downstream_reactor.downstream_reactor.target_annual_biomass_MT * 1000000 / effective_operating_hours()  # Framework §5a
                downstream_target_g_hr = final_target_g_hr * self.downstream_reactor.target_inoculum_ratio
                if self.debug:
                    print(f"  Downstream target (cascaded): {downstream_target_g_hr:.1f} g/h")
            else:
                downstream_target_g_hr = self._get_fallback_target()
                if self.debug:
                    print(f"  Downstream target (actual): {downstream_target_g_hr:.1f} g/h")
        else:
            downstream_target_g_hr = self._get_fallback_target()
            if self.debug:
                print(f"  Downstream target (fallback): {downstream_target_g_hr:.1f} g/h")

        return downstream_target_g_hr

    def _get_fallback_target(self):
        """Get fallback production target from downstream reactor actual production."""
        return getattr(self.downstream_reactor, 'CDW_produced', 0) * getattr(self.downstream_reactor, 'N', 1)

    def _solve_flow_balance(self):
        """Solve algebraic system for F and F_b that satisfy both flow conservation and cell balance."""
        F_total_actual_per_unit = self._required_flow_rate / self.N if self.N > 0 else 0

        if self.eta > 0 and F_total_actual_per_unit > 0:
            # Calculate EXTERNAL biomass input (fresh feed only, not recycle)
            inlet_stream = self.ins[0]
            if self.biomass_id in inlet_stream.chemicals.IDs and inlet_stream.F_vol > 0:
                X_in_fresh = inlet_stream.imass[self.biomass_id] / inlet_stream.F_vol  # g/L
            else:
                X_in_fresh = 0.0

            # Get current reactor biomass concentration (will be updated iteratively)
            if hasattr(self, 'X') and self.X > 0:
                X_reactor = self.X
            else:
                X_reactor = 1.0  # Initial guess for first iteration

            # Solve system of equations:
            # 1. Flow constraint: F + F_b = F_total_actual_per_unit
            # 2. TRADITIONAL Cell balance: μ×X×V + F_fresh×X_fresh = (1-η)×F×X + F_b×X
            F_fresh = F_total_actual_per_unit - (self.F_cake if hasattr(self, 'F_cake') else 0)
            inoculum_term = F_fresh * X_in_fresh / X_reactor if X_reactor > 0 else 0

            F_from_balance = (F_total_actual_per_unit - self.mu * self.V_max - inoculum_term) / self.eta
            F_b_from_balance = F_total_actual_per_unit - F_from_balance

            # Check if solution is physically feasible (both flows positive)
            if F_from_balance > 0 and F_b_from_balance > 0:
                self.F = F_from_balance
                self.F_b = F_b_from_balance

                # Calculate actual dilution rates
                self.D_actual = self.F / self.V_max
                self.D_b_actual = self.F_b / self.V_max

                # Recalculate X and X_max with correct D_actual
                self._calculate_cell_densities(self.D_actual)

                # Recalculate mass flows with correct X (final values for cell balance)
                self._update_mass_flows()
            else:
                # Infeasible solution - use design flows as fallback
                print(f"\n{self.ID} ERROR: Cell balance solution infeasible!")
                print(f"  F_balance = {F_from_balance:.1f} L/h (negative!)")
                print(f"  F_b_balance = {F_b_from_balance:.1f} L/h")
                print(f"  This indicates mu*V > F_total_actual - biologically impossible")

                self._use_design_flows()
        else:
            # Fallback to design flows
            self._use_design_flows()

    def _use_design_flows(self):
        """Use design dilution rates as fallback when flow solver fails."""
        self.F = self.D * self.V_max
        self.F_b = self.D_b * self.V_max
        self.D_actual = self.D
        self.D_b_actual = self.D_b

        # Recalculate X and X_max with design dilution rates
        self._calculate_cell_densities(self.D_actual)

        # Calculate mass flows with correct X
        self._update_mass_flows()

    def _check_feedstock_sufficiency(self, harvest_slurry):
        """Check if incoming stream has sufficient feedstock for all required components."""
        N = self.N
        warnings = []
        errors = []

        # Check H2 sufficiency
        H2_available_kg_h = harvest_slurry.imass[self.h2_id]  # kg/h
        H2_required_kg_h = (self.H2_consumed_final * N) / 1000.0  # g/h -> kg/h
        if H2_available_kg_h < H2_required_kg_h:
            deficit = H2_required_kg_h - H2_available_kg_h
            shortage_pct = (deficit / H2_required_kg_h) * 100
            if shortage_pct > 50:  # Error if more than 50% shortage
                errors.append(f"H2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")
            else:  # Warning for smaller shortages
                warnings.append(f"H2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")

        # Check O2 sufficiency
        O2_available_kg_h = harvest_slurry.imass[self.o2_id]  # kg/h
        O2_required_kg_h = (self.O2_consumed_final * N) / 1000.0  # g/h -> kg/h
        if O2_available_kg_h < O2_required_kg_h:
            deficit = O2_required_kg_h - O2_available_kg_h
            shortage_pct = (deficit / O2_required_kg_h) * 100
            if shortage_pct > 50:
                errors.append(f"O2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")
            else:
                warnings.append(f"O2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")

        # Check CO2 sufficiency
        CO2_available_kg_h = harvest_slurry.imass[self.co2_id]  # kg/h
        CO2_required_kg_h = (self.CO2_consumed_final * N) / 1000.0  # g/h -> kg/h
        if CO2_available_kg_h < CO2_required_kg_h:
            deficit = CO2_required_kg_h - CO2_available_kg_h
            shortage_pct = (deficit / CO2_required_kg_h) * 100
            if shortage_pct > 50:
                errors.append(f"CO2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")
            else:
                warnings.append(f"CO2 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")

        # Check nitrogen source sufficiency
        if self.nitrogen_source == 'ammonia':
            NH3_available_kg_h = harvest_slurry.imass[self.nh3_id]  # kg/h
            NH3_required_kg_h = (self.NH3_consumed_final * N) / 1000.0  # g/h -> kg/h
            if NH3_available_kg_h < NH3_required_kg_h:
                deficit = NH3_required_kg_h - NH3_available_kg_h
                shortage_pct = (deficit / NH3_required_kg_h) * 100
                if shortage_pct > 50:
                    errors.append(f"NH3 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")
                else:
                    warnings.append(f"NH3 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")

        elif self.nitrogen_source == 'ammonium_sulfate':
            NH3_mol = self.NH3_consumed_final / self.MW_NH3
            amS_required_kg_h = (NH3_mol * self.MW_AmmoniumSulfate / 2 * N) / 1000.0  # g/h -> kg/h
            amS_available_kg_h = harvest_slurry.imass[self.ammonium_sulfate_id]  # kg/h
            if amS_available_kg_h < amS_required_kg_h:
                deficit = amS_required_kg_h - amS_available_kg_h
                shortage_pct = (deficit / amS_required_kg_h) * 100
                if shortage_pct > 50:
                    errors.append(f"(NH4)2SO4 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")
                else:
                    warnings.append(f"(NH4)2SO4 shortage: {deficit:.3f} kg/h ({shortage_pct:.1f}% deficit)")

        # Issue warnings
        if warnings:
            print(f"\n{self.ID} FEEDSTOCK WARNINGS:")
            for warning in warnings:
                print(f"  WARNING: {warning}")

        # Issue errors (but don't raise exception - let max(0, ...) handle it)
        if errors:
            print(f"\n{self.ID} FEEDSTOCK ERRORS:")
            for error in errors:
                print(f"  ERROR: {error}")
            print(f"  Continuing with {len(errors)} component(s) at zero concentration in outlet.")

    def _setup_auxiliary_streams_for_costing(self):
        """Create isolated dummy streams for auxiliary unit costing calculations."""
        # Create completely isolated streams that are NOT part of the main flowsheet
        # These streams exist only for auxiliary unit internal sizing calculations

        # CSTR: Create isolated streams for sizing
        if hasattr(self, 'F_total') and self.F_total > 0:
            # Create isolated dummy streams (not connected to main flowsheet)
            dummy_cstr_in = bst.Stream(None)  # Anonymous stream
            # F_total is in L/h; water density ≈ 1 kg/L, so mass flow = F_total kg/h.
            # The earlier /1000 was a unit error (treated L/h as g/h) that caused
            # bst.CSTR to size a vessel 1000× too small.
            dummy_cstr_in.imass[self.water_id] = self.F_total  # L/h → kg/h (water, 1 L ≈ 1 kg)
            dummy_cstr_in.T = self.T_operating
            dummy_cstr_in.P = self.P_operating * 101325

            dummy_cstr_out = bst.Stream(None)  # Anonymous stream
            dummy_cstr_out.copy_like(dummy_cstr_in)

            # Assign to CSTR for internal sizing calculations only.
            # bst.CSTR._design() computes: V_total = ins_F_vol * tau / V_wf
            # and sets self.parallel['self'] = N = ceil(V_total / V_max).
            # V_max here must be the *total* vessel volume (working vol / V_wf) so that
            # N_internal = 1 (one vessel per parallel unit); the 499× multiplier is
            # applied externally via parent.parallel['cstr'].
            self.cstr.ins[:] = [dummy_cstr_in]
            self.cstr.outs[:] = [dummy_cstr_out]
            self.cstr.V_max = self.V_max / 1000.0 / self.cstr.V_wf  # working vol (L) → total vessel vol (m³)

        # Centrifuge: Create isolated streams with biomass loading
        if hasattr(self, 'F') and hasattr(self, 'X') and self.F > 0:
            biomass_flow_kg_h = max((self.F * self.X) / 1000, 0.1)  # Minimum for bounds

            dummy_cent_in = bst.Stream(None)  # Anonymous stream
            # F is in L/h; water density ≈ 1 kg/L, so mass flow = F kg/h (same /1000 bug as CSTR).
            dummy_cent_in.imass[self.water_id] = self.F  # L/h → kg/h (water, 1 L ≈ 1 kg)
            dummy_cent_in.imass[self.biomass_id] = biomass_flow_kg_h
            dummy_cent_in.T = self.T_operating
            dummy_cent_in.P = self.P_operating * 101325

            dummy_cent_cake = bst.Stream(None)
            dummy_cent_super = bst.Stream(None)
            dummy_cent_cake.imass[self.biomass_id] = biomass_flow_kg_h * 0.97
            dummy_cent_super.imass[self.water_id] = self.F / 1000.0

            # Assign for internal sizing only
            self.cell_separator.ins[:] = [dummy_cent_in]
            self.cell_separator.outs[:] = [dummy_cent_cake, dummy_cent_super]

    def _run(self):
        """Execute mass and energy balances for perfusion bioreactor."""
        # ── 0. Reset attributes (PRESERVED) ───────────────────────────────────
        for attr in ['Y_obs', 'q_s', 'D_b', 'D', 'F', 'F_b', 'S', 'X', 'X_max',
                     'CDW_produced', 'H2_consumed', 'CO2_consumed', 'O2_consumed',
                     'NH3_consumed', 'H2O_produced', 'Nutrients_consumed',
                     'cell_to_cake', 'cell_to_super1',
                     'cake_total_mass', 'water_in_cake', 'F_cake', 'F_super1',
                     'cell_bleed', 'F_harvest', 'cell_harvest', 'X_harvest']:
            if hasattr(self, attr):
                delattr(self, attr)

        # ── 1. Kinetic parameters (PRESERVED) ─────────────────────────────────
        self.Y_obs = 1.0 / (1.0/self.Y_max + self.m_s/self.mu)
        self.q_s = self.mu / self.Y_max + self.m_s

        # ── 2. Design dilution rates (PRESERVED) ──────────────────────────────
        self.D_b = self.bleed_fraction * self.mu
        self.D = (self.mu - self.D_b) / (1.0 - self.eta)
        if self.D <= 0:
            raise ValueError(f"Infeasible: D={self.D:.6f}. Check bleed_fraction and eta.")

        # ── 3. Update S_f from actual inlet (PRESERVED) ───────────────────────
        self._calculate_inlet_S_f()

        # ── 4. Residual substrate and initial X (PRESERVED) ───────────────────
        self.S = self.S_f * (1.0 - self.conversion)
        self._calculate_cell_densities(self.D)
        if self.X <= 0:
            raise ValueError(f"Infeasible: X={self.X:.6f}.")

        # ── 5. Initial mass flow estimates (PRESERVED) ─────────────────────────
        self._update_mass_flows()

        # ── 6. Parallel scaling (PRESERVED) ───────────────────────────────────
        combined_feed = self.ins[0]
        required_flow_rate = combined_feed.F_vol * 1000   # m³/h → L/h
        self._required_flow_rate = required_flow_rate
        self.F_max_per_unit = self.D * self.V_max          # L/h per unit
        if not hasattr(self, 'N') or self.N is None:
            self.N = self._calculate_parallel_scaling(required_flow_rate)

        # ── 7. Flow balance solver (PRESERVED from original) ─────────────────────
        # Must use same flow balance approach as original unit.py for identical results
        self._solve_flow_balance()

        # ── 8. Centrifuge split (PRESERVED) ───────────────────────────────────
        self.cell_to_cake = self.eta * self.F * self.X
        self.cell_to_super1 = (1.0 - self.eta) * self.F * self.X
        self.cake_total_mass = self.cell_to_cake / (1.0 - self.moisture)
        self.water_in_cake = self.cake_total_mass * self.moisture
        self.F_cake = self.cake_total_mass / 1000.0
        self.F_super1 = self.F - self.F_cake

        # ── 9. Bleed and harvest (PRESERVED) ──────────────────────────────────
        self.cell_bleed = self.F_b * self.X
        self.F_harvest = self.F_super1 + self.F_b
        self.cell_harvest = self.cell_to_super1 + self.cell_bleed
        self.X_harvest = self.cell_harvest / self.F_harvest

        # ── 10. F_total and F_in (PRESERVED) ──────────────────────────────────
        self.F_total = self.F + self.F_b          # reactor throughput (internal)
        self.F_in = self.F_total - self.F_cake  # fresh feed (external boundary)

        # ── 11. Mixed feed substrate concentration (PRESERVED) ────────────────
        self.S_f_fresh = self.S_f
        if self.F_in + self.F_cake > 1e-6:
            self.S_f_mixed = ((self.F_in * self.S_f_fresh + self.F_cake * self.S)
                              / (self.F_in + self.F_cake))
        else:
            self.S_f_mixed = self.S_f_fresh
        self.S_mixed = self.S_f_mixed * (1.0 - self.conversion)

        # ── 12. Final cell density and mass flows using S_f_mixed (PRESERVED) ──
        self.X_final = self.D_actual * (self.S_f_mixed - self.S_mixed) / self.q_s
        self.X_max_final = self.D_actual * self.S_f_mixed / self.q_s
        self.CDW_produced_final       = self.mu * self.X_final * self.V_max
        self.H2_consumed_final        = self.g_H2_per_gCDW        * self.CDW_produced_final
        self.CO2_consumed_final       = self.g_CO2_per_gCDW       * self.CDW_produced_final
        self.O2_consumed_final        = self.g_O2_per_gCDW        * self.CDW_produced_final
        self.NH3_consumed_final       = self.g_NH3_per_gCDW       * self.CDW_produced_final
        self.H2O_produced_final       = self.g_H2O_per_gCDW       * self.CDW_produced_final
        self.Nutrients_consumed_final = self.g_Nutrients_per_gCDW * self.CDW_produced_final
        H2_available = (self.F_in + self.F_cake) * self.S_f_mixed
        self.actual_conversion = (self.H2_consumed_final / H2_available
                                  if H2_available > 1e-6 else self.conversion)
        self.S_mixed = self.S_f_mixed * (1.0 - self.actual_conversion)

        # ── 13. Balance checks (PRESERVED — exact tolerances and inoculum term) ─
        inlet_stream = self.ins[0]
        F_total_actual_per_unit = self._required_flow_rate / self.N if self.N > 0 else 0
        X_in_fresh = (inlet_stream.imass[self.biomass_id] / inlet_stream.F_vol
                      if (self.biomass_id in inlet_stream.chemicals.IDs
                          and inlet_stream.F_vol > 0) else 0.0)
        F_in_fresh = F_total_actual_per_unit - (self.F_cake if hasattr(self, 'F_cake') else 0)
        incoming_biomass_external = F_in_fresh * X_in_fresh
        total_input = self.CDW_produced + incoming_biomass_external
        cell_loss = self.cell_to_super1 + self.cell_bleed
        tol = max(total_input, cell_loss) * 0.10   # 10% relative (relaxed for realistic inoculum testing)
        if abs(total_input - cell_loss) >= tol:
            raise RuntimeError(
                f"Cell balance failed: input={total_input:.6f} g/h, loss={cell_loss:.6f} g/h"
            )
        vol_check = self.F_super1 + self.F_cake
        if abs(self.F - vol_check) >= 1e-8:
            raise RuntimeError(f"Centrifuge volume balance failed")
        flow_error = abs(self.F_in - self.F_harvest) / max(self.F_in, 1e-6)
        if flow_error >= 1e-6:
            raise RuntimeError(f"Flow balance failed: F_in={self.F_in:.6f}, "
                               f"F_harvest={self.F_harvest:.6f} L/h")
        H2_in = self.F_in * self.S_f_fresh
        H2_out = self.F_harvest * self.S_mixed
        H2_check = self.H2_consumed_final + H2_out
        rel_err = abs(H2_in - H2_check) / max(H2_in, 1e-6)
        if rel_err >= 5e-3:
            raise RuntimeError(f"H₂ balance failed ({rel_err:.2%})")

        # ── 14. Configure auxiliary units for costing only [REVISED v2] ────────
        # Auxiliary units are used for proper BioSTEAM costing and sizing
        # The actual mass/energy balances are handled manually (preserved kinetics)

        # Set auxiliary unit sizes for costing
        self.cstr.tau = self.V_max / self.F_total if self.F_total > 0 else 1.0
        self.cstr.V_max = self.V_max / 1000.0 / self.cstr.V_wf  # working vol (L) → total vessel vol (m³)

        # Update bleed splitter split for sizing
        bleed_split = self.F / (self.F + self.F_b) if (self.F + self.F_b) > 0 else 0.8
        self.bleed_splitter.split = bleed_split

        # Centrifuge split already set during initialization

        # ── 15. Set outlet stream composition (PRESERVED approach) ─────────────
        harvest_slurry = self.outs[0]

        # copy_like first — preserves minerals, vitamins, all other components
        harvest_slurry.copy_like(combined_feed)
        harvest_slurry.T = self.T_operating
        harvest_slurry.P = self.P_operating * 101325

        # Force liquid phase (validated approach)
        try:
            total_mass = {cid: harvest_slurry.imass[cid]
                          for cid in harvest_slurry.chemicals.IDs
                          if harvest_slurry.imass[cid] > 0}
            harvest_slurry.empty()
            harvest_slurry.phase = 'l'
            for cid, mass in total_mass.items():
                harvest_slurry.imass[cid] = mass
        except Exception:
            harvest_slurry.phase = 'l'

        # Check feedstock sufficiency before modifying outlet composition
        self._check_feedstock_sufficiency(harvest_slurry)

        # Modify reaction-affected components only
        # ALL imass in kg/h — internal calcs in g/h, divide by 1000, scale by N
        N = self.N
        harvest_slurry.imass[self.h2_id] = max(0, harvest_slurry.imass[self.h2_id]
                                               - (self.H2_consumed_final * N) / 1000.0)
        harvest_slurry.imass[self.o2_id] = max(0, harvest_slurry.imass[self.o2_id]
                                               - (self.O2_consumed_final * N) / 1000.0)
        harvest_slurry.imass[self.co2_id] = max(0, harvest_slurry.imass[self.co2_id]
                                                - (self.CO2_consumed_final * N) / 1000.0)
        if self.nitrogen_source == 'ammonia':
            harvest_slurry.imass[self.nh3_id] = max(
                0, harvest_slurry.imass[self.nh3_id]
                - (self.NH3_consumed_final * N) / 1000.0)
        elif self.nitrogen_source == 'ammonium_sulfate':
            NH3_mol = self.NH3_consumed_final / self.MW_NH3
            amS_consumed = NH3_mol * self.MW_AmmoniumSulfate / 2
            so4_produced = NH3_mol * self.MW_Sulfate / 2
            harvest_slurry.imass[self.ammonium_sulfate_id] = max(
                0, harvest_slurry.imass[self.ammonium_sulfate_id]
                - (amS_consumed * N) / 1000.0)
            harvest_slurry.imass[self.sulfate_id] = (
                harvest_slurry.imass[self.sulfate_id]
                + (so4_produced * N) / 1000.0)
        harvest_slurry.imass[self.biomass_id] = (
            harvest_slurry.imass[self.biomass_id]
            + (self.CDW_produced_final * N) / 1000.0)
        harvest_slurry.imass[self.water_id] = (
            harvest_slurry.imass[self.water_id]
            + (self.H2O_produced_final * N) / 1000.0)
        harvest_slurry.imass[self.nutrients_id] = max(
            0, harvest_slurry.imass[self.nutrients_id]
            - (self.Nutrients_consumed_final * N) / 1000.0)

    def _design(self):
        """Populate design results and calculate utilities."""
        # Copy design_results exactly from validated unit.py
        self.design_results = {
            # Reactor sizing - PARALLEL SCALING
            'Number of parallel reactors': self.N,
            'Reactor volume per unit (L)': self.V_max,
            'Total reactor volume (L)': self.V_max * self.N,
            'Operating pressure (atm)': self.P_operating,
            'Operating temperature (K)': self.T_operating,

            # Perfusion operating point
            'Specific growth rate mu (h-1)': self.mu,
            'Dilution rate D (h-1)': self.D_actual if hasattr(self, 'D_actual') else self.D,
            'Bleed dilution rate Db (h-1)': self.D_b_actual if hasattr(self, 'D_b_actual') else self.D_b,
            'Max flow rate per unit (L/h)': self.F_max_per_unit,
            'Actual flow rate per unit (L/h)': self.F,
            'Total feed rate F_total (L/h)': self.F_total * self.N,
            'Perfusion flow rate F (L/h)': self.F,
            'Bleed flow rate Fb (L/h)': self.F_b,
            'Liquid residence time (h)': 1.0 / (self.D_actual if hasattr(self, 'D_actual') else self.D),
            'Cell residence time (h)': 1.0 / self.mu,

            # Biological state
            'Cell density X (g CDW/L)': self.X_final if hasattr(self, 'X_final') else self.X,
            'X_max feasibility limit (g/L)': self.X_max_final if hasattr(self, 'X_max_final') else self.X_max,
            'Residual substrate S (g H2/L)': self.S_mixed if hasattr(self, 'S_mixed') else self.S,
            'H2 conversion (%)': (self.actual_conversion if hasattr(self, 'actual_conversion') else self.conversion) * 100.0,
            'Observed yield Yobs (g/g)': self.Y_obs,
            'Specific uptake qs (g/g/h)': self.q_s,
            'Volumetric productivity (g/L/h)': self.mu * self.X,

            # Centrifuge 1
            'Centrifuge 1 feed flow (L/h)': self.F,
            'Centrifuge 1 cake flow (L/h)': self.F_cake,
            'Centrifuge 1 super flow (L/h)': self.F_super1,
            'Cell retention eta (%)': self.eta * 100.0,
            'Cake moisture (%)': self.moisture * 100.0,

            # Harvest stream
            'Harvest slurry flow (L/h)': self.F_harvest,
            'Harvest cell density (g/L)': self.X_harvest,

            # Stoichiometric consumption rates (g/h)
            'H2 consumed (g/h)': self.H2_consumed_final if hasattr(self, 'H2_consumed_final') else self.H2_consumed,
            'O2 consumed (g/h)': self.O2_consumed_final if hasattr(self, 'O2_consumed_final') else self.O2_consumed,
            'CO2 consumed (g/h)': self.CO2_consumed_final if hasattr(self, 'CO2_consumed_final') else self.CO2_consumed,
            'NH3 consumed (g/h)': self.NH3_consumed_final if hasattr(self, 'NH3_consumed_final') else self.NH3_consumed,
            'H2O produced (g/h)': self.H2O_produced_final if hasattr(self, 'H2O_produced_final') else self.H2O_produced,
            'Nutrients consumed (g/h)': self.Nutrients_consumed_final if hasattr(self, 'Nutrients_consumed_final') else self.Nutrients_consumed,
            'CDW produced (g/h)': self.CDW_produced_final if hasattr(self, 'CDW_produced_final') else self.CDW_produced,

            # Nitrogen source configuration
            'Nitrogen source': self.nitrogen_source,
        }

        # Add nitrogen source specific feed requirements
        if self.nitrogen_source == 'ammonium_sulfate':
            NH3_mol_per_hour = (self.NH3_consumed_final if hasattr(self, 'NH3_consumed_final') else self.NH3_consumed) / self.MW_NH3
            ammonium_sulfate_needed = NH3_mol_per_hour * self.MW_AmmoniumSulfate / 2
            sulfate_produced = NH3_mol_per_hour * self.MW_Sulfate / 2
            self.design_results['(NH4)2SO4 required (g/h)'] = ammonium_sulfate_needed
            self.design_results['SO4 produced (g/h)'] = sulfate_produced

        # Set parallelization factors for auxiliary units
        for name in ('feed_mixer', 'cstr', 'bleed_splitter', 'cell_separator', 'harvest_mixer'):
            self.parallel[name] = self.N

        # Create dummy streams for auxiliary unit sizing (they need streams to calculate costs)
        self._setup_auxiliary_streams_for_costing()

        # Design auxiliary units for costing
        for aux_unit in self.auxiliary_units:
            try:
                aux_unit._design()
                aux_unit._cost()
            except Exception as e:
                print(f"Warning: {aux_unit.ID} costing failed: {e}")
                # Continue anyway - some units may not have all required parameters for costing

        # bst.CSTR._design() sets cstr.parallel['self'] = N_internal via ceil(V_total/V_max).
        # V_total can exceed V_max by a tiny margin (water density at 293 K is ~998 kg/m³,
        # not 1000) causing ceil to return 2 instead of 1. Each PerfusionBioreactor
        # parallel unit has exactly one CSTR vessel; the N-way replication is handled
        # entirely by parent.parallel['cstr'] = self.N set below.
        self.cstr.parallel['self'] = 1

        # Register metabolic heat utility (CSTR handles agitation power)
        H2_consumed_for_heat = self.H2_consumed_final if hasattr(self, 'H2_consumed_final') else self.H2_consumed
        metabolic_heat_duty = (H2_consumed_for_heat / self.MW_H2) * 121.0  # kJ/h
        self.add_heat_utility(-metabolic_heat_duty, T_in=self.T_operating)

        # Exclude heat utilities from HXN optimization
        for unit in self.auxiliary_units:
            for hu in unit.heat_utilities:
                hu.hxn_ok = False

    def _cost(self):
        """Calculate equipment costs - all costs come from sub-units."""
        pass

    def __repr__(self):
        """Return one-line summary of perfusion bioreactor."""
        if hasattr(self, 'X') and hasattr(self, 'CDW_produced'):
            return (f"PerfusionBioreactor: V={self.V_max} L, mu={self.mu} h-1, "
                   f"X={self.X:.4f} g/L, P={self.CDW_produced:.4f} g CDW/h")
        else:
            return f"PerfusionBioreactor: V={self.V_max} L, mu={self.mu} h-1 (not simulated)"