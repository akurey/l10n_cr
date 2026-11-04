from odoo import api, fields, models


class FormatAddressMixin(models.AbstractModel):
    _inherit = 'format.address.mixin'

    # Placeholders of the address form: Costa Rican wording (otras señas, province) for Costa Rica, Odoo's for
    # other countries.
    # TODO: return False for other countries once https://github.com/odoo/odoo/issues/300493 is fixed:
    # placeholder_field lost its fallback to the static placeholder in 20.0. Then drop "Street..." and
    # "State" from the .po files too.
    l10n_cr_street_placeholder = fields.Char(compute='_compute_l10n_cr_address_placeholders')
    l10n_cr_state_placeholder = fields.Char(compute='_compute_l10n_cr_address_placeholders')

    @api.depends('country_id')
    @api.depends_context('lang')
    def _compute_l10n_cr_address_placeholders(self):
        for record in self:
            is_cr = record.country_id.code == 'CR'
            record.l10n_cr_street_placeholder = self.env._("Directions...") if is_cr else self.env._("Street...")
            record.l10n_cr_state_placeholder = self.env._("Province") if is_cr else self.env._("State")

    def _view_get_address(self, arch):
        if self.env.company.country_id.code == 'CR':
            # The views already have the Costa Rican order (province, canton, district, barrio, zip; city/state/zip
            # for other countries): skip Odoo's reordering after the address format, which would break it.
            return super(FormatAddressMixin, self.with_context(no_address_format=True))._view_get_address(arch)
        arch = super()._view_get_address(arch)
        # Other countries' formats can move the province: keep canton, district and barrio right after it.
        for address_node in arch.xpath("//div[hasclass('o_address_format')]"):
            previous_field = address_node.find(".//field[@name='state_id']")
            for fname in ('county_id', 'district_id', 'neighborhood_id'):
                field = address_node.find(f".//field[@name='{fname}']")
                if previous_field is not None and field is not None:
                    previous_field.addnext(field)
                    previous_field = field
        return arch
