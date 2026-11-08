# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import fields, release
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# BCCR's SDDE REST API (https://sdd.bccr.fi.cr/), authenticated with a bearer token
API_BASE = 'https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API'
SELLING_INDICATOR = '318'  # Tipo cambio venta
BUYING_INDICATOR = '317'  # Tipo cambio compra
TIMEOUT = 60

# The API gateway answers 403 to the default user agent of the requests
# library, which is why the BCCR sets one explicitly on its own example
USER_AGENT = 'Odoo/%s (res_currency_cr_adapter)' % release.major_version


class BccrApi:
    """Client of the BCCR's exchange rate indicators.

    It only asks the BCCR for its rates: storing them is up to the caller.
    """

    def __init__(self, env, token):
        """:param env: the environment whose language the errors are translated to
        :param str token: the bearer token generated on the BCCR's site
        """
        self.env = env
        self.token = token

    def get_rates(self, first_date, last_date):
        """Return the BCCR's selling and buying rates from first_date to last_date.

        :return: {date: (selling, buying)} in colones per dollar, for every
            date both rates were published for
        :raise UserError: if the BCCR cannot be reached, rejects the request
            or has no data for the range, with the cause in the message.
        """
        selling_rates = self._get_series(SELLING_INDICATOR, first_date, last_date)
        buying_rates = self._get_series(BUYING_INDICATOR, first_date, last_date)

        # A rate is only complete when both indicators published that date,
        # so pair them by date instead of walking both lists by position
        incomplete_dates = set(selling_rates) ^ set(buying_rates)
        if incomplete_dates:
            _logger.error("Error loading currency rates, buying and selling rates don't "
                          "match for %s", ', '.join(sorted(incomplete_dates)))

        return {
            fields.Date.to_date(date_str): (selling_rates[date_str], buying_rates[date_str])
            for date_str in sorted(set(selling_rates) & set(buying_rates))
        }

    def _error_cause(self, status):
        """Cause of a BCCR HTTP error, as documented on Anexo C of the SDDE standard.

        The BCCR's own error bodies are too generic to show: a 500 only says
        "Internal server error", even for an invalid token.
        """
        return {
            400: self.env._("invalid parameters, check the indicator code and that dates use yyyy/mm/dd"),
            401: self.env._("the token is missing, invalid or expired"),
            403: self.env._("the user has no valid subscription, or the gateway rejected the user agent"),
            404: self.env._("wrong endpoint, or the 'idioma' parameter is missing"),
            429: self.env._("too many requests, lower the frequency of the update"),
            500: self.env._("BCCR internal error, or the token was rejected"),
        }.get(status, self.env._("unexpected status"))

    def _get_series(self, indicator, first_date, last_date):
        """Read one BCCR economic indicator from the SDDE REST API.

        Returns {'YYYY-MM-DD': value} for the requested range. The BCCR
        publishes a value for every calendar day, carrying the last published
        one over weekends and holidays, so a single call fills a whole range
        with no gaps.

        :raise UserError: if the BCCR cannot be reached, rejects the request
            or has no data for the range, with the cause in the message.
        """
        url = '%s/indicadoresEconomicos/%s/series' % (API_BASE, indicator)
        params = {
            # The API rejects any other format with a 400
            'fechaInicio': first_date.strftime('%Y/%m/%d'),
            'fechaFin': last_date.strftime('%Y/%m/%d'),
            # Omitting the language answers 404, it is not optional
            'idioma': 'ES',
        }
        headers = {
            'Authorization': 'Bearer %s' % self.token,
            'Accept': 'application/json',
            'User-Agent': USER_AGENT,
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise UserError(self.env._("Could not connect to the BCCR: %(error)s", error=e)) from None

        if response.status_code != 200:
            _logger.warning("BCCR indicator %s: HTTP %s, response: %s",
                            indicator, response.status_code, response.text[:200])
            raise UserError(self.env._(
                "The BCCR rejected the request for indicator %(indicator)s (HTTP %(status)s): %(cause)s",
                indicator=indicator, status=response.status_code,
                cause=self._error_cause(response.status_code)))

        try:
            payload = response.json()
        except ValueError:
            _logger.warning("BCCR indicator %s: response: %s", indicator, response.text[:200])
            raise UserError(self.env._(
                "The BCCR answered the request for indicator %(indicator)s with an invalid response",
                indicator=indicator)) from None

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
            raise UserError(self.env._(
                "The BCCR has no data for indicator %(indicator)s between %(start)s and %(end)s",
                indicator=indicator, start=first_date, end=last_date))

        return series
