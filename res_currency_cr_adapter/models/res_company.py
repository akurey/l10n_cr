# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ, RATE_DATE_OFFSET, UPDATE_TIME
from odoo.addons.res_currency_cr_adapter.tools.bccr_api import BccrApi

_logger = logging.getLogger(__name__)

# A failed or early update is retried every hour until the working day starts, in Costa Rica
RETRY_INTERVAL = timedelta(hours=1)
RETRY_UNTIL = time(6)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_cr_update_rates = fields.Boolean(string='Update Exchange Rates')
    l10n_cr_last_update = fields.Datetime(string='Last Exchange Rate Update', readonly=True)
    l10n_cr_last_update_failed = fields.Boolean(string='Last Exchange Rate Update Failed', readonly=True)

    def write(self, vals):
        if not {'currency_id', 'account_fiscal_country_id', 'country_id'} & vals.keys():
            return super().write(vals)
        rated_currencies = {company: company._l10n_cr_get_rated_currency() for company in self}
        res = super().write(vals)
        for company in self:
            former_currency = rated_currencies[company]
            rated_currency = company._l10n_cr_get_rated_currency()
            if rated_currency == former_currency:
                continue
            # Odoo divides every rate by the company currency's, so the BCCR's rates of the former currency would
            # distort the conversions; rates entered manually are left to the user
            if former_currency:
                self.env['res.currency.rate'].sudo().search([
                    ('company_id', '=', company.id),
                    ('currency_id', '=', former_currency.id),
                    ('l10n_cr_source', '=', 'bccr'),
                ]).unlink()
            if not rated_currency and company.l10n_cr_update_rates:
                company.l10n_cr_update_rates = False
        return res

    @api.model
    def _l10n_cr_get_rated_currency_for(self, fiscal_country, currency):
        """Currency the BCCR rates for a company of that fiscal country and currency, or an empty recordset."""
        Currency = self.env['res.currency']
        if fiscal_country.code != 'CR':
            return Currency
        return {'CRC': self.env.ref('base.USD'), 'USD': self.env.ref('base.CRC')}.get(currency.name, Currency)

    def _l10n_cr_get_rated_currency(self):
        """Currency the BCCR rates for this company: the dollar for a colón company, the colón for a dollar one."""
        self.ensure_one()
        return self._l10n_cr_get_rated_currency_for(self.account_fiscal_country_id, self.currency_id)

    def _l10n_cr_get_last_rate(self):
        """Latest rate of the currency the BCCR rates, the company's own or shared."""
        self.ensure_one()
        return self.env['res.currency.rate'].search([
            ('company_id', 'in', [False, self.id]),
            ('currency_id', '=', self._l10n_cr_get_rated_currency().id),
        ], order='name desc', limit=1)

    def _l10n_cr_get_rates_ready_until(self):
        """Last date whose documents have a rate of the currency the BCCR rates, or False without any."""
        last_rate = self._l10n_cr_get_last_rate()
        return last_rate.name + RATE_DATE_OFFSET if last_rate else False

    def _l10n_cr_get_first_missing_date(self, today):
        """First date whose rate is missing, from the end of the company's rates and at most today."""
        ready_until = self._l10n_cr_get_rates_ready_until()
        return min(ready_until + timedelta(days=1), today) if ready_until else today

    @api.model
    def _l10n_cr_get_bccr_token(self):
        return self.env['ir.config_parameter'].sudo().get_str('bccr_token')

    def _l10n_cr_update_rates(self, first_date=False, last_date=False, replace=False):
        """Load the BCCR rates from first_date to last_date for these root companies, in a single request.

        By default each company catches up from its first missing rate, or today without any, to tomorrow.
        Rates entered manually are only overwritten with replace.

        :return: {company: error} of the companies whose update failed
        """
        # By default up to tomorrow's rate, which the BCCR publishes in the evening
        today = fields.Date.context_today(self.with_context(tz=CR_TZ))
        last_date = last_date or today + timedelta(days=1)
        first_dates = {company: first_date or company._l10n_cr_get_first_missing_date(today) for company in self}

        # Odoo deactivates a cron after repeated failures, so a BCCR outage is only logged
        try:
            rates = BccrApi(self.env, self._l10n_cr_get_bccr_token()).get_rates(min(first_dates.values()), last_date)
        except UserError as e:
            _logger.error("Exchange rate update failed for %s: %s", ', '.join(self.mapped('name')), e)
            self.l10n_cr_last_update_failed = True
            return dict.fromkeys(self, str(e))
        # Each company only gets its own missing days, so rates it already has are left alone
        for company in self:
            company_rates = {date: rate for date, rate in rates.items() if date >= first_dates[company]}
            self.env['res.currency.rate']._l10n_cr_store_rates(company, company_rates, replace)
        return {}

    @api.model
    def _cron_l10n_cr_update_rates(self):
        """Load the missing BCCR rates of each company that updates them, retrying every hour while any is still
        missing, until the morning."""
        companies = self.sudo().search([
            ('parent_id', '=', False),
            ('l10n_cr_update_rates', '=', True),
        ]).filtered(lambda company: company._l10n_cr_get_rated_currency())
        if not companies or not companies._l10n_cr_get_bccr_token():
            _logger.info("No company updates its exchange rates from the BCCR")
            return

        now = datetime.now(ZoneInfo(CR_TZ))
        # The evening update is after tomorrow's rate, and its retries after midnight are still after that same day's
        target_date = now.date() + timedelta(days=1) if now.time() >= RETRY_UNTIL else now.date()

        def is_missing(company):
            ready_until = company._l10n_cr_get_rates_ready_until()
            return not ready_until or ready_until < target_date

        companies.filtered(is_missing)._l10n_cr_update_rates()
        missing_companies = companies.filtered(is_missing)
        retry_at = now + RETRY_INTERVAL
        cron = self._l10n_cr_get_cron()
        if missing_companies and cron and retry_at <= datetime.combine(target_date, RETRY_UNTIL, now.tzinfo):
            cron._trigger(retry_at.astimezone(timezone.utc).replace(tzinfo=None))
            _logger.info(
                "Exchange rates of %s still missing for %s, retrying at %s",
                ', '.join(missing_companies.mapped('name')), target_date, retry_at.strftime('%H:%M'))

    def _l10n_cr_get_rates_status(self):
        """Status of the company's update, shown in the BCCR setting and on the rated currency.

        :return: dict with the status ('error', 'ready', 'late', 'today' or 'missing'), the date the rates are ready
            until, whether the latest one was entered manually, and when the rates were last loaded and the next
            retry runs, as text
        """
        self.ensure_one()
        now = datetime.now(ZoneInfo(CR_TZ))
        today = now.date()
        cron = self._l10n_cr_get_cron()
        last_rate = self._l10n_cr_get_last_rate()
        ready_until = last_rate.name + RATE_DATE_OFFSET if last_rate else False
        if self.l10n_cr_last_update_failed:
            status = 'error'
        elif ready_until and ready_until > today:
            status = 'ready'
        elif ready_until == today:
            status = 'late' if now.time() >= UPDATE_TIME else 'today'
        else:
            status = 'missing'
        retry = cron and self.env['ir.cron.trigger'].sudo().search([
            ('cron_id', '=', cron.id),
            ('call_at', '>', fields.Datetime.now()),
        ], order='call_at', limit=1)
        return {
            'status': status,
            'ready_until': ready_until,
            'entered_manually': last_rate.l10n_cr_source == 'manual',
            'last_update': self.l10n_cr_last_update and self._l10n_cr_format_last_update(self.l10n_cr_last_update),
            'retry_at': self._l10n_cr_to_cr_time(retry.call_at).strftime('%H:%M') if retry else False,
        }

    def _l10n_cr_action_update_rates(self):
        """Load the company's missing rates and notify the result, then reload the view."""
        self.ensure_one()
        error = self._l10n_cr_update_rates().get(self)
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
    def _l10n_cr_get_cron(self):
        cron = self.env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        return cron and cron.sudo()

    @api.model
    def _l10n_cr_to_cr_time(self, utc_datetime):
        return utc_datetime.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(CR_TZ))

    @api.model
    def _l10n_cr_format_last_update(self, last_update):
        """Describe a past UTC datetime in Costa Rica time, relative to today when recent."""
        last_update = self._l10n_cr_to_cr_time(last_update)
        time = last_update.strftime('%H:%M')
        days = (datetime.now(ZoneInfo(CR_TZ)).date() - last_update.date()).days
        if days == 0:
            return self.env._("today at %(time)s", time=time)
        if days == 1:
            return self.env._("yesterday at %(time)s", time=time)
        return self.env._("on %(date)s at %(time)s", date=format_date(self.env, last_update.date()), time=time)
