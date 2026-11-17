# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.res_currency_cr_adapter.models.res_currency import RATES_STATUSES


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_cr_rates_available = fields.Boolean(compute='_compute_l10n_cr_rates_available')
    # The update runs on the root company, so a branch shows and edits its root's settings
    l10n_cr_update_rates = fields.Boolean(related='company_id.root_id.l10n_cr_update_rates', readonly=False)
    l10n_cr_bccr_token = fields.Char(config_parameter='res_currency_cr_adapter.bccr_token')
    l10n_cr_rates_status = fields.Selection(selection=RATES_STATUSES, compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
    l10n_cr_last_update = fields.Char(compute='_compute_l10n_cr_rates_status')
    l10n_cr_last_update_error = fields.Char(compute='_compute_l10n_cr_rates_status')
    l10n_cr_next_update = fields.Char(compute='_compute_l10n_cr_rates_status')

    # From the form's currency and fiscal country, so the setting follows them before they are saved
    @api.depends('currency_id', 'account_fiscal_country_id')
    def _compute_l10n_cr_rates_available(self):
        for settings in self:
            settings.l10n_cr_rates_available = bool(self.env['res.company']._l10n_cr_get_rated_currency_for(
                settings.account_fiscal_country_id, settings.currency_id))

    @api.depends('company_id')
    def _compute_l10n_cr_rates_status(self):
        for settings in self:
            status = settings.company_id.root_id._l10n_cr_get_rates_status()
            settings.l10n_cr_rates_status = status['status']
            settings.l10n_cr_rates_ready_until = status['ready_until']
            settings.l10n_cr_last_update = status['last_update']
            settings.l10n_cr_last_update_error = status['last_update_error']
            settings.l10n_cr_next_update = status['next_update']

    def action_l10n_cr_update_rates(self):
        return self.company_id.root_id._l10n_cr_action_update_rates()

    def action_l10n_cr_open_rate_load_wizard(self):
        return self.company_id.root_id._l10n_cr_action_open_rate_load_wizard()
