# copyright  2018 Carlos Wong, Akurey SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)..

import re

from odoo import models, fields, api


class PartnerElectronic(models.Model):
    _inherit = "res.partner"

    # Province
    state_id = fields.Many2one("res.country.state", string="Province")

    # Canton
    county_id = fields.Many2one("res.country.county", string="Canton")

    # District
    district_id = fields.Many2one("res.country.district", string="District")

    # Neighborhood
    neighborhood_id = fields.Many2one("res.country.neighborhood", string="Neighborhood")

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

    # When you change the province you must clean the other fields to avoid inconveniences
    @api.onchange('state_id')
    def _change_state_id(self):
        self.county_id = False
        self.district_id = False
        self.neighborhood_id = False

    # When you change the canton you must clean the other fields to avoid inconveniences
    @api.onchange('county_id')
    def _change_county_id(self):
        self.district_id = False
        self.neighborhood_id = False

    # When you change the district you must clean the other fields to avoid inconveniences
    @api.onchange('district_id')
    def _calculate_postal_code(self):
        if self.state_id.code and self.county_id.code and self.district_id.code:
            postal = str(self.state_id.code) + str(self.county_id.code) + str(self.district_id.code)
            self.zip = postal
        else:
            self.zip = False
        self.neighborhood_id = False

    # When the neighborhood changes, the city field of odoo is autocomplete
    @api.onchange('neighborhood_id')
    def _change_neighborhood_id(self):
        self.city = self.neighborhood_id.name
