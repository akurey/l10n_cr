from odoo import models, fields, api, _
from odoo.tools import float_round
from odoo.exceptions import UserError


class IvaCodeType(models.Model):
    _inherit = "account.tax"

    tax_code = fields.Char(string="Tax Code")
    iva_tax_desc = fields.Char(string="VAT Tax Rate", default='N/A')
    iva_tax_code = fields.Char(string="VAT Rate Code", default='N/A')
    has_exoneration = fields.Boolean(string="Has Exoneration")
    # Points of the parent tax that are exonerated (13 = all of a 13 % IVA, 6.5 = half of it)
    percentage_exoneration = fields.Float(string="Percentage of VAT Exoneration", digits=(16, 2))
    tax_root = fields.Many2one("account.tax", string="Parent Tax")
    non_tax_deductible = fields.Boolean(string='Indicates if this tax is no deductible for Rent and VAT',)

    @api.onchange('percentage_exoneration')
    def _onchange_percentage_exoneration(self):
        self.tax_compute_exoneration()

    @api.onchange('tax_root')
    def _onchange_tax_root(self):
        self.tax_compute_exoneration()

    def _cr_exoneration_tax(self, percentage, fiscal_position=False):
        """The exonerated version of this sale IVA for a customer whose authorization exonerates `percentage` % of it:
        found, or created once (tied to the fiscal position so that it is offered only there)."""
        self.ensure_one()
        points = float_round(self.amount * percentage / 100, 2)
        # sudo: a salesperson invoicing an exonerated customer may not manage taxes; only this IVA's copy is made
        taxes = self.env['account.tax'].sudo()
        tax = taxes.search([('has_exoneration', '=', True), ('tax_root', '=', self.id),
                            ('percentage_exoneration', '=', points), ('type_tax_use', '=', 'sale'),
                            ('company_id', '=', self.company_id.id)], limit=1)
        if not tax:
            tax = self.sudo().copy({
                'name': _('%(tax)s (%(percentage)s%% exonerated)', tax=self.name, percentage=f'{percentage:g}'),
                'invoice_label': False,
                'description': False, 'amount': self.amount - points, 'has_exoneration': True,
                'tax_root': self.id, 'percentage_exoneration': points,
                'fiscal_position_ids': [fields.Command.set(fiscal_position.ids)] if fiscal_position else False,
            })
        elif fiscal_position and tax.fiscal_position_ids and fiscal_position not in tax.fiscal_position_ids:
            tax.fiscal_position_ids = [fields.Command.link(fiscal_position.id)]
        return tax.sudo(False)

    def _cr_exonerated_for(self, partner, cabys, fiscal_position=False):
        """These taxes of a sale line for an exonerated customer: the IVA becomes its exonerated version for the
        customer's percentage when the line's CABYS is in the customer's authorization, and stays the full IVA
        otherwise (also when the customer has no authorized CABYS yet). Other taxes are kept."""
        authorized = cabys and 0 < partner.percentage_exoneration <= 100 and cabys in partner._cr_exoneration_cabys()
        result = self.browse()
        for tax in self:
            iva = tax.tax_root if tax.has_exoneration else tax
            if iva.tax_code != '01' or iva.type_tax_use != 'sale' or not iva.amount:
                result |= tax
            elif authorized:
                result |= iva._cr_exoneration_tax(partner.percentage_exoneration, fiscal_position)
            else:
                result |= iva
        return result

    def tax_compute_exoneration(self):
        if self.percentage_exoneration <= 13:
            if self.tax_root:
                self.amount = self.tax_root.amount - self.percentage_exoneration
        else:
            raise UserError(_('El porcentaje no puede ser mayor a 13'))
