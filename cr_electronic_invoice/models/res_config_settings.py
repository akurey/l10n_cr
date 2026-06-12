
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

    load_lines = fields.Boolean(
        string='Indicates if invoice lines should be load when loading a Costa Rican Digital Invoice',
        company_dependent=True,
        default=True
    )
