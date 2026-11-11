# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ

# The BCCR publishes tomorrow's rate around 17:30, so the update runs in the evening
UPDATE_HOURS = range(18, 24)


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
    l10n_cr_next_update = fields.Char(compute='_compute_l10n_cr_next_update')
    l10n_cr_last_update_failed = fields.Boolean(related='company_id.root_id.l10n_cr_last_update_failed')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
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

    def _compute_l10n_cr_next_update(self):
        cron = self._l10n_cr_get_cron()
        next_update = cron and cron.nextcall.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ))
        today = datetime.now(ZoneInfo(CR_TZ)).date()
        if not next_update:
            text = False
        elif next_update.date() == today:
            text = self.env._("today at %(time)s", time=next_update.strftime('%H:%M'))
        elif next_update.date() == today + timedelta(days=1):
            text = self.env._("tomorrow at %(time)s", time=next_update.strftime('%H:%M'))
        else:
            text = self.env._(
                "on %(date)s at %(time)s", date=next_update.strftime('%d/%m'), time=next_update.strftime('%H:%M'))
        self.l10n_cr_next_update = text

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
            ready_until = settings.company_id.root_id._l10n_cr_get_rates_ready_until()
            settings.l10n_cr_rates_ready_until = ready_until
            if settings.l10n_cr_last_update_failed:
                settings.l10n_cr_rates_status = 'error'
            elif ready_until and ready_until > today:
                settings.l10n_cr_rates_status = 'ready'
            elif ready_until == today:
                settings.l10n_cr_rates_status = 'late' if updated_today else 'today'
            else:
                settings.l10n_cr_rates_status = 'missing'

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

    def _l10n_cr_get_cron(self):
        cron = self.env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        return cron and cron.sudo()

    def _l10n_cr_get_update_hour(self, cron):
        """Hour of the day, in Costa Rica, at which the scheduled action runs."""
        return cron.nextcall.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ)).hour
