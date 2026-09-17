"""Top-level driver — build, simulate, TEA, and export for all implemented SCP routes.

Usage
-----
    python run_models.py

or from a Jupyter notebook:

    from run_models import main
    results = main()          # dict: route -> {'path': Path, 'msp': float, 'tea': SCPTEA}

Framework §10 / Spec §run_models.py.

Route status
------------
  fructose        — implemented ✓
  acetate         — implemented ✓
  formate         — implemented ✓
  gas_fermentation — implemented ✓

To activate a new route: import its builder below and add it to _BUILDERS.
"""

from __future__ import annotations

import pathlib
import warnings

import biosteam as bst

from common.economics import build_tea
from common.export import (export_results, export_unit_details,
                            export_unit_details_xlsx, export_pfd,
                            export_cross_route_comparison, print_stoichiometry)
from common.lca_export import export_lca_inventory
from common.parameters import ECONOMICS, get

# ---------------------------------------------------------------------------
# Builder registry — add each route as its model is implemented
# ---------------------------------------------------------------------------
from models.fructose_model          import build_fructose_system
from models.acetate_model           import build_acetate_system
from models.formate_model           import build_formate_system
from models.gas_fermentation_model  import build_gas_fermentation_system

_BUILDERS: dict[str, object] = {
    'fructose':          build_fructose_system,
    'acetate':           build_acetate_system,
    'formate':           build_formate_system,
    'gas_fermentation':  build_gas_fermentation_system,
}


def main(
    routes: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, dict]:
    """Run all implemented routes (or a subset) and return results.

    Parameters
    ----------
    routes : list[str] | None
        Route names to run.  Defaults to all keys in _BUILDERS.
    verbose : bool
        Print progress and key metrics to stdout.

    Returns
    -------
    dict
        route -> {'path': pathlib.Path, 'msp': float, 'tea': SCPTEA,
                  'system': bst.System, 'nutrients_mass_fractions': dict}
    """
    if routes is None:
        routes = list(_BUILDERS.keys())

    results: dict[str, dict] = {}

    for route in routes:
        if route not in _BUILDERS:
            warnings.warn(
                f"Route '{route}' is not in _BUILDERS — model not yet implemented; skipping.",
                stacklevel=2,
            )
            continue

        with bst.Flowsheet(route):              # isolate unit/stream IDs — Framework §10

            if verbose:
                print(f'\n[{route}] Building system...')

            params  = get(route)
            builder = _BUILDERS[route]

            system, nutrients_mass_fractions = builder(params, ECONOMICS)

            if verbose:
                print(f'[{route}] Simulating...')

            system.simulate()

            if verbose:
                print(f'[{route}] Building TEA...')

            tea = build_tea(system, ECONOMICS)

            # Identify product stream (highest CNecatorBiomass flow among system.products)
            product = max(
                (s for s in system.products
                 if s.imass['CNecatorBiomass'] > 0.0),
                key=lambda s: s.imass['CNecatorBiomass'],
            )
            msp = tea.solve_price(product)

            if verbose:
                from common.operating_hours import effective_operating_hours
                op_hours = effective_operating_hours()
                annual_mt = product.imass['CNecatorBiomass'] * op_hours / 1000
                print(f'[{route}] MSP = ${msp:.2f}/kg SCP')
                print(f'[{route}] FCI = ${tea.FCI/1e6:.1f}M')
                print(f'[{route}] Annual production = {annual_mt:.0f} MT/yr')
                print_stoichiometry(system, route)

            if verbose:
                print(f'[{route}] Exporting results...')

            out_path    = export_results(system, tea, route, nutrients_mass_fractions)
            detail_path = export_unit_details(system, route)
            xlsx_path   = export_unit_details_xlsx(system, route, nutrients_mass_fractions)
            pfd_paths   = export_pfd(system, route)
            lca_path    = export_lca_inventory(system, route, ECONOMICS)

            if verbose:
                print(f'[{route}] Written -> {out_path}')
                print(f'[{route}] Unit details -> {detail_path}')
                print(f'[{route}] Unit details (xlsx) -> {xlsx_path}')
                for fmt, p in pfd_paths.items():
                    print(f'[{route}] PFD ({fmt}) -> {p}')
                print(f'[{route}] LCA inventory -> {lca_path}')

            results[route] = {
                'path':                    out_path,
                'msp':                     msp,
                'tea':                     tea,
                'system':                  system,
                'nutrients_mass_fractions': nutrients_mass_fractions,
            }

    if len(results) > 1:
        comp_path = export_cross_route_comparison(results)
        if verbose:
            print(f'\n[comparison] Written -> {comp_path}')

    return results


if __name__ == '__main__':
    main()
