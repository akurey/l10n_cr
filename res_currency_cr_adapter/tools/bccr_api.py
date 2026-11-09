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
# Cuadro 1 publishes the dollar's selling and buying rates together, so a
# single call returns both
CUADRO_CODE = 1
SELLING_INDICATOR = '318'  # Tipo cambio venta
BUYING_INDICATOR = '317'  # Tipo cambio compra
TIMEOUT = 60

# The API gateway answers 403 to the default user agent of the requests
# library, which is why the BCCR sets one explicitly on its own example
USER_AGENT = 'Odoo/%s (res_currency_cr_adapter)' % release.major_version

# Causes of the BCCR's HTTP errors, as documented on Anexo C of the SDDE
# standard: its own error bodies are too generic to show, a 500 only says
# "Internal server error", even for an invalid token
ERROR_CAUSES = {
    400: _lt("invalid parameters, check the cuadro code and that dates use yyyy/mm/dd"),
    401: _lt("the token is missing, invalid or expired"),
    403: _lt("the user has no valid subscription, or the gateway rejected the user agent"),
    404: _lt("wrong endpoint, or the 'idioma' parameter is missing"),
    429: _lt("too many requests, lower the frequency of the update"),
    500: _lt("BCCR internal error, or the token was rejected"),
}


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

        :return: {date: (selling, buying)} in colones per dollar
        :raise UserError: if the BCCR cannot be reached, rejects the request
            or has no data for the range, with the cause in the message.
        """
        series = self._get_series(first_date, last_date)
        buying_rates = series[BUYING_INDICATOR]
        return {
            fields.Date.to_date(date_str): (selling, buying_rates[date_str])
            for date_str, selling in series[SELLING_INDICATOR].items()
        }

    def _get_series(self, first_date, last_date):
        """Read the indicators of the BCCR's cuadro from the SDDE REST API.

        Returns {indicator: {'YYYY-MM-DD': value}} for the requested range.
        The BCCR publishes a value for every calendar day, carrying the last
        published one over weekends and holidays, so a single call fills a
        whole range with no gaps.

        :raise UserError: if the BCCR cannot be reached, rejects the request
            or has no data for the range, with the cause in the message.
        """
        url = '%s/cuadro/%s/series' % (API_BASE, CUADRO_CODE)
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
            _logger.warning("BCCR cuadro %s: HTTP %s, response: %s",
                            CUADRO_CODE, response.status_code, response.text[:200])
            raise UserError(self.env._(
                "The BCCR rejected the request for cuadro %(cuadro)s (HTTP %(status)s): %(cause)s",
                cuadro=CUADRO_CODE, status=response.status_code,
                cause=ERROR_CAUSES.get(response.status_code, _lt("unexpected status"))))

        try:
            payload = response.json()
        except ValueError:
            _logger.warning("BCCR cuadro %s: response: %s", CUADRO_CODE, response.text[:200])
            raise UserError(self.env._(
                "The BCCR answered the request for cuadro %(cuadro)s with an invalid response",
                cuadro=CUADRO_CODE)) from None

        series = {}
        for cuadro in payload.get('datos') or []:
            for indicator in cuadro.get('indicadores') or []:
                series[indicator['codigoIndicador']] = {
                    point['fecha']: float(point['valorDatoPorPeriodo'])
                    for point in indicator.get('series') or []
                    # The API sends null for days with no published value
                    if point.get('valorDatoPorPeriodo')
                }

        # 'estado' comes back True even for an empty range, so the series are
        # the only reliable sign that the query actually returned data
        if not any(series.values()):
            raise UserError(self.env._(
                "The BCCR has no data for cuadro %(cuadro)s between %(start)s and %(end)s",
                cuadro=CUADRO_CODE, start=first_date, end=last_date))

        return series
