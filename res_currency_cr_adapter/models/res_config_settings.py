# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_cr_rates_available = fields.Boolean(compute='_compute_l10n_cr_rates_available')
    # The update runs on the root company, so a branch shows and edits its root's settings
    l10n_cr_update_rates = fields.Boolean(related='company_id.root_id.l10n_cr_update_rates', readonly=False)
    l10n_cr_bccr_token = fields.Char(
        related='company_id.root_id.l10n_cr_bccr_token',
        readonly=False,
        groups='base.group_system',
    )
    l10n_cr_last_rate_date = fields.Date(related='company_id.root_id.l10n_cr_last_rate_date')

    @api.depends('company_id')
    def _compute_l10n_cr_rates_available(self):
        for settings in self:
            settings.l10n_cr_rates_available = bool(settings.company_id.root_id._l10n_cr_get_rated_currency())
