from odoo import api, fields, models


# Many cantons, districts and barrios share their name. Dropdowns show where each one is (formatted_display_name,
# rendered as a muted second part); everywhere else the display name is the plain name.

class ResCountryCounty(models.Model):
    _name = "res.country.county"
    _description = "Costa Rica Canton"
    _order = 'name'

    code = fields.Char(required=True)
    state_id = fields.Many2one("res.country.state", string="Province", required=True)
    name = fields.Char(required=True)

    _code_uniq = models.Constraint(
        'unique (state_id, code)',
        "The canton code must be unique within its province.",
    )

    @api.depends('name', 'state_id.name')
    @api.depends_context('formatted_display_name')
    def _compute_display_name(self):
        for county in self:
            if self.env.context.get('formatted_display_name'):
                county.display_name = f"{county.name} \v--{county.state_id.name}--"
            else:
                county.display_name = county.name


class ResCountryDistrict(models.Model):
    _name = "res.country.district"
    _description = "Costa Rica District"
    _order = 'name'

    code = fields.Char(required=True)
    county_id = fields.Many2one("res.country.county", string="Canton", required=True)
    name = fields.Char(required=True)

    _code_uniq = models.Constraint(
        'unique (county_id, code)',
        "The district code must be unique within its canton.",
    )

    @api.depends('name', 'county_id.name', 'county_id.state_id.name')
    @api.depends_context('formatted_display_name')
    def _compute_display_name(self):
        for district in self:
            if self.env.context.get('formatted_display_name'):
                county = district.county_id
                district.display_name = f"{district.name} \v--{county.name}, {county.state_id.name}--"
            else:
                district.display_name = district.name


class ResCountryNeighborhood(models.Model):
    _name = "res.country.neighborhood"
    _description = "Costa Rica Barrio"
    _order = 'name'

    code = fields.Char(required=True)
    district_id = fields.Many2one("res.country.district", string="District", required=True)
    name = fields.Char(required=True)

    _code_uniq = models.Constraint(
        'unique (district_id, code)',
        "The barrio code must be unique within its district.",
    )

    @api.depends('name', 'code', 'district_id.name', 'district_id.county_id.name')
    @api.depends_context('formatted_display_name')
    def _compute_display_name(self):
        for neighborhood in self:
            if self.env.context.get('formatted_display_name'):
                district = neighborhood.district_id
                neighborhood.display_name = (
                    f"{neighborhood.name} \v--{district.name}, {district.county_id.name} · {neighborhood.code}--")
            else:
                neighborhood.display_name = neighborhood.name
