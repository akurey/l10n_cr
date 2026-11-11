# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ


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
    l10n_cr_last_update = fields.Datetime(compute='_compute_l10n_cr_last_update')
    l10n_cr_last_update_failed = fields.Boolean(related='company_id.root_id.l10n_cr_last_update_failed')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_status = fields.Selection(
        selection=[('error', 'Failed'), ('ready', 'Ready'), ('today', 'Ready for today'), ('missing', 'Missing')],
        compute='_compute_l10n_cr_rates_status',
    )

    @api.depends('company_id')
    def _compute_l10n_cr_rates_available(self):
        for settings in self:
            settings.l10n_cr_rates_available = bool(settings.company_id.root_id._l10n_cr_get_rated_currency())

    @api.depends('company_id', 'l10n_cr_last_update_failed')
    def _compute_l10n_cr_rates_status(self):
        today = fields.Date.context_today(self.with_context(tz=CR_TZ))
        for settings in self:
            ready_until = settings.company_id.root_id._l10n_cr_get_rates_ready_until()
            settings.l10n_cr_rates_ready_until = ready_until
            if settings.l10n_cr_last_update_failed:
                settings.l10n_cr_rates_status = 'error'
            elif ready_until and ready_until > today:
                settings.l10n_cr_rates_status = 'ready'
            elif ready_until == today:
                settings.l10n_cr_rates_status = 'today'
            else:
                settings.l10n_cr_rates_status = 'missing'

    def _compute_l10n_cr_last_update(self):
        cron = self.env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        self.l10n_cr_last_update = cron and cron.sudo().lastcall
