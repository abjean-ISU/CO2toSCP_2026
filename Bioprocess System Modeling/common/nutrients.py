"""Nutrients derived properties: composite price, stoichiometric coefficient,
and mass fractions — all computed live from the raw recipe dict.

Public function
---------------
build_nutrients_properties — derive composite price, stoichiometric
    coefficient, and mass fractions from recipe concentrations and prices.

Deviation from Spec pseudocode (§common/nutrients.py)
------------------------------------------------------
The Spec's ``build_nutrients_chemical`` pseudocode creates a new
``bst.Chemical('Nutrients', ...)`` and sets ``Nutrients.price``.  Both are
incorrect as written:
  - The Nutrients Chemical is already built in common/chemicals.py and
    registered via bst.settings.set_thermo(); creating it a second time
    would conflict with the live registry.
  - ``Chemical.price`` does not exist in thermosteam (confirmed from installed
    source); prices are a Stream attribute, applied to feed streams by the
    route model builder.
This function therefore returns (composite_price, coefficient, mass_fractions)
and leaves Chemical creation and stream wiring to the appropriate callers.

Framework §7 / §9.3 / Spec §common/nutrients.py.
"""

from __future__ import annotations


def build_nutrients_properties(
    concentrations: dict[str, float],
    prices: dict[str, float],
    achieved_titer: float,
) -> tuple[float, float, dict[str, float]]:
    """Derive composite price, stoichiometric coefficient, and mass fractions.

    All three quantities are computed live from the raw recipe — nothing
    hardcoded.  Caller applies composite_price to the Nutrients feed stream
    (``stream.price = composite_price``).

    Parameters
    ----------
    concentrations : dict[str, float]
        Component name → g/L in fermentation media (Framework §9.3).
    prices : dict[str, float]
        Component name → $/kg (Framework §9.3).
        Must contain a key for every key in concentrations.
    achieved_titer : float
        CDW titer (g/L) at which the recipe was reported (Framework §9.3).
        Basis for the stoichiometric coefficient.

    Returns
    -------
    composite_price : float
        Mass-weighted $/kg for the Nutrients feed stream.
    coefficient : float
        g Nutrients consumed per g biomass produced.
        Derived as sum(concentrations.values()) / achieved_titer — Framework §9.3.
    mass_fractions : dict[str, float]
        Component name → mass fraction (sums to 1.0).
        Passed to common/export.py to unlump the Nutrients stream into
        individual components for the LCI stream table.

    Raises
    ------
    ValueError
        If concentrations is empty or achieved_titer <= 0.
    KeyError
        If any concentrations key is absent from prices.
    """
    if not concentrations:
        raise ValueError('concentrations dict is empty.')
    if achieved_titer <= 0:
        raise ValueError(
            f'achieved_titer must be positive; got {achieved_titer}.'
        )

    missing = set(concentrations) - set(prices)
    if missing:
        raise KeyError(
            f'Price missing for recipe component(s): {missing}. '
            'Every key in concentrations must have a corresponding entry in prices.'
        )

    total_mass: float = sum(concentrations.values())    # g/L

    # Mass fractions — sum to 1.0 (Framework §7 "compute, don't assert")
    mass_fractions: dict[str, float] = {
        component: conc / total_mass
        for component, conc in concentrations.items()
    }

    # Composite price — mass-weighted average ($/kg)
    composite_price: float = sum(
        mass_fractions[c] * prices[c] for c in concentrations
    )

    # Stoichiometric coefficient (Framework §9.3)
    # = total recipe g/L ÷ CDW titer g/L at which the recipe was reported
    coefficient: float = total_mass / achieved_titer    # g Nutrients / g biomass

    return composite_price, coefficient, mass_fractions
