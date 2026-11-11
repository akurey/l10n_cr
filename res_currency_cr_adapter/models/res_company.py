# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.res_currency_cr_adapter.models.res_currency import CR_TZ, RATE_DATE_OFFSET
from odoo.addons.res_currency_cr_adapter.tools.bccr_api import TIMEOUT, BccrApi

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_cr_update_rates = fields.Boolean(string='Update Exchange Rates')
    l10n_cr_bccr_token = fields.Char(string='BCCR Token', groups='base.group_system')
    l10n_cr_last_update = fields.Datetime(string='Last Exchange Rate Update', readonly=True)
    l10n_cr_last_update_failed = fields.Boolean(string='Last Exchange Rate Update Failed', readonly=True)

    def _l10n_cr_get_rated_currency(self):
        """Currency the BCCR rates for this company: the dollar for a colón company, the colón for a dollar one."""
        self.ensure_one()
        Currency = self.env['res.currency']
        if self.account_fiscal_country_id.code != 'CR':
            return Currency
        return {'CRC': self.env.ref('base.USD'), 'USD': self.env.ref('base.CRC')}.get(self.currency_id.name, Currency)

    def _l10n_cr_get_rates_ready_until(self):
        """Last date whose documents have a rate of the currency the BCCR rates, or False without any."""
        self.ensure_one()
        last_rate = self.env['res.currency.rate'].search([
            ('company_id', 'in', [False, self.id]),
            ('currency_id', '=', self._l10n_cr_get_rated_currency().id),
        ], order='name desc', limit=1)
        return last_rate and last_rate.name + RATE_DATE_OFFSET

    def _l10n_cr_get_first_missing_date(self, today):
        """First date whose rate is missing, from the end of the company's rates and at most today."""
        ready_until = self._l10n_cr_get_rates_ready_until()
        return min(ready_until + timedelta(days=1), today) if ready_until else today

    def _l10n_cr_update_rates(self, first_date=False, last_date=False, timeout=TIMEOUT, replace=True):
        """Load the BCCR rates from first_date to last_date for these root companies.

        By default each company catches up from its first missing rate, or today without any, to tomorrow.
        Without replace, rates the companies already have in the range are left as they are.

        :return: {company: error} of the companies whose update failed
        """
        # By default up to tomorrow's rate, which the BCCR publishes in the evening
        today = fields.Date.context_today(self.with_context(tz=CR_TZ))
        last_date = last_date or today + timedelta(days=1)
        first_dates = {company: first_date or company._l10n_cr_get_first_missing_date(today) for company in self}

        errors = {}
        # The rates are the same for every token, so companies sharing one share the request
        for token, token_companies in self.grouped('l10n_cr_bccr_token').items():
            # Odoo deactivates a cron after repeated failures, so a BCCR outage is only logged
            try:
                rates = BccrApi(self.env, token, timeout).get_rates(
                    min(first_dates[company] for company in token_companies), last_date)
            except UserError as e:
                _logger.error("Exchange rate update failed for %s: %s", ', '.join(token_companies.mapped('name')), e)
                token_companies.l10n_cr_last_update_failed = True
                errors.update(dict.fromkeys(token_companies, str(e)))
                continue
            # Each company only gets its own missing days, so rates it already has are left alone
            for company in token_companies:
                company_rates = {date: rate for date, rate in rates.items() if date >= first_dates[company]}
                self.env['res.currency.rate']._l10n_cr_store_rates(company, company_rates, replace)
        return errors
