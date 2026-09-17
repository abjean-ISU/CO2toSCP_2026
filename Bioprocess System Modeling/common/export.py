"""Shared export for all four SCP routes — 9-sheet workbook.

Public functions
----------------
export_results      — writes outputs/{route}_results.xlsx with nine sheets:
    'Executive Summary' — MSP, production metrics, capital and operating cost totals.
    'All Streams'       — flat table, one row per named stream; paired kg/h and
                          kg/kg SCP chemical columns; Nutrients unlumped to individual
                          salt rows.
    'Equipment'         — ID, type, N, material, purchase cost, BM factor, installed
                          cost, heat duty, power, plus all design_results keys.
    'Mass Balance'      — component-level Input / Output / Balance / Closure.
    'TEA Parameters'    — all EconomicBasis fields used in the analysis.
    'Capital Costs'     — FCI, working capital, TCI.
    'Operating Costs'   — FOC block (startrow=0) then 3 blank rows then VOC block.
    'Cash Flow'         — year-by-year cash flow table from tea.get_cashflow_table():
                          capital expenditures, operating costs, sales, depreciation,
                          income tax, net earnings, discounted cash flow, NPV.
    'Stoichiometry'     — production reaction stoichiometric coefficients on a mass
                          basis (g / g substrate consumed), with a g / kg SCP column.
                          Liquid routes: extracted from the bst.Reaction on R101.
                          Gas fermentation: derived from PerfusionBioreactor
                          design_results rates (Framework §5).

print_stoichiometry — prints the same stoichiometry table to stdout (called by
                      run_models.py after each route's simulate()).

The Nutrients unlumping reuses the mass_fractions already computed in
common/nutrients.py — one calculation, two consumers (TEA costing + this
export), per Framework §8.

Framework §8 / Spec §common/export.py.
"""

from __future__ import annotations
import pathlib

import biosteam as bst
import pandas as pd

from common.operating_hours import effective_operating_hours
from common.parameters import ECONOMICS, NUTRIENTS_RECIPE

# Default material of construction — stainless steel unless a unit specifies
# otherwise (needed to link to the correct ecoinvent infrastructure dataset,
# Framework §8).
_DEFAULT_MATERIAL = 'Stainless steel 304'

_OUTPUTS_DIR = pathlib.Path('outputs')


def export_results(
    system: bst.System,
    tea: object,
    route: str,
    nutrients_mass_fractions: dict[str, float],
) -> pathlib.Path:
    """Export 9-sheet workbook for one route.

    Called by run_models.py after system.simulate() and build_tea().
    Identical call signature and output schema for all four routes — Framework §8.

    Parameters
    ----------
    system : bst.System
        Fully simulated BioSTEAM system for the route.
    tea : SCPTEA
        Constructed TEA; provides FCI, FOC, VOC, and solve_price().
    route : str
        Route name ('fructose', 'acetate', 'formate', 'gas_fermentation').
    nutrients_mass_fractions : dict[str, float]
        Component → mass fraction from common.nutrients.build_nutrients_properties().
        Unlumps the Nutrients stream — Framework §8.

    Returns
    -------
    pathlib.Path
        Path of the written .xlsx file.
    """
    _OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUTS_DIR / f'{route}_results.xlsx'

    product_stream    = _scp_product_stream(system)
    msp               = tea.solve_price(product_stream)          # $/kg SCP
    product_flow_kgph = product_stream.imass['CNecatorBiomass']  # kg/h

    exec_df           = _build_executive_summary(system, tea, msp, product_flow_kgph)
    strm_df           = _build_all_streams(system, nutrients_mass_fractions, product_flow_kgph)
    equip_df          = _build_equipment_list(system)
    mb_df             = _build_mass_balance(system, nutrients_mass_fractions)
    param_df          = _build_tea_parameters()
    cap_df            = _build_capital_costs(system, tea)
    foc_df, voc_df    = _build_operating_costs(system, tea, product_flow_kgph,
                                                nutrients_mass_fractions)
    cf_df             = _build_cashflow_table(tea, product_stream, msp)
    stoich_meta, stoich_coeff = _build_stoichiometry(system)    # Framework §8 / §5

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        exec_df.to_excel(writer,  sheet_name='Executive Summary', index=False)
        strm_df.to_excel(writer,  sheet_name='All Streams',       index=False)
        equip_df.to_excel(writer, sheet_name='Equipment',         index=False)
        mb_df.to_excel(writer,    sheet_name='Mass Balance',      index=False)
        param_df.to_excel(writer, sheet_name='TEA Parameters',    index=False)
        cap_df.to_excel(writer,   sheet_name='Capital Costs',     index=False)
        foc_df.to_excel(writer,   sheet_name='Operating Costs',
                        startrow=0, index=False)
        voc_df.to_excel(writer,   sheet_name='Operating Costs',
                        startrow=len(foc_df) + 3, index=False)
        cf_df.to_excel(writer,    sheet_name='Cash Flow',         index=False)
        stoich_meta.to_excel(writer,  sheet_name='Stoichiometry',
                             startrow=0, index=False)
        stoich_coeff.to_excel(writer, sheet_name='Stoichiometry',
                              startrow=len(stoich_meta) + 2, index=False)

    return out_path


def export_unit_details_xlsx(
    system: bst.System,
    route: str,
    nutrients_mass_fractions: dict[str, float],
) -> pathlib.Path:
    """Write per-unit detail workbook to outputs/{route}_unit_details.xlsx.

    One sheet per unit in system.units.  Each sheet contains:
      - BioSTEAM's unit.results() table (utilities, design parameters, costs)
      - Stream composition table below: one row per component per stream,
        with Direction (IN/OUT), Stream ID, kg/h, mass fraction, kg/d, and
        g/L for liquid-phase streams.

    Nutrients pseudo-component is unlumped via nutrients_mass_fractions.
    Mirrors the layout of SCP_BiorefineryResults/MB Checks.xlsx — Framework §8.

    Parameters
    ----------
    system : bst.System
        Fully simulated BioSTEAM system.
    route : str
        Route name used to construct the output filename.
    nutrients_mass_fractions : dict[str, float]
        Component -> mass fraction from build_nutrients_properties().

    Returns
    -------
    pathlib.Path
        Path of the written .xlsx file.
    """
    _OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUTS_DIR / f'{route}_unit_details.xlsx'

    all_chem_ids = [c.ID for c in bst.settings.chemicals]
    _nutrient_ids = set(nutrients_mass_fractions.keys())

    # Component ordering: Nutrients unlumped, matching mass balance sheet
    row_chem_ids: list[str] = []
    for cid in all_chem_ids:
        if cid == 'Nutrients':
            row_chem_ids.extend(sorted(nutrients_mass_fractions.keys()))
        elif cid not in _nutrient_ids:
            row_chem_ids.append(cid)

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        for unit in system.units:
            sheet_name = unit.ID[:31]  # Excel sheet name limit

            # --- Unit results table ---
            try:
                results_df = unit.results()
                n_results_rows = len(results_df) + 2  # header row + data rows
            except Exception:
                results_df = pd.DataFrame({'(results unavailable)': []})
                n_results_rows = 2
            results_df.to_excel(writer, sheet_name=sheet_name, startrow=0)

            # --- Stream composition table ---
            stream_rows: list[dict] = []

            def _add_stream(direction: str, stream: bst.Stream) -> None:
                if stream is None or stream.F_mass == 0.0:
                    return
                total_kgh = stream.F_mass
                # Use water mass flow as volumetric basis for g/L (water density = 1000 kg/m³ exactly).
                # This avoids thermosteam's F_vol, which sums density contributions from
                # pseudo-components (CNecatorBiomass, Nutrients) whose densities may not be
                # accurately characterised, and which shrinks when CO2 evolves from the liquid.
                is_liquid = getattr(stream, 'phase', '') == 'l'
                try:
                    water_kgh_stream = stream.imass['H2O'] if is_liquid else 0.0
                except Exception:
                    water_kgh_stream = 0.0
                F_vol_m3h = water_kgh_stream / 1000.0 if water_kgh_stream > 0.0 else None

                # Stream header row — T and P inserted after Stream ID (Framework §8)
                stream_rows.append({
                    'Direction':     direction,
                    'Stream ID':     stream.ID or '(unnamed)',
                    'Component':     '',
                    'T (°C)':        round(stream.T - 273.15, 2),
                    'P (bar)':       round(stream.P / 1e5, 4),
                    'kg/h':          total_kgh,
                    'Mass fraction': '',
                    'kg/d':          total_kgh * 24.0,
                    'g/L':           '',
                })

                for cid in row_chem_ids:
                    if cid in _nutrient_ids:
                        try:
                            nuts_kgph = stream.imass['Nutrients']
                        except Exception:
                            nuts_kgph = 0.0
                        flow = nuts_kgph * nutrients_mass_fractions.get(cid, 0.0)
                    else:
                        try:
                            flow = stream.imass[cid]
                        except Exception:
                            flow = 0.0

                    if flow <= 0.0:
                        continue

                    mf = flow / total_kgh if total_kgh > 0.0 else 0.0
                    gl = (flow / F_vol_m3h) if F_vol_m3h else None  # kg/m³ = g/L

                    stream_rows.append({
                        'Direction':     direction,
                        'Stream ID':     '',
                        'Component':     cid,
                        'kg/h':          flow,
                        'Mass fraction': mf,
                        'kg/d':          flow * 24.0,
                        'g/L':           gl,
                    })

            for s in unit.ins:
                _add_stream('IN', s)
            for s in unit.outs:
                _add_stream('OUT', s)

            if stream_rows:
                stream_df = pd.DataFrame(stream_rows)
                startrow = n_results_rows + 1  # one blank row after unit results
                stream_df.to_excel(
                    writer, sheet_name=sheet_name,
                    startrow=startrow, index=False,
                )

    return out_path


def export_pfd(system: bst.System, route: str) -> dict[str, pathlib.Path]:
    """Save process flow diagram in PNG and HTML formats.

    Uses BioSTEAM's system.diagram() (graphviz backend).  kind='thorough'
    shows all units including the seed train.  auxiliaries=False hides
    IsentropicCompressor sub-units (design internals) for a cleaner diagram.

    Requires Graphviz executables on the system PATH.  If unavailable,
    a warning is printed per format and an empty dict is returned; the rest
    of the export pipeline continues unaffected.

    Framework §8.

    Returns
    -------
    dict[str, pathlib.Path]
        format -> path for each successfully written file.
    """
    import warnings as _warnings
    _OUTPUTS_DIR.mkdir(exist_ok=True)
    paths: dict[str, pathlib.Path] = {}
    stem = str(_OUTPUTS_DIR / f'{route}_pfd')   # graphviz appends .ext

    for fmt in ('png', 'html'):
        try:
            system.diagram(
                kind='thorough',
                file=stem,
                format=fmt,
                display=False,
                auxiliaries=False,
            )
            paths[fmt] = pathlib.Path(f'{stem}.{fmt}')
        except Exception as exc:
            _warnings.warn(
                f'PFD export failed for format {fmt!r}: {exc}. '
                'Ensure Graphviz executables are installed and on PATH.',
                stacklevel=2,
            )

    return paths


def export_unit_details(system: bst.System, route: str) -> pathlib.Path:
    """Write per-unit detail report to outputs/{route}_unit_details.txt.

    One section per unit in system.units order, using BioSTEAM's native
    unit.results() table — the same output as unit.show() — which includes
    utility flows/costs, design parameters, and itemised purchase costs.

    Format mirrors SCP_BiorefineryResults_UnitDetails.txt from the reference
    model: major separator (===) between units, minor separator (---) under
    the unit header.  Called by run_models.py after export_results().

    Parameters
    ----------
    system : bst.System
        Fully simulated BioSTEAM system.
    route : str
        Route name used to construct the output filename.

    Returns
    -------
    pathlib.Path
        Path of the written .txt file.
    """
    _OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUTS_DIR / f'{route}_unit_details.txt'

    _SEP_MAJOR = '=' * 60
    _SEP_MINOR = '-' * 50

    with open(out_path, 'w') as fh:
        fh.write('DETAILED UNIT OPERATION RESULTS\n')
        fh.write(_SEP_MAJOR + '\n')

        for unit in system.units:
            fh.write('\n\n')
            fh.write(f'{unit.ID} ({type(unit).__name__})\n')
            fh.write(_SEP_MINOR + '\n')
            try:
                fh.write(str(unit.results()) + '\n')
            except Exception as exc:
                fh.write(f'(results unavailable: {exc})\n')
            fh.write('\n' + _SEP_MAJOR + '\n')

    return out_path


# ---------------------------------------------------------------------------
# Sheet 1: Executive Summary
# ---------------------------------------------------------------------------

def _build_executive_summary(
    system: bst.System,
    tea: object,
    msp: float,
    product_flow_kgph: float,
) -> pd.DataFrame:
    """Build the Executive Summary DataFrame.

    Two columns: Metric | Value.
    Framework §8.
    """
    op_hours      = effective_operating_hours()      # h/yr
    annual_scp_kg = product_flow_kgph * op_hours     # kg/yr

    fci = tea.FCI
    try:
        tci = tea.TCI
    except AttributeError:
        tci = fci * (1.0 + tea.WC_over_FCI)

    rows = [
        {'Metric': 'MSP ($/kg SCP)',               'Value': msp},
        {'Metric': 'Annual SCP production (MT/yr)', 'Value': annual_scp_kg / 1000.0},
        {'Metric': 'Annual production (kg/h)',      'Value': product_flow_kgph},
        {'Metric': 'Operating hours (h/yr)',        'Value': op_hours},
        {'Metric': 'Fixed Capital Investment ($M)', 'Value': fci / 1e6},
        {'Metric': 'Working Capital ($M)',          'Value': (tci - fci) / 1e6},
        {'Metric': 'Total Capital Investment ($M)', 'Value': tci / 1e6},
        {'Metric': 'Annual FOC ($M/yr)',            'Value': tea.FOC / 1e6},
        {'Metric': 'Annual VOC ($M/yr)',            'Value': tea.VOC / 1e6},
        {'Metric': 'Annual depreciation ($M/yr)',   'Value': tea.annual_depreciation / 1e6},
        {'Metric': 'Annual FOC ($/kg SCP)',         'Value': tea.FOC / annual_scp_kg},
        {'Metric': 'Annual VOC ($/kg SCP)',         'Value': tea.VOC / annual_scp_kg},
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sheet 2: All Streams — flat, one row per named stream
# ---------------------------------------------------------------------------

def _build_all_streams(
    system: bst.System,
    nutrients_mass_fractions: dict[str, float],
    product_flow_kgph: float,
) -> pd.DataFrame:
    """Build the All Streams DataFrame — flat layout, one row per named stream.

    Fixed columns: Stream ID | From Unit | To Unit | Phase | Temperature (°C) |
                   Pressure (bar) | Total Flow (kg/h) | Total Molar Flow (kmol/h) |
                   Price ($/kg) | Annual Cost ($/yr)

    Followed by paired chemical columns per row_id:
        {chem} (kg/h) | {chem} (kg/kg SCP)

    row_ids construction: iterate all_chem_ids; replace 'Nutrients' with
    sorted(nutrients_mass_fractions.keys()); skip standalone salt IDs.
    Identical logic to legacy _build_stream_table — Framework §8.

    Nutrients unlumped: flow_kgph = stream.imass['Nutrients'] * frac[salt].
    """
    op_hours = effective_operating_hours()

    named_streams = [s for s in system.streams if s.ID]
    if not named_streams:
        return pd.DataFrame()

    all_chem_ids: list[str] = [c.ID for c in bst.settings.chemicals]
    _nutrient_ids: set[str] = set(nutrients_mass_fractions.keys())

    # Replace 'Nutrients' lump with sorted individual salt IDs; skip standalone salts.
    row_ids: list[str] = []
    for cid in all_chem_ids:
        if cid == 'Nutrients':
            row_ids.extend(sorted(nutrients_mass_fractions.keys()))
        elif cid not in _nutrient_ids:
            row_ids.append(cid)

    rows = []
    for stream in named_streams:
        annual_cost = stream.cost * op_hours

        row: dict = {
            'Stream ID':                 stream.ID,
            'From Unit':                 stream.source.ID if stream.source else 'Feed',
            'To Unit':                   stream.sink.ID   if stream.sink   else 'Product',
            'Phase':                     stream.phase,
            'Temperature (°C)':          stream.T - 273.15,
            'Pressure (bar)':            stream.P / 1e5,
            'Total Flow (kg/h)':         stream.F_mass,
            'Total Molar Flow (kmol/h)': stream.F_mol,
            'Price ($/kg)':              stream.price,
            'Annual Cost ($/yr)':        annual_cost,
        }

        for rid in row_ids:
            if rid in _nutrient_ids:
                # Unlump from the Nutrients pseudo-component — Framework §8
                try:
                    nuts_kgph = stream.imass['Nutrients']
                except Exception:
                    nuts_kgph = 0.0
                abs_flow = nuts_kgph * nutrients_mass_fractions.get(rid, 0.0)
            else:
                try:
                    abs_flow = stream.imass[rid]
                except Exception:
                    abs_flow = 0.0

            row[f'{rid} (kg/h)']      = abs_flow
            row[f'{rid} (kg/kg SCP)'] = (abs_flow / product_flow_kgph
                                          if product_flow_kgph > 0.0 else 0.0)

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sheet 3: Equipment — unchanged
# ---------------------------------------------------------------------------

def _build_equipment_list(system: bst.System) -> pd.DataFrame:
    """Build the equipment-list DataFrame from system.units.

    Fixed columns: ID | Type | N (parallel) | Material | Purchase cost/unit ($) |
                   Purchase cost total ($) | BM factor | Installed cost/unit ($) |
                   Installed cost total ($) | Heat duty (MJ/h) | Power (kW)
    Dynamic columns: all unique design_results keys found across system.units,
                     in order of first appearance.

    N (parallel) includes the N+1 redundancy vessel added by
    ExtentBasedBioreactor._design().  Omitting N would cause openLCA to see
    only one vessel and undercount capital-goods impact — Framework §8.

    BM factor = installed_cost / purchase_cost (bare-module multiplier).
    Heat duty: positive = heating, negative = cooling (kJ/h → MJ/h via /1000).
    """
    # Collect all design_results keys in order of first appearance across units
    all_dr_keys: list[str] = list(dict.fromkeys(
        k for unit in system.units for k in getattr(unit, 'design_results', {})
    ))

    rows = []
    for unit in system.units:
        dr = getattr(unit, 'design_results', {})
        # PerfusionBioreactor manages its own parallelization internally and stores
        # the vessel count in design_results['Number of parallel reactors'] rather
        # than in parallel['self'] (which stays at 1).  Prefer the design_results
        # entry when present so the equipment list shows the actual N.
        n = int(dr.get('Number of parallel reactors', unit.parallel.get('self', 1)))
        purchase_tot = unit.purchase_cost
        install_tot  = unit.installed_cost
        purchase_u   = purchase_tot / n if n else purchase_tot
        install_u    = install_tot  / n if n else install_tot
        bm_factor    = (install_tot / purchase_tot
                        if purchase_tot and purchase_tot > 0.0 else 1.0)

        # Heat duty: sum over all heat utilities for this unit (kJ/h → MJ/h)
        heat_duty_mjh = sum(hu.duty for hu in unit.heat_utilities) / 1000.0

        # Power: net electricity consumption (kW)
        power_kw = unit.power_utility.consumption

        row: dict = {
            'ID':                           unit.ID,
            'Type':                         type(unit).__name__,
            'N (parallel)':                 n,
            'Material':                     _DEFAULT_MATERIAL,
            'Purchase cost per unit ($)':   purchase_u,
            'Purchase cost total ($)':      purchase_tot,
            'BM factor':                    bm_factor,
            'Installed cost per unit ($)':  install_u,
            'Installed cost total ($)':     install_tot,
            'Heat duty (MJ/h)':             heat_duty_mjh if heat_duty_mjh != 0.0 else None,
            'Power (kW)':                   power_kw if power_kw != 0.0 else None,
        }
        for key in all_dr_keys:
            row[key] = dr.get(key)
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sheet 4: Mass Balance
# ---------------------------------------------------------------------------

def _build_mass_balance(
    system: bst.System,
    nutrients_mass_fractions: dict[str, float],
) -> pd.DataFrame:
    """Build the Mass Balance DataFrame.

    Columns: Component | Input (kg/h) | Output (kg/h) | Balance (kg/h) | Closure (%)

    Input  = sum of component flows across system.feeds (Nutrients unlumped).
    Output = sum of component flows across system.products (Nutrients unlumped).
    Balance = Input − Output (positive = net consumption; negative = net generation).
    Closure (%) = Output / Input × 100 if Input > 0 else blank.

    Air (N2 + O2) inputs: BioSTEAM's AeratedBioreactor._run() creates an anonymous
    (unnamed) gas-phase stream for aeration and inserts it into self.ins dynamically.
    Anonymous streams are never registered in the BioSTEAM flowsheet and are therefore
    absent from system.feeds.  This function collects unit.air from every
    AeratedBioreactor in the system and adds it to the input tally explicitly.

    Expected closures:
      N2  — 100 %: inert, passes through gas vent to system.products unchanged.
      O2  — < 100 %: consumed by aerobic respiration; atoms exit as CO2 and H2O
            in other rows of this sheet (overall atomic mass is conserved).

    Only rows with nonzero Input or Output are included — zero rows are omitted
    to keep the sheet readable.  Row ordering matches row_ids from _build_all_streams.
    Framework §8.
    """
    all_chem_ids: list[str] = [c.ID for c in bst.settings.chemicals]
    _nutrient_ids: set[str] = set(nutrients_mass_fractions.keys())

    row_ids: list[str] = []
    for cid in all_chem_ids:
        if cid == 'Nutrients':
            row_ids.extend(sorted(nutrients_mass_fractions.keys()))
        elif cid not in _nutrient_ids:
            row_ids.append(cid)

    # system.feeds does NOT include the air inlets to AeratedBioreactor units.
    # AeratedBioreactor._run() creates an anonymous bst.Stream(phase='g') with no
    # ID and inserts it into self.ins dynamically.  Anonymous (unnamed) streams are
    # never registered in the BioSTEAM flowsheet, so system.feeds excludes them —
    # O2 and N2 appear in the vent (system.products) with no corresponding inlet,
    # giving zero-input / nonzero-output rows on the mass balance.
    # Fix: collect unit.air from every AeratedBioreactor (and subclass) in the
    # system and include it in the input tally alongside system.feeds.
    # unit.air is the stream that crosses the system boundary as atmospheric air
    # feed to the bioreactor (the compressor and air_cooler are internal auxiliary
    # units — they do not add additional boundary crossings).
    _input_streams = list(system.feeds)
    for unit in system.units:
        if isinstance(unit, bst.AeratedBioreactor):
            air = unit.air
            if air is not None and air not in _input_streams:
                _input_streams.append(air)

    def _sum_flows(streams: list, rid: str) -> float:
        total = 0.0
        for stream in streams:
            if rid in _nutrient_ids:
                try:
                    nuts_kgph = stream.imass['Nutrients']
                except Exception:
                    nuts_kgph = 0.0
                total += nuts_kgph * nutrients_mass_fractions.get(rid, 0.0)
            else:
                try:
                    total += stream.imass[rid]
                except Exception:
                    pass
        return total

    rows = []
    for rid in row_ids:
        inp = _sum_flows(_input_streams, rid)
        out = _sum_flows(system.products, rid)
        if inp == 0.0 and out == 0.0:
            continue    # skip all-zero rows to keep the sheet readable
        balance = inp - out
        closure = (out / inp * 100.0) if inp > 0.0 else None
        rows.append({
            'Component':      rid,
            'Input (kg/h)':   inp,
            'Output (kg/h)':  out,
            'Balance (kg/h)': balance,
            'Closure (%)':    closure,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sheet 5: TEA Parameters
# ---------------------------------------------------------------------------

def _build_tea_parameters() -> pd.DataFrame:
    """Build the TEA Parameters DataFrame.

    Columns: Category | Parameter | Value | Description

    All 19 rows are derived from the ECONOMICS singleton — no new literals
    introduced here (Framework §9.4 / §hard-rules).
    """
    duration = ECONOMICS.duration

    rows = [
        # Financial
        ('Financial', 'IRR Target',
         f'{ECONOMICS.IRR * 100:.0f}%',
         'Internal rate of return target'),
        ('Financial', 'Plant Life',
         f'{duration[1] - duration[0]} yr',
         'Economic analysis period'),
        ('Financial', 'Income Tax Rate',
         f'{ECONOMICS.income_tax * 100:.0f}%',
         'Federal + state combined'),
        ('Financial', 'Depreciation Schedule',
         ECONOMICS.depreciation,
         'BioSTEAM schedule name'),
        # Economic Basis
        ('Economic Basis', 'CEPCI',
         ECONOMICS.CEPCI,
         'Chemical Engineering Plant Cost Index'),
        ('Economic Basis', 'Dollar Year',
         ECONOMICS.dollar_year,
         'All costs in this basis year'),
        # Construction
        ('Construction', 'Construction Schedule',
         str(ECONOMICS.construction_schedule),
         'Fraction of FCI per pre-startup year'),
        ('Construction', 'Working Capital Fraction',
         ECONOMICS.WC_over_FCI,
         'Fraction of FCI held as working capital'),
        # Operating
        ('Operating', 'Labor Cost ($/yr)',
         ECONOMICS.labor_cost,
         'Direct + fringe + supplies loaded in'),
        ('Operating', 'Property Tax',
         f'{ECONOMICS.property_tax * 100:.1f}% FCI',
         ''),
        ('Operating', 'Property Insurance',
         f'{ECONOMICS.property_insurance * 100:.1f}% FCI',
         ''),
        ('Operating', 'Maintenance',
         f'{ECONOMICS.maintenance * 100:.1f}% FCI',
         ''),
        ('Operating', 'Administration',
         f'{ECONOMICS.administration * 100:.1f}% FCI',
         ''),
        # Pricing
        ('Pricing', 'Electricity',
         f'${ECONOMICS.electricity_price}/kWh',
         ''),
        ('Pricing', 'Steam',
         f'${ECONOMICS.steam_price}/GJ',
         ''),
        ('Pricing', 'Cooling Water',
         f'${ECONOMICS.cooling_water_price}/m\u00b3',
         ''),
        ('Pricing', 'Chilled Water',
         f'${ECONOMICS.chilled_water_price}/GJ',
         ''),
        ('Pricing', 'Process Water',
         f'${ECONOMICS.water_price}/m\u00b3',
         ''),
        ('Pricing', 'Ammonia',
         f'${ECONOMICS.ammonia_price}/kg',
         ''),
        ('Pricing', 'WWT Organic Removal',
         f'${ECONOMICS.wwt_organic_removal_cost}/kg organic',
         ''),
    ]

    return pd.DataFrame(rows, columns=['Category', 'Parameter', 'Value', 'Description'])


# ---------------------------------------------------------------------------
# Sheet 6: Capital Costs
# ---------------------------------------------------------------------------

def _build_capital_costs(system: bst.System, tea: object) -> pd.DataFrame:
    """Build the Capital Costs DataFrame.

    Columns: Cost Category | Value ($) | Value ($M) | Description
    Three rows: FCI, Working Capital, TCI.
    Framework §8.
    """
    fci = tea.FCI
    try:
        tci = tea.TCI
    except AttributeError:
        tci = fci * (1.0 + tea.WC_over_FCI)
    wc = tci - fci

    rows = [
        {
            'Cost Category': 'Fixed Capital Investment (FCI)',
            'Value ($)':     fci,
            'Value ($M)':    fci / 1e6,
            'Description':   'Turton BM method: 1.18 × Σ(C_P × f_BM) — Framework §9.4',
        },
        {
            'Cost Category': 'Working Capital',
            'Value ($)':     wc,
            'Value ($M)':    wc / 1e6,
            'Description':   f'{ECONOMICS.WC_over_FCI * 100:.1f}% of FCI (Seider et al.)',
        },
        {
            'Cost Category': 'Total Capital Investment (TCI)',
            'Value ($)':     tci,
            'Value ($M)':    tci / 1e6,
            'Description':   'FCI + Working Capital',
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sheet 7: Cash Flow — year-by-year TEA table
# ---------------------------------------------------------------------------

def _build_cashflow_table(tea: object, product_stream, msp: float) -> pd.DataFrame:
    """Return the year-by-year cash flow table from tea.get_cashflow_table().

    bst.TEA.solve_price() returns the MSP analytically without setting the
    product stream's price (stream.price remains 0).  get_cashflow_table()
    uses system.sales, which sums stream.cost for priced product streams, so
    with stream.price == 0 the sales column contains only waste-disposal costs
    and the cumulative NPV converges to the (large negative) total discounted
    cost rather than to zero.

    Fix: temporarily set product_stream.price = msp so that system.sales
    includes the full product revenue, making the cash flow table reflect the
    MSP scenario (cumulative NPV → 0 at end of plant life).  The original
    price (0) is restored in a finally block so downstream code is unaffected.

    Pre-startup (construction) years appear before the first operating year;
    operating years run through the end of the plant life.

    Framework §8.
    """
    original_price = product_stream.price
    try:
        product_stream.price = msp
        df = tea.get_cashflow_table()
    finally:
        product_stream.price = original_price
    df = df.reset_index()
    # Rename the index column if BioSTEAM uses a non-descriptive name
    if df.columns[0] not in ('Year', 'year'):
        df = df.rename(columns={df.columns[0]: 'Year'})
    return df


# ---------------------------------------------------------------------------
# Sheet 8: Operating Costs — two blocks
# ---------------------------------------------------------------------------

def _build_operating_costs(
    system: bst.System,
    tea: object,
    product_flow_kgph: float,
    nutrients_mass_fractions: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build FOC and VOC DataFrames for the Operating Costs sheet.

    Block 1 (FOC) — Columns: Category | $/yr | $/kg SCP
        Rows: Property tax | Property insurance | Maintenance |
              Administration | Labor (incl. fringe/supplies) | Total FOC

    Block 2 (VOC) — Columns: Category | Flow (kg/h) | Price ($/kg) | $/yr | $/kg SCP
        Rows: feed streams (nutrients unlumped) | waste disposal |
              Electricity | heat agents | Total VOC

    Written to the same sheet:
        foc_df at startrow=0; voc_df at startrow=len(foc_df)+3.
    Framework §8.
    """
    op_hours      = effective_operating_hours()
    annual_scp_kg = product_flow_kgph * op_hours
    fci           = tea.FCI

    # ---- Block 1: Fixed Operating Costs ----

    def _per_kg(annual_usd: float) -> float | None:
        return annual_usd / annual_scp_kg if annual_scp_kg > 0.0 else None

    prop_tax_yr    = tea.property_tax       * fci
    prop_ins_yr    = tea.property_insurance * fci
    maintenance_yr = tea.maintenance        * fci
    admin_yr       = tea.administration     * fci
    labor_yr       = tea.labor_cost * (1.0 + tea.fringe_benefits + tea.supplies)

    foc_rows = [
        {'Category': 'Property tax',
         '$/yr': prop_tax_yr,    '$/kg SCP': _per_kg(prop_tax_yr)},
        {'Category': 'Property insurance',
         '$/yr': prop_ins_yr,    '$/kg SCP': _per_kg(prop_ins_yr)},
        {'Category': 'Maintenance',
         '$/yr': maintenance_yr, '$/kg SCP': _per_kg(maintenance_yr)},
        {'Category': 'Administration',
         '$/yr': admin_yr,       '$/kg SCP': _per_kg(admin_yr)},
        {'Category': 'Labor (incl. fringe/supplies)',
         '$/yr': labor_yr,       '$/kg SCP': _per_kg(labor_yr)},
        {'Category': 'Total FOC',
         '$/yr': tea.FOC,        '$/kg SCP': _per_kg(tea.FOC)},
    ]
    foc_df = pd.DataFrame(foc_rows)

    # ---- Block 2: Variable Operating Costs ----

    voc_rows: list[dict] = []

    def _voc_row(label: str,
                 flow: float | None = None,
                 price: float | None = None,
                 annual_usd: float | None = None) -> None:
        per_kg = (annual_usd / annual_scp_kg
                  if annual_usd is not None and annual_scp_kg > 0.0 else None)
        voc_rows.append({
            'Category':    label,
            'Flow (kg/h)': flow,
            'Price ($/kg)': price,
            '$/yr':         annual_usd,
            '$/kg SCP':     per_kg,
        })

    # Material feed streams with positive cost — nutrients unlumped
    for stream in system.feeds:
        cost_per_yr = stream.cost * op_hours
        if cost_per_yr > 0.0:
            _voc_row(f'Feed: {stream.ID}',
                     flow=stream.F_mass,
                     price=stream.price,
                     annual_usd=cost_per_yr)
            if stream.ID == 'nutrients_feed':
                for comp, frac in nutrients_mass_fractions.items():
                    comp_flow   = stream.F_mass * frac
                    comp_price  = NUTRIENTS_RECIPE.prices.get(comp, 0.0)
                    comp_annual = comp_flow * comp_price * op_hours
                    _voc_row(f'  -> {comp}',
                             flow=comp_flow,
                             price=comp_price,
                             annual_usd=comp_annual)

    # Waste disposal — negative-priced product streams.
    # BioSTEAM routes these through system.sales (not material_cost), so they
    # do NOT appear in tea.VOC.  They are captured by solve_price() via the
    # total_production_cost = AOC - coproduct_sales path, so the MSP is correct.
    # Accumulate total_disposal_yr so the summary row can add it back explicitly.
    total_disposal_yr = 0.0
    for stream in system.products:
        if stream.price < 0.0:
            disposal_yr = abs(stream.price) * stream.F_mass * op_hours
            total_disposal_yr += disposal_yr
            _voc_row(f'Waste disposal: {stream.ID}',
                     flow=stream.F_mass,
                     price=stream.price,
                     annual_usd=disposal_yr)

    # Electricity — flow/price blank (units incompatible with kg basis)
    power_cost_yr = system.power_utility.cost * op_hours
    if abs(power_cost_yr) > 0.0:
        _voc_row('Utility: Electricity', annual_usd=power_cost_yr)

    # Heat utilities grouped by agent — flow/price blank
    heat_by_agent: dict[str, float] = {}
    for hu in system.heat_utilities:
        agent_id = hu.agent.ID if hu.agent else 'Unknown'
        heat_by_agent[agent_id] = heat_by_agent.get(agent_id, 0.0) + hu.cost * op_hours
    for agent_id, cost_yr in heat_by_agent.items():
        if abs(cost_yr) > 0.0:
            _voc_row(f'Utility: {agent_id}', annual_usd=cost_yr)

    # tea.VOC = material_cost + utility_cost (feeds + utilities only).
    # Disposal flows through sales in BioSTEAM — add it here so the reported
    # total matches the effective cost seen by solve_price().
    _voc_row('Total VOC + WWT disposal', annual_usd=tea.VOC + total_disposal_yr)

    voc_df = pd.DataFrame(voc_rows)

    return foc_df, voc_df


# ---------------------------------------------------------------------------
# Stoichiometry — public print + private builders  (Framework §8 / §5)
# ---------------------------------------------------------------------------

def print_stoichiometry(system: bst.System, route: str) -> None:
    """Print production reaction stoichiometry to stdout.

    Liquid routes (fructose / acetate / formate): extracts the bst.Reaction
    from ExtentBasedBioreactor R101 (basis='wt', g / g substrate consumed).

    Gas fermentation: derives mass-basis coefficients from PerfusionBioreactor
    R101 design_results rates (g/h per unit), normalised by H2 consumed.

    Called by run_models.py after system.simulate() for each route — Framework §8.
    """
    substrate_id, biomass_coeff, rows = _extract_production_stoichiometry(system)
    if not rows:
        print(f'[{route}] No production reaction found in R101.')
        return

    r101  = next((u for u in system.units if u.ID == 'R101'), None)
    X_str = (f'{r101.reactions.X:.2f}'
             if r101 is not None and hasattr(r101, 'reactions')
             else 'from design_results')

    print(f'\n[{route}] Production reaction stoichiometry')
    print(f'  Substrate: {substrate_id}   '
          f'Basis: mass (g / g {substrate_id} consumed)   X = {X_str}')
    print()
    print(f'  {"Species":22s}  {"Role":10s}  {"g/g substrate":>15s}  {"g/kg SCP":>12s}')
    print(f'  {"-"*22}  {"-"*10}  {"-"*15}  {"-"*12}')
    for row in rows:
        coeff    = row['Coefficient (g/g substrate)']
        g_per_kg = coeff / biomass_coeff * 1000.0 if biomass_coeff > 0.0 else None
        g_str    = f'{g_per_kg:12.1f}' if g_per_kg is not None else '           -'
        print(f'  {row["Species"]:22s}  {row["Role"]:10s}  {coeff:+15.6f}  {g_str}')
    print()


def _extract_production_stoichiometry(
    system: bst.System,
) -> tuple[str, float, list[dict]]:
    """Extract production-bioreactor stoichiometry from R101.

    Two dispatch paths:

    Liquid routes — ExtentBasedBioreactor.reactions is a bst.Reaction with
        stoichiometry in mass basis (g / g substrate, basis='wt').

    Gas fermentation — PerfusionBioreactor stores volumetric rates
        (g/h per unit) in design_results; coefficients are derived by
        dividing each rate by 'H2 consumed (g/h)'.

    Returns
    -------
    substrate_id : str
        Chemical ID of the primary carbon/energy substrate.
    biomass_coeff : float
        g CNecatorBiomass produced per g substrate consumed (positive).
    rows : list[dict]
        One dict per non-zero species:
          'Species', 'Role' (Substrate/Reactant/Product),
          'Coefficient (g/g substrate)' (negative = consumed, positive = produced).
    """
    import numpy as np

    r101 = next((u for u in system.units if u.ID == 'R101'), None)
    if r101 is None:
        return 'Unknown', 0.0, []

    # --- Liquid routes: ExtentBasedBioreactor with bst.Reaction ---
    if hasattr(r101, 'reactions') and hasattr(r101.reactions, 'stoichiometry'):
        rxn          = r101.reactions
        chemicals    = list(rxn.chemicals)
        chem_ids     = [c.ID for c in chemicals]
        stoich       = np.array(rxn.stoichiometry.tolist())
        substrate_id = rxn.reactant
        biomass_coeff = 0.0
        rows: list[dict] = []
        for cid, coeff in zip(chem_ids, stoich):
            if abs(coeff) < 1e-12:
                continue
            if cid == substrate_id:
                role = 'Substrate'
            elif coeff < 0:
                role = 'Reactant'
            else:
                role = 'Product'
            if cid == 'CNecatorBiomass':
                biomass_coeff = float(coeff)
            rows.append({
                'Species':                     cid,
                'Role':                        role,
                'Coefficient (g/g substrate)': float(coeff),
            })
        return substrate_id, biomass_coeff, rows

    # --- Gas fermentation: PerfusionBioreactor with design_results rates ---
    dr          = getattr(r101, 'design_results', {})
    h2_consumed = dr.get('H2 consumed (g/h)', 0.0)
    if h2_consumed <= 0.0:
        return 'H2', 0.0, []

    _GAS_SPECIES: list[tuple[str, str, str]] = [
        ('H2',              'H2 consumed (g/h)',        'Substrate'),
        ('O2',              'O2 consumed (g/h)',        'Reactant'),
        ('CO2',             'CO2 consumed (g/h)',       'Reactant'),
        ('NH3',             'NH3 consumed (g/h)',       'Reactant'),
        ('Nutrients',       'Nutrients consumed (g/h)', 'Reactant'),
        ('H2O',             'H2O produced (g/h)',       'Product'),
        ('CNecatorBiomass', 'CDW produced (g/h)',       'Product'),
    ]
    biomass_coeff = 0.0
    rows = []
    for cid, dr_key, role in _GAS_SPECIES:
        rate = dr.get(dr_key, 0.0)
        if rate == 0.0:
            continue
        sign  = -1.0 if role in ('Substrate', 'Reactant') else +1.0
        coeff = sign * rate / h2_consumed
        if cid == 'CNecatorBiomass':
            biomass_coeff = abs(coeff)
        rows.append({
            'Species':                     cid,
            'Role':                        role,
            'Coefficient (g/g substrate)': coeff,
        })
    return 'H2', biomass_coeff, rows


def _build_stoichiometry(
    system: bst.System,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build stoichiometry header and coefficient DataFrames for the Excel sheet.

    Returns
    -------
    meta_df : pd.DataFrame
        Three-row table: Parameter | Value.
        Rows: Substrate, Reaction basis, Conversion (X).
    coeff_df : pd.DataFrame
        Coefficient table: Species | Role | g/g substrate | g/kg SCP.
        Negative values = consumed; positive = produced.

    Written to the 'Stoichiometry' sheet at startrow=0 (meta) and
    startrow=len(meta)+2 (coeff) — Framework §8.
    """
    substrate_id, biomass_coeff, rows = _extract_production_stoichiometry(system)

    r101  = next((u for u in system.units if u.ID == 'R101'), None)
    X_val = (r101.reactions.X
             if r101 is not None and hasattr(r101, 'reactions')
             else 'see design_results')

    meta_df = pd.DataFrame([
        {'Parameter': 'Substrate',      'Value': substrate_id},
        {'Parameter': 'Reaction basis', 'Value': 'mass (g / g substrate consumed)'},
        {'Parameter': 'Conversion (X)', 'Value': X_val},
    ])

    if not rows:
        return meta_df, pd.DataFrame()

    coeff_rows = []
    for row in rows:
        coeff    = row['Coefficient (g/g substrate)']
        g_per_kg = coeff / biomass_coeff * 1000.0 if biomass_coeff > 0.0 else None
        coeff_rows.append({
            'Species':         row['Species'],
            'Role':            row['Role'],
            'g / g substrate': coeff,
            'g / kg SCP':      g_per_kg,
        })
    return meta_df, pd.DataFrame(coeff_rows)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def export_cross_route_comparison(results: dict) -> pathlib.Path:
    """Write cross-route comparison workbook to outputs/cross_route_comparison.xlsx.

    Called by run_models.main() after all routes complete.
    Only called when len(results) > 1.
    Framework §8.
    """
    _OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUTS_DIR / 'cross_route_comparison.xlsx'

    summary_df = _build_comparison_summary(results)
    capital_df = _build_comparison_capital(results)
    opex_df    = _build_comparison_opex(results)

    with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Summary',                 index=False)
        capital_df.to_excel(writer, sheet_name='Capital by Unit',         index=False)
        opex_df.to_excel(writer,    sheet_name='Operating Costs by Route', index=False)

    return out_path


# ---------------------------------------------------------------------------
# Cross-route comparison helpers
# ---------------------------------------------------------------------------

def _build_comparison_summary(results: dict) -> pd.DataFrame:
    """Build the Summary DataFrame for the cross-route comparison workbook.

    Transposed layout: rows = metrics, one column per route.
    Reuses effective_operating_hours() and _scp_product_stream() — Framework §8.
    """
    op_hours = effective_operating_hours()

    metrics = [
        'MSP ($/kg SCP)',
        'Annual production (MT/yr)',
        'FCI ($M)',
        'Working capital ($M)',
        'TCI ($M)',
        'Annual FOC ($M/yr)',
        'Annual VOC ($M/yr)',
        'FOC ($/kg SCP)',
        'VOC ($/kg SCP)',
        'Annual depreciation ($M/yr)',
    ]

    data: dict[str, list] = {'Metric': metrics}

    for route, r in results.items():
        tea    = r['tea']
        system = r['system']

        product_stream    = _scp_product_stream(system)
        product_flow_kgph = product_stream.imass['CNecatorBiomass']
        annual_scp_kg     = product_flow_kgph * op_hours

        fci = tea.FCI
        try:
            tci = tea.TCI
        except AttributeError:
            tci = fci * (1.0 + tea.WC_over_FCI)
        wc = tci - fci

        data[route] = [
            r['msp'],
            annual_scp_kg / 1000.0,
            fci / 1e6,
            wc / 1e6,
            tci / 1e6,
            tea.FOC / 1e6,
            tea.VOC / 1e6,
            tea.FOC / annual_scp_kg if annual_scp_kg > 0.0 else None,
            tea.VOC / annual_scp_kg if annual_scp_kg > 0.0 else None,
            tea.annual_depreciation / 1e6,
        ]

    return pd.DataFrame(data)


def _build_comparison_capital(results: dict) -> pd.DataFrame:
    """Build the Capital by Unit DataFrame for the cross-route comparison workbook.

    One row per (route, unit). Columns: Route | Unit ID | Type | N (parallel) |
    Purchase cost ($) | Installed cost ($) | Fraction of FCI (%).
    N follows the same pattern as _build_equipment_list() — Framework §8.
    """
    rows: list[dict] = []

    for route, r in results.items():
        tea    = r['tea']
        system = r['system']
        fci    = tea.FCI

        for unit in system.units:
            dr = getattr(unit, 'design_results', {})
            # PerfusionBioreactor stores vessel count in design_results rather than
            # parallel['self'] — prefer design_results when present (same as _build_equipment_list).
            n             = int(dr.get('Number of parallel reactors', unit.parallel.get('self', 1)))
            purchase_cost  = unit.purchase_cost
            installed_cost = unit.installed_cost
            frac_fci       = (installed_cost / fci * 100.0
                               if fci and fci > 0.0 else None)

            rows.append({
                'Route':               route,
                'Unit ID':             unit.ID,
                'Type':                type(unit).__name__,
                'N (parallel)':        n,
                'Purchase cost ($)':   purchase_cost,
                'Installed cost ($)':  installed_cost,
                'Fraction of FCI (%)': frac_fci,
            })

    return pd.DataFrame(rows)


def _build_comparison_opex(results: dict) -> pd.DataFrame:
    """Build the Operating Costs by Route DataFrame for the cross-route comparison workbook.

    One row per cost line per route. Columns: Route | Category | $/yr | $/kg SCP.
    Row order per route: feed streams | electricity | heat agents | Total VOC |
    property tax | property insurance | maintenance | administration | labor |
    Total FOC | Grand total.
    Reuses the same feed/utility iteration pattern as _build_operating_costs() — Framework §8.
    """
    op_hours = effective_operating_hours()
    rows: list[dict] = []

    for route, r in results.items():
        tea    = r['tea']
        system = r['system']

        product_stream    = _scp_product_stream(system)
        product_flow_kgph = product_stream.imass['CNecatorBiomass']
        annual_scp_kg     = product_flow_kgph * op_hours

        def _per_kg(annual_usd: float) -> float | None:
            return annual_usd / annual_scp_kg if annual_scp_kg > 0.0 else None

        def _row(category: str, annual_usd: float) -> None:
            rows.append({
                'Route':    route,
                'Category': category,
                '$/yr':     annual_usd,
                '$/kg SCP': _per_kg(annual_usd),
            })

        # Feed streams with positive cost
        for stream in system.feeds:
            cost_per_yr = stream.cost * op_hours
            if cost_per_yr > 0.0:
                _row(f'Feed: {stream.ID}', cost_per_yr)

        # Waste disposal — negative-priced product streams (flows through
        # system.sales in BioSTEAM, not tea.VOC; see common/wastewater.py).
        total_disposal_yr = 0.0
        for stream in system.products:
            if stream.price < 0.0:
                disposal_yr = abs(stream.price) * stream.F_mass * op_hours
                total_disposal_yr += disposal_yr
                _row(f'Waste disposal: {stream.ID}', disposal_yr)

        # Electricity utility
        power_cost_yr = system.power_utility.cost * op_hours
        if abs(power_cost_yr) > 0.0:
            _row('Utility: Electricity', power_cost_yr)

        # Heat utilities grouped by agent
        heat_by_agent: dict[str, float] = {}
        for hu in system.heat_utilities:
            agent_id = hu.agent.ID if hu.agent else 'Unknown'
            heat_by_agent[agent_id] = heat_by_agent.get(agent_id, 0.0) + hu.cost * op_hours
        for agent_id, cost_yr in heat_by_agent.items():
            if abs(cost_yr) > 0.0:
                _row(f'Utility: {agent_id}', cost_yr)

        _row('Total VOC + WWT disposal', tea.VOC + total_disposal_yr)

        # Fixed operating cost line items
        fci            = tea.FCI
        prop_tax_yr    = tea.property_tax       * fci
        prop_ins_yr    = tea.property_insurance * fci
        maintenance_yr = tea.maintenance        * fci
        admin_yr       = tea.administration     * fci
        labor_yr       = tea.labor_cost * (1.0 + tea.fringe_benefits + tea.supplies)

        _row('Property tax',       prop_tax_yr)
        _row('Property insurance', prop_ins_yr)
        _row('Maintenance',        maintenance_yr)
        _row('Administration',     admin_yr)
        _row('Labor',              labor_yr)
        _row('Total FOC',          tea.FOC)

        _row('Grand total (FOC + VOC)', tea.FOC + tea.VOC)

    return pd.DataFrame(rows)


def _scp_product_stream(system: bst.System) -> bst.Stream:
    """Return the product stream carrying the largest CNecatorBiomass mass flow.

    Searches system.products (streams that exit the system boundary) rather than
    system.streams (all streams, including intermediates).  The bioreactor liquid
    effluent is an intermediate stream with more biomass than the final dried product
    (centrifuge removes 5 %), so using system.streams would return the wrong stream.

    Raises
    ------
    ValueError
        If no product stream carries nonzero CNecatorBiomass after simulation.
    """
    best_stream = None
    max_flow    = 0.0
    for stream in system.products:
        try:
            flow = stream.imass['CNecatorBiomass']
        except Exception:
            continue
        if flow > max_flow:
            max_flow    = flow
            best_stream = stream
    if best_stream is None or max_flow <= 0.0:
        raise ValueError(
            'No CNecatorBiomass flow found in any system stream. '
            'Ensure the system has been simulated before calling export_results().'
        )
    return best_stream
