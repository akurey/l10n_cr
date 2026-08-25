
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    expense_product_id = fields.Many2one(
        'product.product',
        company_dependent=True,
        string="Default product for expenses when loading data from XML",
        help="The default product used when loading Costa Rican digital invoice")

    expense_account_id = fields.Many2one(
        'account.account',
        company_dependent=True,
        string="Default Expense Account when loading data from XML",
        help="The expense account used when loading Costa Rican digital invoice")

    expense_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        company_dependent=True,
        string="Default Analytic Account for expenses when loading data from XML",
        help="The analytic account used when loading Costa Rican digital invoice")

    # 19-port migration: this field's own consuming code (account_move.py,
    # api_facturae.py) reads its value via
    # self.env['ir.config_parameter'].sudo().get_param('load_lines') - a
    # global setting, not the company-scoped field-access pattern
    # company_dependent=True implies. Confirmed via real production data:
    # ir_model_fields never had company_dependent=True for this field before
    # (checked pre-19.0 state), and there's no ir.property history for it
    # either - company_dependent=True is a declaration/consumption mismatch
    # in this checkout, not an intentional feature. Removed to match actual
    # usage and keep the existing boolean column (Postgres can't auto-cast
    # boolean to the jsonb type company_dependent=True requires in 19.0).
    load_lines = fields.Boolean(
        string='Indicates if invoice lines should be load when loading a Costa Rican Digital Invoice',
        default=True
    )
