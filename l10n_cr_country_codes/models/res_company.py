# copyright 2018 Carlos Wong, Akurey SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    state_id = fields.Many2one(string="Province")
    county_id = fields.Many2one(
        "res.country.county", string="Canton", domain="[('state_id', '=?', state_id)]",
        compute='_compute_address', inverse='_inverse_county')
    district_id = fields.Many2one(
        "res.country.district", string="District",
        domain="[('county_id', '=?', county_id), ('county_id.state_id', '=?', state_id)]",
        compute='_compute_address', inverse='_inverse_district')
    neighborhood_id = fields.Many2one(
        "res.country.neighborhood", string="Neighborhood",
        domain=(
            "[('district_id', '=?', district_id), ('district_id.county_id', '=?', county_id),"
            " ('district_id.county_id.state_id', '=?', state_id)]"),
        compute='_compute_address', inverse='_inverse_neighborhood')

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

    def _get_company_address_field_names(self):
        return super()._get_company_address_field_names() + ['county_id', 'district_id', 'neighborhood_id']

    def _inverse_county(self):
        for company in self:
            company.partner_id.county_id = company.county_id

    def _inverse_district(self):
        for company in self:
            company.partner_id.district_id = company.district_id

    def _inverse_neighborhood(self):
        for company in self:
            company.partner_id.neighborhood_id = company.neighborhood_id
