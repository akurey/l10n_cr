# copyright  2018 Carlos Wong, Akurey SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    state_id = fields.Many2one("res.country.state", string="Province")
    county_id = fields.Many2one(
        "res.country.county", string="Canton", domain="[('state_id', '=', state_id)]")
    district_id = fields.Many2one(
        "res.country.district", string="District", domain="[('county_id', '=', county_id)]")
    neighborhood_id = fields.Many2one(
        "res.country.neighborhood", string="Neighborhood", domain="[('district_id', '=', district_id)]")

    # Keys for Costa Rica's address_format
    county_name = fields.Char(string="Canton Name", related="county_id.name")
    district_name = fields.Char(string="District Name", related="district_id.name")

    @api.model
    def _formatting_address_fields(self):
        return super()._formatting_address_fields() + ['county_name', 'district_name']

    def _display_address(self, without_name=False, separator='\n'):
        address = super()._display_address(without_name=without_name, separator=separator)
        if self.country_id.code != 'CR':
            return address
        # Drop the commas left by an empty canton, district or barrio
        address = re.sub(r',(\s*,)+', ',', address)
        return re.sub(r'^\s*,\s*|\s*,\s*$', '', address, flags=re.MULTILINE)

    # Changing the province clears canton, district and barrio
    @api.onchange('state_id')
    def _change_state_id(self):
        self.county_id = False
        self.district_id = False
        self.neighborhood_id = False

    # Changing the canton clears district and barrio
    @api.onchange('county_id')
    def _change_county_id(self):
        self.district_id = False
        self.neighborhood_id = False

    # The district sets the ZIP (province, canton and district codes) and clears the barrio
    @api.onchange('district_id')
    def _change_district_id(self):
        codes = (self.state_id.code, self.county_id.code, self.district_id.code)
        self.zip = ''.join(codes) if all(codes) else False
        self.neighborhood_id = False

    # The barrio's name goes to the city, which is hidden for Costa Rica
    @api.onchange('neighborhood_id')
    def _change_neighborhood_id(self):
        self.city = self.neighborhood_id.name
