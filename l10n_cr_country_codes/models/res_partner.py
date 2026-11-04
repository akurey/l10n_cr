# copyright  2018 Carlos Wong, Akurey SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import re

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    state_id = fields.Many2one("res.country.state", string="Province")
    county_id = fields.Many2one(
        "res.country.county", string="Canton", domain="[('state_id', '=?', state_id)]")
    district_id = fields.Many2one(
        "res.country.district", string="District",
        domain="[('county_id', '=?', county_id), ('county_id.state_id', '=?', state_id)]")
    neighborhood_id = fields.Many2one(
        "res.country.neighborhood", string="Neighborhood",
        domain=(
            "[('district_id', '=?', district_id), ('district_id.county_id', '=?', county_id),"
            " ('district_id.county_id.state_id', '=?', state_id)]"))

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

    # Any level can be picked first: it fills the levels above it, and a change clears the levels below that no
    # longer belong to it. The ZIP comes from the district (province, canton and district codes), the city from
    # the barrio's name (the city is hidden for Costa Rica).
    @api.onchange('state_id')
    def _change_state_id(self):
        if self.county_id.state_id != self.state_id:
            self.county_id = False

    @api.onchange('county_id')
    def _change_county_id(self):
        if self.county_id:
            self.state_id = self.county_id.state_id
        if self.district_id.county_id != self.county_id:
            self.district_id = False

    @api.onchange('district_id')
    def _change_district_id(self):
        district = self.district_id
        if district:
            self.county_id = district.county_id
        if self.neighborhood_id.district_id != district:
            self.neighborhood_id = False
        codes = (district.county_id.state_id.code, district.county_id.code, district.code)
        self.zip = ''.join(codes) if all(codes) else False

    @api.onchange('neighborhood_id')
    def _change_neighborhood_id(self):
        if self.neighborhood_id:
            self.district_id = self.neighborhood_id.district_id
        self.city = self.neighborhood_id.name
