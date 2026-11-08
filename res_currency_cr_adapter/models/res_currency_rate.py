# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, release
from datetime import timedelta, datetime
import logging
import requests

_logger = logging.getLogger(__name__)

# The old SOAP service (wsindicadoreseconomicos.asmx) was retired and answers
# 503; the SDDE REST API is mandatory since 2025-04-07. The token is no longer
# a subscription parameter, it is a bearer token generated from the
# Indicadores Economicos site under Mi Perfil -> Generar token.
BCCR_API_BASE = 'https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API'
BCCR_SELLING_INDICATOR = '318'  # Tipo cambio venta
BCCR_BUYING_INDICATOR = '317'  # Tipo cambio compra
BCCR_TIMEOUT = 60

# The API gateway answers 403 to the default user agent of the requests
# library, which is why the BCCR sets one explicitly on its own example
BCCR_USER_AGENT = 'Odoo/%s (res_currency_cr_adapter)' % release.major_version

# Causes documented on Anexo C of the SDDE standard
BCCR_HTTP_ERRORS = {
    400: "invalid parameters, check the indicator code and that dates use yyyy/mm/dd",
    401: "the token is missing, invalid or expired",
    403: "the user has no valid subscription, or the gateway rejected the user agent",
    404: "wrong endpoint, or the 'idioma' parameter is missing",
    429: "too many requests, lower the frequency of the cron",
    500: "BCCR internal error, or the token was rejected",
}

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

    def _bccr_get_series(self, indicator, first_date, last_date, token):
        """Read one BCCR economic indicator from the SDDE REST API.

        Returns {'YYYY-MM-DD': value} for the requested range. The BCCR
        publishes a value for every calendar day, carrying the last published
        one over weekends and holidays, so a single call fills a whole range
        with no gaps. Returns an empty dict on any failure: this runs from a
        cron and must not raise, but every failure is logged as an error so it
        never goes unnoticed.
        """
        url = '%s/indicadoresEconomicos/%s/series' % (BCCR_API_BASE, indicator)
        params = {
            # The API rejects any other format with a 400
            'fechaInicio': first_date.strftime('%Y/%m/%d'),
            'fechaFin': last_date.strftime('%Y/%m/%d'),
            # Omitting the language answers 404, it is not optional
            'idioma': 'ES',
        }
        headers = {
            'Authorization': 'Bearer %s' % token,
            'Accept': 'application/json',
            'User-Agent': BCCR_USER_AGENT,
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=BCCR_TIMEOUT)
        except requests.exceptions.RequestException as e:
            _logger.error("BCCR indicator %s: request failed: %s", indicator, e)
            return {}

        if response.status_code != 200:
            _logger.error("BCCR indicator %s: HTTP %s - %s. Response: %s",
                          indicator, response.status_code,
                          BCCR_HTTP_ERRORS.get(response.status_code, "unexpected status"),
                          response.text[:200])
            return {}

        try:
            payload = response.json()
        except ValueError:
            _logger.error("BCCR indicator %s: response is not valid JSON: %s",
                          indicator, response.text[:200])
            return {}

        series = {}
        for indicator_data in payload.get('datos') or []:
            for point in indicator_data.get('series') or []:
                value = point.get('valorDatoPorPeriodo')
                # The API sends null for days with no published value
                if not value:
                    continue
                series[point['fecha'][:10]] = float(value)

        # 'estado' comes back True even for an empty range, so the series are
        # the only reliable sign that the query actually returned data
        if not series:
            _logger.error("BCCR indicator %s: no data between %s and %s (%s)", indicator,
                          params['fechaInicio'], params['fechaFin'], payload.get('mensaje'))

        return series

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

        selling_rates = self._bccr_get_series(
            BCCR_SELLING_INDICATOR, first_date, last_date, bccr_token)
        buying_rates = self._bccr_get_series(
            BCCR_BUYING_INDICATOR, first_date, last_date, bccr_token)

        currency = self.env.ref('base.USD')

        # A rate is only complete when both indicators published that date,
        # so pair them by date instead of walking both lists by position
        incomplete_dates = set(selling_rates) ^ set(buying_rates)
        if incomplete_dates:
            _logger.error("Error loading currency rates, buying and selling rates don't "
                          "match for %s", ', '.join(sorted(incomplete_dates)))

        loaded_dates = sorted(set(selling_rates) & set(buying_rates))
        for date_str in loaded_dates:
            selling_original_rate = selling_rates[date_str]
            buying_original_rate = buying_rates[date_str]
            rate_date = fields.Date.to_date(date_str) - RATE_DATE_OFFSET

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

        if loaded_dates:
            _logger.info("BCCR exchange rates loaded for %s to %s", loaded_dates[0], loaded_dates[-1])
