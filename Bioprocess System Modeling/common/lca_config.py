"""LCA Inventory Assessment configuration — NAICS allocation, elementary flows,
and per-route Operational Flow row specifications.

This module is the single source of truth for *what to compute* in each LCA
inventory row.  The interpreter (common/lca_export.py) reads these structures
and computes values directly from BioSTEAM stream/unit objects — no hardcoded
numbers, no external links.

Framework §8 / Plan: lca/LCA_Automation_Plan.md.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 1. NAICS categories — six rows in the Capital Goods sheet
# ---------------------------------------------------------------------------

NAICS_CATEGORIES: list[tuple[str, str]] = [
    ("Heavy Gauge Metal Tanks",                "3324"),  # index 0
    ("Power Boilers and Heat Exchangers",       "3324"),  # index 1
    ("Pumps and Pumping Equipment",             "3339"),  # index 2
    ("Air and Gas Compressors",                "3339"),  # index 3
    ("Welding/Soldering/General Machinery",    "3339"),  # index 4
    ("Air Conditioning/Refrigeration/Heating", "3334"),  # index 5
]


# ---------------------------------------------------------------------------
# 2. LCA inventory dollar-year basis
# ---------------------------------------------------------------------------

_CEPCI_LCA_BASE: float = 584.6
# 2012 CEPCI — matches the dollar year of the hand-built LCA inventory workbooks.
# Runtime deflation factor: _CEPCI_LCA_BASE / economics.CEPCI
# (economics.CEPCI = 809.3 for the 2025 project dollar year — Framework §9.4)


# ---------------------------------------------------------------------------
# 3. Purchase-cost key → NAICS row index
#
# Populated from stream inspection (lca/stream_inspection.py) run against
# the simulated fructose and gas_fermentation systems.  Any unmapped key
# raises KeyError at runtime, forcing this dict to stay current whenever
# BioSTEAM adds cost items.
# ---------------------------------------------------------------------------

COST_KEY_TO_NAICS_ROW: dict[str, int] = {
    # --- 0  Heavy Gauge Metal Tanks (3324) ---
    'Tank':                            0,   # bst.StorageTank, bst.MixTank
    'Vertical pressure vessel':        0,   # ExtentBasedBioreactor, SeedBioreactor, DropletColumn
    'Platform and ladders':            0,   # ExtentBasedBioreactor, SeedBioreactor, DropletColumn
    'Cstr - Vertical pressure vessel': 0,   # PerfusionBioreactor CSTR sub-unit (gas ferm R101)
    'Cstr - Platform and ladders':     0,   # PerfusionBioreactor CSTR sub-unit (gas ferm R101)

    # --- 1  Power Boilers and Heat Exchangers (3324) ---
    'Floating head':                   1,   # bst.HXutility (production heater/aftercooler)
    'Double pipe':                     1,   # bst.HXutility (seed heater/cooler)
    'Heat exchanger - Floating head':  1,   # ExtentBasedBioreactor / SeedBioreactor (large stages)
    'Heat exchanger - Double pipe':    1,   # SeedBioreactor (small stages)

    # --- 2  Pumps and Pumping Equipment (3339) ---
    'Pump':                            2,   # bst.Pump P101 (gas ferm pressurisation)
    'Motor':                           2,   # bst.Pump motor
    'Recirculation pump - Pump':       2,   # ExtentBasedBioreactor / SeedBioreactor recirculation
    'Recirculation pump - Motor':      2,   # ExtentBasedBioreactor / SeedBioreactor recirculation motor

    # --- 3  Air and Gas Compressors (3339) ---
    'Compressor(s)':                   3,   # bst.IsentropicCompressor CP101/CP102 (gas ferm)
    'Compressor - Compressor(s)':      3,   # ExtentBasedBioreactor / SeedBioreactor aeration compressor

    # --- 4  Welding/Soldering/General Machinery (3339) ---
    'Agitator - Agitator':             4,   # ExtentBasedBioreactor / SeedBioreactor agitator
    'Cstr - Agitator - Agitator':      4,   # PerfusionBioreactor CSTR agitator sub-unit (gas ferm R101)
    'Centrifuges':                     4,   # bst.SolidsCentrifuge C101
    'Cell separator - Centrifuges':    4,   # PerfusionBioreactor internal centrifuge (gas ferm R101)
    'Spray dryer':                     4,   # bst.SprayDryer D101
    'UF membrane system':              4,   # UltrafiltrationSterilizer UF101 (gas ferm only)

    # --- 5  Air Conditioning/Refrigeration/Heating (3334) ---
    'Air cooler - Floating head':      5,   # ExtentBasedBioreactor air cooler (liquid routes R101)
    'Air cooler - Double pipe':        5,   # SeedBioreactor air cooler (gas ferm SR102/SR103)
    # Note: 'Air cooler - Double pipe' confirmed from stream inspection of gas_fermentation
    # model (SR102 and SR103 in gas ferm are large enough to require an air cooler).
}


# ---------------------------------------------------------------------------
# 4. Elementary flow strings — verbatim from existing inventory workbooks
# ---------------------------------------------------------------------------

ELEMENTARY_FLOWS: dict[str, str] = {
    'Fructose':              'Fructose proxy flow',
    'Acetic Acid':           'Acetic Acid Proxy Flow',
    'Formic Acid':           'Formic Acid Proxy Flow',
    'H2':                    'Hydrogen Proxy Flow',
    'CO2_in':                'Biogenic CO2 emission to air, unspecified',
    'O2_in':                 'Oxygen, emission, air',
    'Nutrients':             'Other basic Inorganic Chemicals (3251)',
    'NH3_in':                'Ammonia, SMR Liquid at plant (3253)',
    'Electricity':           'Relevant mix for SA',
    'Water':                 'Water, (elementary)',
    'Steam':                 'Natural gas combustion / steam injection at turbine',
    'Chilled Water':         'Water, Process + cooling (elementary)',
    'WWT':                   'Drinking water/wastewater treatment US (2213)',
    'O2_air_in':             'Resource, air',
    'N2_air_in':             'Resource, air',
    'Water_effluent':        'Water, (elementary)',
    'NH3_water':             'Ammonia, emission to water, freshwater',
    'KH2PO4_water':          'Monopotassium phosphate, emissions, water',
    'AmmoniumSulfate_water':  'Ammonium Sulfate, emissions, water',
    'NaHCO3_water':          'Sodium Bicarbonate, emissions, water',
    'FerricAmmoniumCitrate_water': 'Waste, inorganic',
    'Substrate_water':       'Waste, organic',
    'MgSO4_7H2O_water':      'Waste, inorganic',
    'Biomass_water':         'waste, organic',
    'Na2HPO4_2H2O_water':    'Waste, inorganic',
    'TraceMetals_water':     'Metal waste',
    'N2_air':                'Nitrogen, emission, air',
    'O2_air':                'Oxygen, emission, air',
    'CO2_air':               'carbon dioxide, emission, air',
    'NH3_air':               'ammonia, emission, air',
    'H2O_air':               'water, emission, air',
    'Substrate_air':         'air emission, organic',
    'H2_water':              'Hydrogen, dissolved, emission to water',
    'O2_water':              'Oxygen, dissolved, emission to water',
    'CO2_water':             'Carbon dioxide, dissolved, emission to water',
}


# ---------------------------------------------------------------------------
# 5. OP_FLOW_SPECS — explicit per-route, per-row operational flow designation
#
# Each row spec is a dict with:
#   section  : 'ins' or 'outs'
#   material : Col A display label
#   ef_key   : Key into ELEMENTARY_FLOWS for Col C
#   units    : Col D unit string
#   scope    : List of unit/stream IDs contributing to this row (written to Col B)
#   accessor : Tuple (type, *args) describing how to read the value from BioSTEAM
#
# Accessor types and what they return (before unit conversion):
#   ('feed_stream', stream_id, component)
#       → stream.imass[component], kg/hr
#   ('unit_in_sum', [(unit_id, in_idx, component), ...])
#       → sum of unit.ins[in_idx].imass[component], kg/hr
#   ('cost_sum', [(unit_id, in_idx, component), ...], price_or_sentinel)
#       → sum(mass × price), $/hr current-year  [× cepci_ratio in export → 2012 $/hr]
#       price sentinel '<composite_price>' is substituted at export time.
#   ('power_sum', [unit_id, ...])
#       → sum(unit.power_utility.consumption), kW  [÷ 1000 → MWh/hr in export]
#   ('h2o_feed_sum', [stream_id, ...])
#       → sum(stream.imass['H2O']), kg/hr  [÷ 1000 → m³/hr in export]
#   ('utility_sum', [unit_id, ...], agent_id)
#       → sum(hu.flow for matching agent), kmol/hr
#       [× 18.015 → kg/hr for steam; × 18.015/1000 → m³/hr for chilled water]
#       agent_id is matched case-insensitively with spaces→underscores.
#   ('air_sum', [unit_id, ...], component)
#       → sum(unit.air.imass[component]), kg/hr
#       Units without .air attribute (e.g. PerfusionBioreactor) are skipped.
#   ('wwt_cost', wwt_unit_id)
#       → non-H2O flow in unit.ins[0] × economics.wwt_organic_removal_cost, $/hr
#       [× cepci_ratio in export → 2012 $/hr]
#   ('discharge', component)
#       → RCY101.outs[1].imass[component], kg/hr
#       [÷ 1000 → m³/hr when units='m3']
#   ('gas_out_sum', [unit_id, ...], component)
#       → sum(unit.outs[0].imass[component]), kg/hr
#       outs[0] is the gas vent for AeratedBioreactor subclasses.
#   ('dryer_vapor', component)
#       → D101.outs[0].imass[component], kg/hr
#   ('unit_out_sum', [(unit_id, out_idx), ...], component)
#       → sum(unit.outs[idx].imass[component]), kg/hr
#       Combines multiple liquid outlets (e.g. RCY101.outs[1] + WWT102.outs[1]) into
#       a single row, eliminating separate discharge vs. sludge rows.
#   ('multi_out_unlump', [(unit_id, out_idx), ...], nutrient_key)
#       → sum(unit.outs[idx].imass['Nutrients']) × nmf[nutrient_key], kg/hr
#       Unlumps Nutrients from multiple outlets combined; replaces separate
#       discharge_unlump + unit_out_unlump rows with a single combined row.
#
#   The following accessor types remain valid in lca_export.py but are no longer
#   used in any OP_FLOW_SPECS entry (superseded by unit_out_sum / multi_out_unlump):
#   ('discharge_unlump', nutrient_key)
#       → RCY101.outs[1].imass['Nutrients'] × nmf[nutrient_key], kg/hr
#   ('unit_out', unit_id, out_idx, component)
#       → unit_map[unit_id].outs[out_idx].imass[component], kg/hr
#   ('unit_out_unlump', unit_id, out_idx, nutrient_key)
#       → unit_map[unit_id].outs[out_idx].imass['Nutrients'] × nmf[nutrient_key], kg/hr
#
# Confirmed from stream inspection (2026-08-12):
#   - BioSTEAM agent IDs: 'low_pressure_steam', 'chilled_water'
#   - ExtentBasedBioreactor R101 outs[0] = gas (phase='g'), outs[1] = liquid
#   - PerfusionBioreactor R101 outs[0] = liquid harvest slurry (no gas vent)
#   - D101.outs[0] = evaporated water vapor (H2O only)
#   - RCY101.outs[1] = discharge (H2O, substrate residual, biomass, nutrients trace)
#   - SR101.air.F_mass ≈ 0 for fructose route (tiny seed volume);
#     SR102/SR103.air nonzero for gas ferm (larger seed volumes at that scale)
#   - 'Air cooler - Double pipe' observed on gas ferm SR102/SR103 (added to NAICS map)
# ---------------------------------------------------------------------------


def _liquid_route_specs(
    substrate_stream_id: str,
    substrate_component: str,
    substrate_ef_key: str,
) -> list[dict]:
    """Return OP_FLOW_SPECS rows for one liquid-substrate route.

    Called three times (fructose, acetate, formate) with only the substrate
    identifiers differing.  All other unit IDs and accessor args are identical
    across the three routes — Framework §10 (shared flowsheet topology).
    """
    # Aerated units contributing to air supply (production + all seed stages).
    # SR101.air ≈ 0 for liquid routes (tiny volume) but included for completeness
    # and to keep scope consistent with gas ferm treatment.  Framework §hard-rules:
    # explicit per-row designation, not implicit scoping.
    _aerated = ['R101', 'SR101', 'SR102', 'SR103']

    return [
        # ===== INPUTS =====
        {
            'section': 'ins',
            'material': substrate_component,
            'ef_key':   substrate_ef_key,
            'units':    'kg',
            'scope':    ['ST101', 'ST201'],
            'accessor': ('unit_in_sum', [('ST101', 0, substrate_component),
                                         ('ST201', 0, substrate_component)]),
            # ST101: production substrate storage inlet (main feed).
            # ST201: seed substrate storage inlet — same chemical, separate feed stream.
        },
        {
            'section': 'ins',
            'material': 'Nutrients (salts)',
            'ef_key':   'Nutrients',
            'units':    '2012 USD',
            'scope':    ['ST102', 'ST202'],
            'accessor': ('cost_sum',
                         [('ST102', 0, 'Nutrients'), ('ST202', 0, 'Nutrients')],
                         '<composite_price>'),
            # price sentinel is substituted at export time with the runtime composite
            # $/kg computed from NUTRIENTS_RECIPE by build_nutrients_properties().
        },
        {
            'section': 'ins',
            'material': 'NH3',
            'ef_key':   'NH3_in',
            'units':    'kg',
            'scope':    ['ST103', 'ST203'],
            'accessor': ('unit_in_sum', [('ST103', 0, 'NH3'), ('ST203', 0, 'NH3')]),
            # ST103: production NH3 storage inlet. ST203: seed train NH3 storage inlet.
        },
        {
            'section': 'ins',
            'material': 'Electricity',
            'ef_key':   'Electricity',
            'units':    'MWh',
            'scope':    ['M101', 'R101', 'C101', 'SM101', 'SR101', 'SR102', 'SR103'],
            'accessor': ('power_sum',
                         ['M101', 'R101', 'C101', 'SM101', 'SR101', 'SR102', 'SR103']),
        },
        {
            'section': 'ins',
            'material': 'Water',
            'ef_key':   'Water',
            'units':    'm3',
            'scope':    ['water_feed', 'seed_water_feed'],
            'accessor': ('h2o_feed_sum', ['water_feed', 'seed_water_feed']),
        },
        {
            'section': 'ins',
            'material': 'Low Pressure Steam',
            'ef_key':   'Steam',
            'units':    'kg',
            'scope':    ['HX101', 'SHX101'],
            'accessor': ('utility_sum', ['HX101', 'SHX101'], 'low_pressure_steam'),
            # HX101: production media heater to 134 °C (Framework §9.2)
            # SHX101: seed media heater to 134 °C (Framework §6)
            # HX102 uses chilled_water (30 °C target < cooling_water T_supply).
        },
        {
            'section': 'ins',
            'material': 'Chilled Water',
            'ef_key':   'Chilled Water',
            'units':    'm3',
            'scope':    ['HX102', 'R101', 'SHX102', 'SR101', 'SR102', 'SR103'],
            'accessor': ('utility_sum',
                         ['HX102', 'R101', 'SHX102', 'SR101', 'SR102', 'SR103'],
                         'chilled_water'),
            # 30 °C fermentation target < cooling water supply (32.2 °C) →
            # BioSTEAM selects chilled_water for all coolers and bioreactors.
        },
        {
            'section': 'ins',
            'material': 'Waste Water Treatment',
            'ef_key':   'WWT',
            'units':    '2012 USD',
            'scope':    ['WWT102'],
            'accessor': ('wwt_cost', 'WWT102'),
        },
        {
            'section': 'ins',
            'material': 'O2 (from air)',
            'ef_key':   'O2_air_in',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('air_sum', _aerated, 'O2'),
        },
        {
            'section': 'ins',
            'material': 'N2 (from air)',
            'ef_key':   'N2_air_in',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('air_sum', _aerated, 'N2'),
        },

        # ===== OUTPUTS =====
        # One row per component per phase — discharge (RCY101.outs[1]) and WWT sludge
        # (WWT102.outs[1]) are combined into a single "liquid effluent" row per component.
        # Water effluent sums BOTH outlets: RCY101.outs[1] (treated discharge) and
        # WWT102.outs[1] (sludge cake — 80% moisture per WWT_SLUDGE_MOISTURE; the
        # _SludgeSettler routes H2O to sludge to meet this moisture target).
        {
            'section': 'outs',
            'material': 'Water effluent',
            'ef_key':   'Water_effluent',
            'units':    'm3',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'H2O'),
        },
        {
            'section': 'outs',
            'material': 'NH3 (liquid effluent)',
            'ef_key':   'NH3_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'NH3'),
            # Combines RCY101.outs[1] (discharge) + WWT102.outs[1] (sludge).
        },
        *_effluent_nutrient_rows(),
        {
            'section': 'outs',
            'material': f'{substrate_component} (liquid effluent)',
            'ef_key':   'Substrate_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], substrate_component),
        },
        {
            'section': 'outs',
            'material': 'Biomass (liquid effluent)',
            'ef_key':   'Biomass_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'CNecatorBiomass'),
        },
        {
            'section': 'outs',
            'material': 'CO2 (liquid effluent)',
            'ef_key':   'CO2_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'CO2'),
            # Non-zero for acetate route (~0.32 kg/hr dissolved CO2 in WWT sludge);
            # ~0 for fructose/formate.  unit_out_sum is correct for both.
        },
        {
            'section': 'outs',
            'material': 'N2 (air emissions)',
            'ef_key':   'N2_air',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('gas_out_sum', _aerated, 'N2'),
            # outs[0] of ExtentBasedBioreactor / SeedBioreactor is the gas vent.
        },
        {
            'section': 'outs',
            'material': 'CO2 (air emissions)',
            'ef_key':   'CO2_air',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('gas_out_sum', _aerated, 'CO2'),
        },
        {
            'section': 'outs',
            'material': 'O2 (air emissions)',
            'ef_key':   'O2_air',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('gas_out_sum', _aerated, 'O2'),
        },
        {
            'section': 'outs',
            'material': 'NH3 (air emissions)',
            'ef_key':   'NH3_air',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('gas_out_sum', _aerated, 'NH3'),
        },
        {
            'section': 'outs',
            'material': 'H2O (air emissions)',
            'ef_key':   'H2O_air',
            'units':    'kg',
            'scope':    _aerated + ['D101'],
            'accessor': ('gas_out_sum', _aerated + ['D101'], 'H2O'),
            # Combines bioreactor vents (R101, SR101-SR103) with spray dryer vapor
            # (D101.outs[0] = evaporated water) into a single air emission row.
        },
        {
            'section': 'outs',
            'material': f'{substrate_component} (air emissions)',
            'ef_key':   'Substrate_air',
            'units':    'kg',
            'scope':    _aerated,
            'accessor': ('gas_out_sum', _aerated, substrate_component),
        },
    ]


# Gas fermentation seed stages that supply aeration air to seed bioreactors.
# SR101.air ≈ 0 for gas ferm (negligible volume at N=1) but included for
# consistency.  SR102/SR103 have nonzero air (confirmed from stream inspection).
_GF_SEED = ['SR101', 'SR102', 'SR103']

# Combined liquid-effluent nutrient rows — sums RCY101.outs[1] (discharge) and
# WWT102.outs[1] (sludge) into a single row per salt, eliminating duplicate rows.
# multi_out_unlump: sums Nutrients across both outlets then unlumps via mass fraction.
_NUTRIENT_EFFLUENT_ROWS: list[dict] = [
    {'material': 'KH2PO4 (liquid effluent)',
     'ef_key': 'KH2PO4_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'KH2PO4')},
    {'material': '(NH4)2SO4 (liquid effluent)',
     'ef_key': 'AmmoniumSulfate_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'AmmoniumSulfate')},
    {'material': 'NaHCO3 (liquid effluent)',
     'ef_key': 'NaHCO3_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'NaHCO3')},
    {'material': 'Ferric Ammonium Citrate (liquid effluent)',
     'ef_key': 'FerricAmmoniumCitrate_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'FerricAmmoniumCitrate')},
    {'material': 'MgSO4.7H2O (liquid effluent)',
     'ef_key': 'MgSO4_7H2O_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'MgSO4.7H2O')},
    {'material': 'Na2HPO4.2H2O (liquid effluent)',
     'ef_key': 'Na2HPO4_2H2O_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'Na2HPO4.2H2O')},
    {'material': 'Trace Metals (liquid effluent)',
     'ef_key': 'TraceMetals_water',
     'accessor': ('multi_out_unlump', [('RCY101', 1), ('WWT102', 1)], 'TraceMetals')},
]


def _effluent_nutrient_rows() -> list[dict]:
    """Combined discharge + WWT sludge nutrient rows, all routes.

    Returns seven rows (one per nutrient salt) using multi_out_unlump to sum
    RCY101.outs[1] and WWT102.outs[1] before unlumping.  Feed-side Nutrients
    remain as a single lumped cost row (2012 USD) — user decision 2026-08-12.
    """
    return [
        {**row, 'section': 'outs', 'units': 'kg', 'scope': ['RCY101', 'WWT102']}
        for row in _NUTRIENT_EFFLUENT_ROWS
    ]


OP_FLOW_SPECS: dict[str, list[dict]] = {
    # -----------------------------------------------------------------------
    # Liquid-substrate routes — identical flowsheet topology, substrate differs
    # -----------------------------------------------------------------------
    'fructose': _liquid_route_specs('fructose_feed', 'Fructose',  'Fructose'),
    'acetate':  _liquid_route_specs('acetate_feed',  'AceticAcid', 'Acetic Acid'),
    'formate':  _liquid_route_specs('formate_feed',  'FormicAcid', 'Formic Acid'),

    # -----------------------------------------------------------------------
    # Gas fermentation — different topology (Framework §4a):
    #   • H2/CO2/O2 feedstocks replace single liquid substrate
    #   • UF membrane sterilization (UF101) replaces HX101/HX102 heat sterilization
    #   • HX101/HX102 are gas aftercoolers (chilled water, not steam)
    #   • SHX101 still uses steam (seed media sterilization unchanged)
    #   • PerfusionBioreactor R101 has no gas vent (closed pressurized vessel)
    #   • Aeration air in R101 is absent; seed SR102/SR103 supply aeration air
    #   • CP101/CP102 (gas compressors), P101 (pump) add electricity
    #   • No ST101 (gas H2/O2/CO2 feeds have no liquid storage tank)
    # -----------------------------------------------------------------------
    'gas_fermentation': [
        # ===== INPUTS =====
        {
            'section': 'ins',
            'material': 'H2',
            'ef_key':   'H2',
            'units':    'kg',
            'scope':    ['h2_feed'],
            'accessor': ('feed_stream', 'h2_feed', 'H2'),
        },
        {
            'section': 'ins',
            'material': 'CO2 (feed)',
            'ef_key':   'CO2_in',
            'units':    'kg',
            'scope':    ['co2_o2_feed'],
            'accessor': ('feed_stream', 'co2_o2_feed', 'CO2'),
        },
        {
            'section': 'ins',
            'material': 'O2 (feed)',
            'ef_key':   'O2_in',
            'units':    'kg',
            'scope':    ['co2_o2_feed'],
            'accessor': ('feed_stream', 'co2_o2_feed', 'O2'),
        },
        {
            'section': 'ins',
            'material': 'Fructose (seed train)',
            'ef_key':   'Fructose',
            'units':    'kg',
            'scope':    ['ST201'],
            'accessor': ('unit_in_sum', [('ST201', 0, 'Fructose')]),
            # Seed train grown heterotrophically on fructose (user decision 2026-08-07).
            # ST201 is the seed substrate storage tank; its inlet is seed_substrate_feed.
            # ~158 kg/hr at 25,000 MT/yr scale (large seed train for ~492 production vessels).
        },
        {
            'section': 'ins',
            'material': 'Nutrients (salts)',
            'ef_key':   'Nutrients',
            'units':    '2012 USD',
            'scope':    ['ST102', 'ST202'],
            'accessor': ('cost_sum',
                         [('ST102', 0, 'Nutrients'), ('ST202', 0, 'Nutrients')],
                         '<composite_price>'),
        },
        {
            'section': 'ins',
            'material': 'NH3',
            'ef_key':   'NH3_in',
            'units':    'kg',
            'scope':    ['ST103', 'ST203'],
            'accessor': ('unit_in_sum', [('ST103', 0, 'NH3'), ('ST203', 0, 'NH3')]),
            # ST103: production NH3 storage inlet. ST203: seed train NH3 storage inlet.
        },
        {
            'section': 'ins',
            'material': 'Electricity',
            'ef_key':   'Electricity',
            'units':    'MWh',
            'scope':    ['CP101', 'CP102', 'P101', 'R101', 'C101',
                         'SM101', 'SR101', 'SR102', 'SR103'],
            'accessor': ('power_sum',
                         ['CP101', 'CP102', 'P101', 'R101', 'C101',
                          'SM101', 'SR101', 'SR102', 'SR103']),
            # UF101, DC101, DC102, MX101, SP101 all have power = 0 (confirmed from
            # stream inspection) and are excluded for cleanliness of scope list.
        },
        {
            'section': 'ins',
            'material': 'Water',
            'ef_key':   'Water',
            'units':    'm3',
            'scope':    ['water_feed', 'seed_water_feed'],
            'accessor': ('h2o_feed_sum', ['water_feed', 'seed_water_feed']),
        },
        {
            'section': 'ins',
            'material': 'Low Pressure Steam (seed only)',
            'ef_key':   'Steam',
            'units':    'kg',
            'scope':    ['SHX101'],
            'accessor': ('utility_sum', ['SHX101'], 'low_pressure_steam'),
            # Gas ferm production media sterilised by UF101 (no steam).
            # SHX101 (seed media heater) still uses steam — Framework §6.
            # HX101/HX102 are gas aftercoolers (chilled water, not steam).
        },
        {
            'section': 'ins',
            'material': 'Chilled Water',
            'ef_key':   'Chilled Water',
            'units':    'm3',
            'scope':    ['HX101', 'HX102', 'R101', 'SHX102',
                         'SR101', 'SR102', 'SR103'],
            'accessor': ('utility_sum',
                         ['HX101', 'HX102', 'R101', 'SHX102',
                          'SR101', 'SR102', 'SR103'],
                         'chilled_water'),
            # HX101/HX102: gas aftercoolers (~250 °C / ~200 °C → 30 °C, Framework §4a)
            # R101 (PerfusionBioreactor): metabolic heat removal at 30 °C
            # SHX102: seed media cooler
        },
        {
            'section': 'ins',
            'material': 'Waste Water Treatment',
            'ef_key':   'WWT',
            'units':    '2012 USD',
            'scope':    ['WWT102'],
            'accessor': ('wwt_cost', 'WWT102'),
        },
        {
            'section': 'ins',
            'material': 'O2 (from air, seed)',
            'ef_key':   'O2_air_in',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('air_sum', _GF_SEED, 'O2'),
            # R101 (PerfusionBioreactor) has no .air attribute (no direct air supply;
            # O2 dissolved via DC102).  Seed bioreactors SR102/SR103 aerobically
            # grow fructose-heterotrophic culture and do consume air.
        },
        {
            'section': 'ins',
            'material': 'N2 (from air, seed)',
            'ef_key':   'N2_air_in',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('air_sum', _GF_SEED, 'N2'),
        },

        # ===== OUTPUTS =====
        # One row per component per phase — discharge (RCY101.outs[1]) and WWT sludge
        # (WWT102.outs[1]) are combined into a single "liquid effluent" row per component.
        # Water effluent sums BOTH outlets: RCY101.outs[1] (treated discharge) and
        # WWT102.outs[1] (sludge cake — 80% moisture per WWT_SLUDGE_MOISTURE; the
        # _SludgeSettler routes H2O to sludge to meet this moisture target).
        {
            'section': 'outs',
            'material': 'Water effluent',
            'ef_key':   'Water_effluent',
            'units':    'm3',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'H2O'),
        },
        {
            'section': 'outs',
            'material': 'NH3 (liquid effluent)',
            'ef_key':   'NH3_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'NH3'),
        },
        *_effluent_nutrient_rows(),
        {
            'section': 'outs',
            'material': 'Fructose (liquid effluent, seed train)',
            'ef_key':   'Substrate_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'Fructose'),
            # Seed train grown heterotrophically on fructose (user decision 2026-08-07).
            # Residual fructose from seed effluent appears in both discharge and sludge.
        },
        {
            'section': 'outs',
            'material': 'Biomass (liquid effluent)',
            'ef_key':   'Biomass_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'CNecatorBiomass'),
        },
        {
            'section': 'outs',
            'material': 'H2 (liquid effluent)',
            'ef_key':   'H2_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'H2'),
            # Dissolved H2 carried through to both discharge and WWT sludge streams.
        },
        {
            'section': 'outs',
            'material': 'O2 (liquid effluent)',
            'ef_key':   'O2_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'O2'),
        },
        {
            'section': 'outs',
            'material': 'CO2 (liquid effluent)',
            'ef_key':   'CO2_water',
            'units':    'kg',
            'scope':    ['RCY101', 'WWT102'],
            'accessor': ('unit_out_sum', [('RCY101', 1), ('WWT102', 1)], 'CO2'),
        },
        {
            'section': 'outs',
            'material': 'H2O (air emissions)',
            'ef_key':   'H2O_air',
            'units':    'kg',
            'scope':    _GF_SEED + ['D101'],
            'accessor': ('gas_out_sum', _GF_SEED + ['D101'], 'H2O'),
            # Combines seed bioreactor vents (SR101-SR103) with spray dryer vapor
            # (D101.outs[0]).  R101 (PerfusionBioreactor) has no gas vent.
        },
        {
            'section': 'outs',
            'material': 'N2 (air, seed vents)',
            'ef_key':   'N2_air',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('gas_out_sum', _GF_SEED, 'N2'),
            # outs[0] of SeedBioreactor (AeratedBioreactor subclass) is the gas vent.
            # R101 (PerfusionBioreactor) has no gas vent — pressurised closed vessel.
        },
        {
            'section': 'outs',
            'material': 'CO2 (air, seed vents)',
            'ef_key':   'CO2_air',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('gas_out_sum', _GF_SEED, 'CO2'),
        },
        {
            'section': 'outs',
            'material': 'O2 (air, seed vents)',
            'ef_key':   'O2_air',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('gas_out_sum', _GF_SEED, 'O2'),
        },
        {
            'section': 'outs',
            'material': 'NH3 (air, seed vents)',
            'ef_key':   'NH3_air',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('gas_out_sum', _GF_SEED, 'NH3'),
        },
        {
            'section': 'outs',
            'material': 'Fructose (air, seed vents)',
            'ef_key':   'Substrate_air',
            'units':    'kg',
            'scope':    _GF_SEED,
            'accessor': ('gas_out_sum', _GF_SEED, 'Fructose'),
        },
    ],
}
