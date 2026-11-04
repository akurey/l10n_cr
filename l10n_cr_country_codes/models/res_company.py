# copyright 2018 Carlos Wong, Akurey SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    state_id = fields.Many2one(string="Province")
    county_id = fields.Many2one(
        "res.country.county", string="Canton", domain="[('state_id', '=', state_id)]",
        compute='_compute_address', inverse='_inverse_county')
    district_id = fields.Many2one(
        "res.country.district", string="District", domain="[('county_id', '=', county_id)]",
        compute='_compute_address', inverse='_inverse_district')
    neighborhood_id = fields.Many2one(
        "res.country.neighborhood", string="Neighborhood", domain="[('district_id', '=', district_id)]",
        compute='_compute_address', inverse='_inverse_neighborhood')

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
