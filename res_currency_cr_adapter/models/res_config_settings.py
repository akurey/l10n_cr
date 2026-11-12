# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.tools import format_date

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ, RATE_DATE_OFFSET

# The BCCR publishes tomorrow's rate around 17:30, so the update runs in the evening
UPDATE_HOURS = range(18, 24)
# Seconds the BCCR has to answer while the user waits in Settings
TIMEOUT = 5


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
    l10n_cr_last_update = fields.Char(compute='_compute_l10n_cr_last_update')
    l10n_cr_last_update_failed = fields.Boolean(related='company_id.root_id.l10n_cr_last_update_failed')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_entered_manually = fields.Boolean(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_status = fields.Selection(
        selection=[
            ('error', 'Failed'),
            ('ready', 'Ready'),
            ('late', 'Tomorrow missing'),
            ('today', 'Ready for today'),
            ('missing', 'Missing'),
        ],
        compute='_compute_l10n_cr_rates_status',
    )

    @api.depends('company_id')
    def _compute_l10n_cr_rates_available(self):
        for settings in self:
            settings.l10n_cr_rates_available = bool(settings.company_id.root_id._l10n_cr_get_rated_currency())

    @api.depends('company_id')
    def _compute_l10n_cr_last_update(self):
        for settings in self:
            last_update = settings.company_id.root_id.l10n_cr_last_update
            settings.l10n_cr_last_update = last_update and settings._l10n_cr_format_last_update(last_update)

    @api.depends('company_id')
    def _compute_l10n_cr_update_time(self):
        cron = self._l10n_cr_get_cron()
        hour = cron and self._l10n_cr_get_update_hour(cron)
        for settings in self:
            settings.l10n_cr_update_time = hour in UPDATE_HOURS and str(hour)

    @api.depends('company_id', 'l10n_cr_last_update_failed')
    def _compute_l10n_cr_rates_status(self):
        now = datetime.now(ZoneInfo(CR_TZ))
        today = now.date()
        cron = self._l10n_cr_get_cron()
        hour = cron and self._l10n_cr_get_update_hour(cron)
        updated_today = hour in UPDATE_HOURS and now.hour >= hour
        for settings in self:
            last_rate = settings.company_id.root_id._l10n_cr_get_last_rate()
            ready_until = last_rate and last_rate.name + RATE_DATE_OFFSET
            settings.l10n_cr_rates_ready_until = ready_until
            settings.l10n_cr_rates_entered_manually = last_rate.l10n_cr_source == 'manual'
            if settings.l10n_cr_last_update_failed:
                settings.l10n_cr_rates_status = 'error'
            elif ready_until and ready_until > today:
                settings.l10n_cr_rates_status = 'ready'
            elif ready_until == today:
                settings.l10n_cr_rates_status = 'late' if updated_today else 'today'
            else:
                settings.l10n_cr_rates_status = 'missing'

    @api.model_create_multi
    def create(self, vals_list):
        settings_list = super().create(vals_list)
        # Related fields are written on create, and only those that changed stay in the values
        for settings, vals in zip(settings_list, vals_list):
            if (
                (vals.get('l10n_cr_update_rates') or 'l10n_cr_bccr_token' in vals)
                and settings.l10n_cr_update_rates
                and settings.l10n_cr_bccr_token
                and settings.l10n_cr_rates_available
            ):
                settings.company_id.root_id._l10n_cr_update_rates(timeout=TIMEOUT)
        return settings_list

    def set_values(self):
        super().set_values()
        cron = self._l10n_cr_get_cron()
        hour = self.l10n_cr_update_time and int(self.l10n_cr_update_time)
        if cron and hour and hour != self._l10n_cr_get_update_hour(cron):
            now = datetime.now(ZoneInfo(CR_TZ))
            next_update = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_update <= now:
                next_update += timedelta(days=1)
            cron.nextcall = next_update.astimezone(timezone.utc).replace(tzinfo=None)

    def action_l10n_cr_update_rates(self):
        company = self.company_id.root_id
        error = company._l10n_cr_update_rates(timeout=TIMEOUT).get(company)
        if error:
            notification = {'type': 'danger', 'message': error}
        else:
            notification = {
                'type': 'success',
                'message': self.env._(
                    "Exchange rates loaded up to %(date)s",
                    date=format_date(self.env, company._l10n_cr_get_rates_ready_until())),
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {**notification, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def action_l10n_cr_open_rate_load_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Load Past Exchange Rates"),
            'res_model': 'l10n_cr.rate.load.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_company_id': self.company_id.root_id.id, 'dialog_size': 'medium'},
        }

    def _l10n_cr_get_cron(self):
        cron = self.env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        return cron and cron.sudo()

    def _l10n_cr_format_last_update(self, last_update):
        """Describe a past UTC datetime in Costa Rica time, relative to today when recent."""
        last_update = last_update.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ))
        time = last_update.strftime('%H:%M')
        days = (datetime.now(ZoneInfo(CR_TZ)).date() - last_update.date()).days
        if days == 0:
            return self.env._("today at %(time)s", time=time)
        if days == 1:
            return self.env._("yesterday at %(time)s", time=time)
        return self.env._("on %(date)s at %(time)s", date=last_update.strftime('%d/%m'), time=time)

    def _l10n_cr_get_update_hour(self, cron):
        """Hour of the day, in Costa Rica, at which the scheduled action runs."""
        return cron.nextcall.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ)).hour
