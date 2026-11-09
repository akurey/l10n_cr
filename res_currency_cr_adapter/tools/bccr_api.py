# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import fields, release
from odoo.exceptions import UserError
from odoo.tools.translate import LazyTranslate

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

# BCCR's SDDE REST API (https://sdd.bccr.fi.cr/), authenticated with a bearer token
API_BASE = 'https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API'
CUADRO_CODE = 1  # The dollar's selling and buying rates
SELLING_INDICATOR = '318'
BUYING_INDICATOR = '317'
TIMEOUT = 60

# The API gateway answers 403 to the requests library's default user agent
USER_AGENT = 'Odoo/%s (res_currency_cr_adapter)' % release.major_version

# Causes of the HTTP errors, from Annex C of the SDDE standard: the BCCR's own are too generic
ERROR_CAUSES = {
    400: _lt("invalid parameters, check the cuadro code and that dates use yyyy/mm/dd"),
    401: _lt("the token is missing, invalid or expired"),
    403: _lt("the user has no valid subscription, or the gateway rejected the user agent"),
    404: _lt("wrong endpoint, or the 'idioma' parameter is missing"),
    429: _lt("too many requests, lower the frequency of the update"),
    500: _lt("BCCR internal error, or the token was rejected"),
}


class BccrApi:
    """Client of the BCCR's exchange rate API."""

    def __init__(self, env, token):
        self.env = env
        self.token = token

    def get_rates(self, first_date, last_date):
        """Return {date: (selling, buying)} in colones per dollar from first_date to last_date.

        :raise UserError: if the BCCR cannot be reached, rejects the request or has no data
        """
        series = self._get_series(first_date, last_date)
        selling_rates = series[SELLING_INDICATOR]
        buying_rates = series[BUYING_INDICATOR]
        return {date: (selling_rates[date], buying_rates[date]) for date in selling_rates}

    def _get_series(self, first_date, last_date):
        """Return the cuadro's {indicator: {date: value}} from first_date to last_date."""
        payload = self._request('cuadro/%s/series' % CUADRO_CODE, {
            # The API rejects any other format with a 400
            'fechaInicio': first_date.strftime('%Y/%m/%d'),
            'fechaFin': last_date.strftime('%Y/%m/%d'),
        })
        series = {
            indicator['codigoIndicador']: {
                fields.Date.to_date(point['fecha']): point['valorDatoPorPeriodo']
                for point in indicator['series']
                # The API sends null for days with no published value
                if point['valorDatoPorPeriodo']
            }
            for cuadro in payload['datos']
            for indicator in cuadro['indicadores']
        }

        # 'estado' is True even for an empty range, so only the series show there is data
        if not any(series.values()):
            raise UserError(self.env._(
                "The BCCR has no data between %(start)s and %(end)s", start=first_date, end=last_date))

        return series

    def _request(self, path, params):
        """Return the decoded JSON of a GET on the SDDE API."""
        headers = {
            'Authorization': 'Bearer %s' % self.token,
            'Accept': 'application/json',
            'User-Agent': USER_AGENT,
        }
        try:
            response = requests.get(
                '%s/%s' % (API_BASE, path),
                # Omitting the language answers 404, it is not optional
                params={**params, 'idioma': 'ES'},
                headers=headers, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise UserError(self.env._("Could not connect to the BCCR: %(error)s", error=e)) from None

        if response.status_code != 200:
            _logger.warning("BCCR %s: HTTP %s, response: %s", path, response.status_code, response.text[:200])
            raise UserError(self.env._(
                "The BCCR rejected the request (HTTP %(status)s): %(cause)s",
                status=response.status_code,
                cause=ERROR_CAUSES.get(response.status_code, _lt("unexpected status"))))

        try:
            return response.json()
        except ValueError:
            _logger.warning("BCCR %s: response: %s", path, response.text[:200])
            raise UserError(self.env._("The BCCR answered with an invalid response")) from None
