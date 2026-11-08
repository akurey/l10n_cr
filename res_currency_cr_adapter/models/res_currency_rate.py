# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.res_currency_cr_adapter.tools.bccr_api import BccrApi

_logger = logging.getLogger(__name__)

# Since 20.0 Odoo converts a document with the last rate dated before the
# document's own date, never with one from that same day (odoo/odoo@cba671d),
# so a rate is stored the day before the date the BCCR publishes it for
RATE_DATE_OFFSET = timedelta(days=1)


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    rate = fields.Float(string='Selling Rate')

    # Costa Rica uses two exchange rates:
    #   - Selling exchange rate - used when financial institutions sell USD to you (rate)
    #   - Buying exchange rate - used when financial institutions buy USD from you (rate_2)
    rate_2 = fields.Float(string='Buying Rate', digits=0,
                          help='The buying rate of the currency to the currency of rate 1.')

    # The rates as the BCCR publishes them, in colones per dollar
    original_rate = fields.Float(string='Selling Rate in Costa Rica', digits=(6, 2),
                                 help='The selling exchange rate from CRC to USD as sent by the BCCR')

    original_rate_2 = fields.Float(string='Buying Rate in Costa Rica', digits=(6, 2),
                                   help='The buying exchange rate from CRC to USD as sent by the BCCR')

    @api.model
    def _cron_update(self, first_date=False, last_date=False):
        """Load the BCCR rates from first_date to last_date, by default today's."""
        bccr_token = self.env['ir.config_parameter'].sudo().get_str('bccr_token')

        # The token is what turns the update on, so without one there is
        # nothing to do yet and it is no error
        if not bccr_token:
            _logger.info("No BCCR token configured, the exchange rate is not updated")
            return

        first_date = first_date or datetime.now().date()
        last_date = last_date or first_date

        # The cron must not fail on a BCCR outage: Odoo would deactivate it
        # after a few days of failures, so the error is only logged
        try:
            rates = BccrApi(self.env, bccr_token).get_rates(first_date, last_date)
        except UserError as e:
            _logger.error("Exchange rate update failed: %s", e)
            return

        currency = self.env.ref('base.USD')
        for date, (selling_original_rate, buying_original_rate) in rates.items():
            rate_date = date - RATE_DATE_OFFSET

            # Odoo stores how many dollars one colón is worth, the inverse of
            # the colones per dollar the BCCR publishes
            vals = {
                'rate': 1 / selling_original_rate,
                'original_rate': selling_original_rate,
                'rate_2': 1 / buying_original_rate,
                'original_rate_2': buying_original_rate,
            }
            existing_rate = self.search([
                ('name', '=', rate_date),
                ('currency_id', '=', currency.id),
            ], limit=1)
            if existing_rate:
                existing_rate.write(vals)
            else:
                self.create({**vals, 'name': rate_date, 'currency_id': currency.id})

        if rates:
            _logger.info("BCCR exchange rates loaded for %s to %s", min(rates), max(rates))
