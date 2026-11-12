# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ, RATES_STATUSES, UPDATE_HOURS


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
    l10n_cr_update_time = fields.Selection(
        selection=[(str(hour), f'{hour}:00') for hour in UPDATE_HOURS],
        string='Update Time',
        help="Costa Rica time. One scheduled action updates every company at this time.",
        compute='_compute_l10n_cr_update_time',
        readonly=False,
        store=True,
    )
    l10n_cr_last_update_failed = fields.Boolean(related='company_id.root_id.l10n_cr_last_update_failed')
    l10n_cr_rates_status = fields.Selection(selection=RATES_STATUSES, compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_entered_manually = fields.Boolean(compute='_compute_l10n_cr_rates_status')
    l10n_cr_last_update = fields.Char(compute='_compute_l10n_cr_rates_status')
    l10n_cr_retry_at = fields.Char(compute='_compute_l10n_cr_rates_status')

    # From the form's currency and fiscal country, as they are saved together with the update switch
    @api.depends('currency_id', 'account_fiscal_country_id')
    def _compute_l10n_cr_rates_available(self):
        for settings in self:
            settings.l10n_cr_rates_available = bool(self.env['res.company']._l10n_cr_get_rated_currency_for(
                settings.account_fiscal_country_id, settings.currency_id))

    @api.onchange('currency_id', 'account_fiscal_country_id')
    def _onchange_l10n_cr_rates_available(self):
        # Otherwise saving would switch the update back on right after the company switched it off
        if not self.l10n_cr_rates_available:
            self.l10n_cr_update_rates = False

    @api.depends('company_id')
    def _compute_l10n_cr_update_time(self):
        cron = self.env['res.company']._l10n_cr_get_cron()
        hour = cron and self.env['res.company']._l10n_cr_get_update_hour(cron)
        for settings in self:
            settings.l10n_cr_update_time = hour in UPDATE_HOURS and str(hour)

    @api.depends('company_id', 'l10n_cr_last_update_failed')
    def _compute_l10n_cr_rates_status(self):
        for settings in self:
            status = settings.company_id.root_id._l10n_cr_get_rates_status()
            settings.l10n_cr_rates_status = status['status']
            settings.l10n_cr_rates_ready_until = status['ready_until']
            settings.l10n_cr_rates_entered_manually = status['entered_manually']
            settings.l10n_cr_last_update = status['last_update']
            settings.l10n_cr_retry_at = status['retry_at']

    @api.model_create_multi
    def create(self, vals_list):
        settings_list = super().create(vals_list)
        # Related fields are written on create, and only those that changed stay in the values
        for settings, vals in zip(settings_list, vals_list):
            changed_fields = {'l10n_cr_bccr_token', 'currency_id', 'account_fiscal_country_id'} & vals.keys()
            if (
                (vals.get('l10n_cr_update_rates') or changed_fields)
                and settings.l10n_cr_update_rates
                and settings.l10n_cr_bccr_token
                and settings.l10n_cr_rates_available
            ):
                settings.company_id.root_id._l10n_cr_update_rates()
        return settings_list

    def set_values(self):
        super().set_values()
        Company = self.env['res.company']
        cron = Company._l10n_cr_get_cron()
        hour = self.l10n_cr_update_time and int(self.l10n_cr_update_time)
        if cron and hour and hour != Company._l10n_cr_get_update_hour(cron):
            now = datetime.now(ZoneInfo(CR_TZ))
            next_update = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_update <= now:
                next_update += timedelta(days=1)
            cron.nextcall = next_update.astimezone(timezone.utc).replace(tzinfo=None)

    def action_l10n_cr_update_rates(self):
        return self.company_id.root_id._l10n_cr_action_update_rates()

    def action_l10n_cr_open_rate_load_wizard(self):
        return self.company_id.root_id._l10n_cr_action_open_rate_load_wizard()
