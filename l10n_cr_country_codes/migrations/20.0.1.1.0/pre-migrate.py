"""Move the barrios whose xmlid had a dot back under l10n_cr_country_codes.

Odoo splits an xmlid on its first dot, so "neighborhood_Otoya._Carmen_San_José_SJ" was stored as
module "neighborhood_Otoya", name "_Carmen_San_José_SJ": 593 barrios belonged to made-up modules,
were never cleaned up with the module, and logged "Creating record ... in module" on install.
The data now uses the same xmlids without the dot (plus the Hacienda code where two barrios of a
district share a name). Renaming the existing ir_model_data rows keeps them linked to the same
barrios instead of creating duplicates.
"""
import csv
import logging
import os

_logger = logging.getLogger(__name__)

MODULE = 'l10n_cr_country_codes'

# Two barrios with the same name in the same district: the dotted one gets its Hacienda code.
SAME_NAME = {
    'neighborhood_Flores._San_José_Alajuela_A': 'neighborhood_Flores_05_San_José_Alajuela_A',
    'neighborhood_Virginia._Nicoya_Nicoya_G': 'neighborhood_Virginia_11_Nicoya_Nicoya_G',
    'neighborhood_Santa_Rosa._La_Cruz_La_Cruz_G': 'neighborhood_Santa_Rosa_32_La_Cruz_La_Cruz_G',
    'neighborhood_El_Roble._El_Roble_Puntarenas_P': 'neighborhood_El_Roble_01_El_Roble_Puntarenas_P',
}


def _data_xmlids():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'res.country.neighborhood.csv')
    with open(path, encoding='utf-8') as f:
        return {row['id'] for row in csv.DictReader(f)}


def migrate(cr, version):
    xmlids = _data_xmlids()
    cr.execute("""SELECT id, module, name FROM ir_model_data
                   WHERE model = 'res.country.neighborhood' AND module != %s""", [MODULE])
    renamed = 0
    for imd_id, module, name in cr.fetchall():
        old = f'{module}.{name}'
        new = SAME_NAME.get(old, old.replace('.', ''))
        if new not in xmlids:
            continue  # not one of this module's barrios (e.g. one dropped from Hacienda's list)
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s", [MODULE, new])
        if cr.fetchone():
            _logger.warning("Barrio xmlid %s already exists, %s left as is", new, old)
            continue
        cr.execute("UPDATE ir_model_data SET module = %s, name = %s WHERE id = %s", [MODULE, new, imd_id])
        renamed += 1
    _logger.info("Barrio xmlids moved back under %s: %s", MODULE, renamed)
