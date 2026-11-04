from odoo import models


class FormatAddressMixin(models.AbstractModel):
    _inherit = 'format.address.mixin'

    def _view_get_address(self, arch):
        arch = super()._view_get_address(arch)
        # Odoo reorders city/state/zip after the company country's address_format, which moves the zip
        # between the province and the canton: keep canton, district and barrio right after the province.
        cr_company = self.env.company.country_id.code == 'CR'
        for address_node in arch.xpath("//div[hasclass('o_address_format')]"):
            state_field = address_node.find(".//field[@name='state_id']")
            if state_field is None:
                continue
            previous_field = state_field
            for fname in ('county_id', 'district_id', 'neighborhood_id'):
                field = address_node.find(f".//field[@name='{fname}']")
                if field is not None:
                    previous_field.addnext(field)
                    previous_field = field
            if cr_company:
                # Costa Rica's format puts the province before the city (barrio, hidden for Costa Rica):
                # keep city/state/zip for other countries, and the zip after the barrio.
                city_field = address_node.find(".//field[@name='city']")
                if city_field is not None:
                    state_field.addprevious(city_field)
                zip_field = address_node.find(".//field[@name='zip']")
                if zip_field is not None:
                    previous_field.addnext(zip_field)
        return arch
