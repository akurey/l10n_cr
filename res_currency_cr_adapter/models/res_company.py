# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ, UPDATE_TIME
from odoo.addons.res_currency_cr_adapter.tools.bccr_api import BccrApi

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_cr_update_rates = fields.Boolean(string='Update Exchange Rates')
    # The scheduled update's last run, as {'date': UTC datetime, 'error': message or False}
    l10n_cr_last_scheduled_update = fields.Json(readonly=True)

    @api.model
    def _l10n_cr_get_rated_currency_for(self, fiscal_country, currency):
        """Currency the BCCR rates for a company of that fiscal country and currency, or an empty recordset."""
        if fiscal_country.code != 'CR' or currency.name not in ('CRC', 'USD'):
            return self.env['res.currency']
        return self.env.ref('base.USD' if currency.name == 'CRC' else 'base.CRC')

    def _l10n_cr_get_rated_currency(self):
        """Currency the BCCR rates for this company: the dollar for a colón company, the colón for a dollar one."""
        self.ensure_one()
        return self._l10n_cr_get_rated_currency_for(self.account_fiscal_country_id, self.currency_id)

    def _l10n_cr_get_rates_ready_until(self):
        """Last date whose documents have a rate of the currency the BCCR rates, or False without any.

        The company's own rates come first and else the shared ones.
        """
        self.ensure_one()
        return self.env['res.currency.rate'].search([
            ('company_id', 'in', [False, self.id]),
            ('currency_id', '=', self._l10n_cr_get_rated_currency().id),
        ], order='company_id.id, name desc', limit=1).l10n_cr_date

    def _l10n_cr_get_first_missing_date(self, today):
        """First date whose rate is missing, from the end of the company's rates and at most today."""
        ready_until = self._l10n_cr_get_rates_ready_until()
        return min(ready_until + timedelta(days=1), today) if ready_until else today

    @api.model
    def _l10n_cr_get_bccr_token(self):
        return self.env['ir.config_parameter'].sudo().get_str('res_currency_cr_adapter.bccr_token')

    def _l10n_cr_update_rates(self, first_date=False, last_date=False, replace=False):
        """Load the BCCR rates from first_date to last_date for these root companies, in a single request.

        By default each company catches up from its first missing rate, or today without any, to tomorrow's rate,
        which the BCCR publishes in the evening. Each company only stores the dates from its own start date, so the
        rates it already has are left alone, and rates entered manually are only overwritten with replace.

        :return: the error message if the update failed, else False; it isn't raised, since Odoo deactivates a cron
            after repeated failures
        """
        if not self:
            return False
        today = datetime.now(ZoneInfo(CR_TZ)).date()
        last_date = last_date or today + timedelta(days=1)
        start_dates = {company: first_date or company._l10n_cr_get_first_missing_date(today) for company in self}

        try:
            rates = BccrApi(self.env, self._l10n_cr_get_bccr_token()).get_rates(min(start_dates.values()), last_date)
        except UserError as e:
            _logger.warning("Exchange rate update failed for %s: %s", ', '.join(self.mapped('name')), e)
            return str(e)
        for company, start_date in start_dates.items():
            company_rates = {date: rate for date, rate in rates.items() if date >= start_date}
            self.env['res.currency.rate']._l10n_cr_store_rates(company, company_rates, replace)
        return False

    @api.model
    def _l10n_cr_is_missing_rates(self, ready_until, now):
        """Whether rates ready until that date lack the latest one due at that Costa Rica time: tomorrow's from the
        evening, else today's."""
        due_date = now.date() + timedelta(days=1) if now.time() >= UPDATE_TIME else now.date()
        return not ready_until or ready_until < due_date

    @api.model
    def _cron_l10n_cr_update_rates(self):
        """Load the due BCCR rates of each company that updates them and is missing any.

        It runs every hour and does nothing while no rate is missing, so a failed or late update is retried within
        the hour, and tomorrow's rate has the evening to load before the first documents of its day.
        """
        if not self._l10n_cr_get_bccr_token():
            return
        now = datetime.now(ZoneInfo(CR_TZ))
        companies = self.sudo().search([
            ('parent_id', '=', False),
            ('l10n_cr_update_rates', '=', True),
        ]).filtered(lambda company: company._l10n_cr_get_rated_currency()
                    and self._l10n_cr_is_missing_rates(company._l10n_cr_get_rates_ready_until(), now))

        error = companies._l10n_cr_update_rates()
        run_date = fields.Datetime.to_string(now.astimezone(timezone.utc))
        companies.l10n_cr_last_scheduled_update = {'date': run_date, 'error': error}

    def _l10n_cr_get_rates_status(self):
        """Status of the company's update, shown in the BCCR setting and on the rated currency.

        :return: dict with the status ('ready', 'late' or 'missing'), the date the rates are ready until, when the
            scheduled update last ran, as text, with its error, and when it runs next, as text
        """
        self.ensure_one()
        now = datetime.now(ZoneInfo(CR_TZ))
        ready_until = self._l10n_cr_get_rates_ready_until()
        if not self._l10n_cr_is_missing_rates(ready_until, now):
            status = 'ready'
        elif ready_until == now.date():
            status = 'late'
        else:
            status = 'missing'
        next_run = False
        cron = self.sudo().env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        if cron and cron.active and self.l10n_cr_update_rates and self._l10n_cr_get_bccr_token():
            next_run = cron.nextcall
            if status == 'ready':
                # The hourly runs skip the company until its next rate is due
                due_at = datetime.combine(ready_until, UPDATE_TIME, now.tzinfo).astimezone(timezone.utc)
                next_run = max(next_run, due_at.replace(tzinfo=None))
        last_run = self.l10n_cr_last_scheduled_update
        return {
            'status': status,
            'ready_until': ready_until,
            'last_update': last_run and self._l10n_cr_format_datetime(fields.Datetime.to_datetime(last_run['date'])),
            'last_update_error': last_run and last_run['error'] or False,
            'next_update': next_run and self._l10n_cr_format_datetime(next_run),
        }

    def _l10n_cr_action_update_rates(self):
        """Load the company's missing rates and notify the result, then reload the view."""
        self.ensure_one()
        error = self._l10n_cr_update_rates()
        if error:
            notification = {'type': 'danger', 'message': error}
        else:
            notification = {
                'type': 'success',
                'message': self.env._(
                    "Exchange rates loaded up to %(date)s",
                    date=format_date(self.env, self._l10n_cr_get_rates_ready_until())),
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {**notification, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }

    def _l10n_cr_action_open_rate_load_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Load Past Exchange Rates"),
            'res_model': 'l10n_cr.rate.load.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_company_id': self.id, 'dialog_size': 'medium'},
        }

    @api.model
    def _l10n_cr_to_cr_time(self, utc_datetime):
        return utc_datetime.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ))

    @api.model
    def _l10n_cr_format_datetime(self, utc_datetime):
        """Describe a UTC datetime in Costa Rica time, relative to today when near."""
        cr_datetime = self._l10n_cr_to_cr_time(utc_datetime)
        time = cr_datetime.strftime('%H:%M')
        days = (cr_datetime.date() - datetime.now(ZoneInfo(CR_TZ)).date()).days
        if days == 0:
            return self.env._("today at %(time)s", time=time)
        if days == -1:
            return self.env._("yesterday at %(time)s", time=time)
        if days == 1:
            return self.env._("tomorrow at %(time)s", time=time)
        return self.env._("on %(date)s at %(time)s", date=format_date(self.env, cr_datetime.date()), time=time)
