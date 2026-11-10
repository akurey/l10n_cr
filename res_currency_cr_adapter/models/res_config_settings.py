# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_cr_update_rates = fields.Boolean(related='company_id.l10n_cr_update_rates', readonly=False)
    l10n_cr_bccr_token = fields.Char(
        related='company_id.l10n_cr_bccr_token',
        readonly=False,
        groups='base.group_system',
    )
