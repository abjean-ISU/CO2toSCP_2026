"""Chemical definitions for all four SCP routes.

Exposes one public function: ``build_chemicals() -> bst.Chemicals``.
Caller must call ``bst.settings.set_thermo(chemicals)`` before creating any
streams or units.

Prices are NOT set on Chemical objects here — BioSTEAM prices are a Stream
attribute, not a Chemical attribute (confirmed from installed thermosteam
source).  Feedstock/media prices from parameters.py are applied to feed
streams in each route model builder.

Framework §10 / Spec §common/chemicals.py.
"""

from __future__ import annotations
import biosteam as bst
from common.parameters import NUTRIENTS_RECIPE


def build_chemicals() -> bst.Chemicals:
    """Build and return the BioSTEAM chemicals registry for all four SCP routes.

    All pseudo-components call ``.default()`` after construction so that
    BioSTEAM's ``set_thermo`` compile step finds the required thermodynamic
    properties (V, S, H, Cn) — confirmed behaviour from installed source.
    """

    # ------------------------------------------------------------------
    # Core process chemicals — all present in BioSTEAM database
    # ------------------------------------------------------------------
    # Framework §7: core growth reaction
    #   substrate + NH3 + O2 + Nutrients → CNecatorBiomass + CO2 + H2O
    NH3        = bst.Chemical('NH3')        # nitrogen source — Framework §7
    Fructose   = bst.Chemical('Fructose')   # carbon source, fructose route
    AceticAcid = bst.Chemical('AceticAcid') # carbon source, acetate route
    FormicAcid = bst.Chemical('FormicAcid') # carbon source, formate route
    H2         = bst.Chemical('H2')         # electron donor, gas fermentation route
    O2         = bst.Chemical('O2')         # terminal electron acceptor (all routes)
    CO2        = bst.Chemical('CO2')        # metabolic product; C source (gas ferm.)
    H2O        = bst.Chemical('H2O')
    N2         = bst.Chemical('N2')         # carrier gas / headspace component

    # ------------------------------------------------------------------
    # Nutrient salt components (all present in BioSTEAM database)
    # ------------------------------------------------------------------
    # Real chemicals that make up the Nutrients pseudo-component lump.
    # Their MWs drive the molar-average MW of the Nutrients Chemical below.
    # Framework §9.3 / §7.
    # KH2PO4, NaHCO3, FerricAmmoniumCitrate are in the BioSTEAM database but
    # have incomplete thermo data (Psat/Tb/Hvap missing or non-functional) that
    # blocks set_thermo compilation even after .default().  Fix: create as
    # pseudo-components (search_db=False) with the MW from the DB lookup,
    # then call .default() — confirmed working from installed source.
    KH2PO4 = bst.Chemical(
        'KH2PO4', MW=bst.Chemical('KH2PO4').MW, phase='l', search_db=False,
    ); KH2PO4.default()
    AmmoniumSulfate = bst.Chemical(
        'AmmoniumSulfate', MW=bst.Chemical('AmmoniumSulfate').MW, phase='l', search_db=False,
    ); AmmoniumSulfate.default()  # (NH4)2SO4 — same pseudo-component pattern as KH2PO4/NaHCO3
    NaHCO3 = bst.Chemical(
        'NaHCO3', MW=bst.Chemical('NaHCO3').MW, phase='l', search_db=False,
    ); NaHCO3.default()
    FerricAmmoniumCitrate = bst.Chemical(
        'FerricAmmoniumCitrate', MW=bst.Chemical('FerricAmmoniumCitrate').MW,
        phase='l', search_db=False,
    ); FerricAmmoniumCitrate.default()

    # ------------------------------------------------------------------
    # Hydrated salt pseudo-components
    # ------------------------------------------------------------------
    # Recipe specifies Na2HPO4·2H2O and MgSO4·7H2O (as weighed into media).
    # BioSTEAM database has only anhydrous forms; hydrated MW derived as:
    #   MW_hydrated = MW_anhydrous + n_water × H2O.MW   (compute, don't assert)
    # Framework §7 "compute, don't assert" principle; IDs match NUTRIENTS_RECIPE
    # keys exactly so the _nutrients_mw() lookup works without a separate mapping.
    Na2HPO4_2H2O = bst.Chemical(
        'Na2HPO4.2H2O',
        MW=bst.Chemical('Na2HPO4').MW + 2 * H2O.MW,  # 141.96 + 36.04 = 178.00
        phase='l', search_db=False,
    )
    Na2HPO4_2H2O.default()

    MgSO4_7H2O = bst.Chemical(
        'MgSO4.7H2O',
        MW=bst.Chemical('MgSO4').MW + 7 * H2O.MW,    # 120.37 + 126.14 = 246.51
        phase='l', search_db=False,
    )
    MgSO4_7H2O.default()

    # ------------------------------------------------------------------
    # TraceMetals pseudo-component (Framework §9.3)
    # ------------------------------------------------------------------
    # Seven trace metals (H3BO3, CoCl2, ZnSO4, MnCl2, Na2MoO4, NiCl2, CuSO4)
    # lumped into one pseudo-component (~0.02 % of recipe mass).
    # MW = molar-average at stock-solution proportions — computed from
    # BioSTEAM database MWs, not hardcoded.
    TraceMetals = _build_trace_metals()

    # ------------------------------------------------------------------
    # CNecatorBiomass pseudo-component (Framework §7)
    # ------------------------------------------------------------------
    # Empirical formula C4.09H7.13O1.89N0.76 (Roels/Herbert elemental analysis).
    # BioSTEAM supports non-integer formula subscripts — confirmed from installed
    # source; MW computed automatically as 97.19 g/mol.
    CNecatorBiomass = bst.Chemical(
        'CNecatorBiomass',
        formula='C4.09H7.13O1.89N0.76',
        phase='s', search_db=False,
    )
    CNecatorBiomass.default()

    # ------------------------------------------------------------------
    # Nutrients pseudo-component (Framework §7)
    # ------------------------------------------------------------------
    # Lumped mineral-salts media component consumed stoichiometrically (mass
    # basis, basis='wt').  MW derived from the recipe — not invented.
    # Price is NOT set here; it is applied to the Nutrients feed stream in each
    # route model builder using the composite price from nutrients.py.
    nutrient_chemicals = [
        Na2HPO4_2H2O, KH2PO4, AmmoniumSulfate, MgSO4_7H2O,
        NaHCO3, FerricAmmoniumCitrate, TraceMetals,
    ]
    MW_nutrients = _nutrients_mw(
        concentrations=NUTRIENTS_RECIPE.concentrations,
        component_mws={c.ID: c.MW for c in nutrient_chemicals},
    )
    Nutrients = bst.Chemical('Nutrients', MW=MW_nutrients, phase='l', search_db=False)
    Nutrients.default()

    # ------------------------------------------------------------------
    # Assemble registry
    # ------------------------------------------------------------------
    return bst.Chemicals([
        # Core process chemicals
        NH3, Fructose, AceticAcid, FormicAcid, H2,
        O2, CO2, H2O, N2,
        # Nutrient salt components
        Na2HPO4_2H2O, KH2PO4, AmmoniumSulfate, MgSO4_7H2O, NaHCO3,
        FerricAmmoniumCitrate, TraceMetals,
        # Biomass and lumped media
        CNecatorBiomass, Nutrients,
    ])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_trace_metals() -> bst.Chemical:
    """Molar-average MW of the 7 trace metals at stock-solution proportions.

    Stock solution concentrations (g/L) from Framework §9.3:
      H3BO3 0.6, CoCl2 0.4, ZnSO4 0.2, MnCl2 0.06,
      Na2MoO4 0.06, NiCl2 0.04, CuSO4 0.02
    All seven are present in the BioSTEAM database (verified).
    MW = total_stock_mass / total_stock_moles — computed, not hardcoded.
    """
    stock = {               # g/L in stock solution — Framework §9.3
        'H3BO3':   0.60,
        'CoCl2':   0.40,
        'ZnSO4':   0.20,
        'MnCl2':   0.06,
        'Na2MoO4': 0.06,
        'NiCl2':   0.04,
        'CuSO4':   0.02,
    }
    component_mws   = {name: bst.Chemical(name).MW for name in stock}
    total_mass      = sum(stock.values())
    total_moles     = sum(conc / component_mws[name] for name, conc in stock.items())
    c = bst.Chemical('TraceMetals', MW=total_mass / total_moles, phase='l', search_db=False)
    c.default()
    return c


def _nutrients_mw(concentrations: dict[str, float],
                   component_mws: dict[str, float]) -> float:
    """Molar-average MW of the Nutrients pseudo-component.

    Parameters
    ----------
    concentrations:
        Recipe component ID → g/L  (from NUTRIENTS_RECIPE.concentrations).
        Keys must match the Chemical IDs in component_mws exactly.
    component_mws:
        Recipe component ID → g/mol  (built from Chemical objects above).

    Returns
    -------
    float
        Molar-average MW in g/mol.

    Notes
    -----
    Molar-average MW = total_mass / total_moles, consistent with BioSTEAM's
    own stream.MW definition.  This is the same quantity that would be read
    off a reference bst.Stream built at the recipe's mass proportions.
    Framework §7 "compute, don't assert."
    """
    total_mass  = sum(concentrations.values())
    total_moles = sum(conc / component_mws[cid] for cid, conc in concentrations.items())
    return total_mass / total_moles
