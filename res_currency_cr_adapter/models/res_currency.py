# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from datetime import timedelta, datetime, date as date_type
import logging
import requests
from zoneinfo import ZoneInfo

_logger = logging.getLogger(__name__)

# The old SOAP service (wsindicadoreseconomicos.asmx) was retired and answers
# 503; the SDDE REST API is mandatory since 2025-04-07. The token is no longer
# a subscription parameter, it is a bearer token generated from the
# Indicadores Economicos site under Mi Perfil -> Generar token.
BCCR_API_BASE = 'https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API'
BCCR_SELLING_INDICATOR = '318'  # Tipo cambio venta
BCCR_BUYING_INDICATOR = '317'  # Tipo cambio compra
# The BCCR publishes the euro against the US dollar (USD per EUR), on business days, the same day. The euro in
# colones is not published: it is derived as that rate times the dollar's selling rate (EUR → USD → CRC).
BCCR_EUR_USD_INDICATOR = '333'
# The euro update runs twice a day (see currency_data.xml): in the evening, for tomorrow, and in the morning, for today
COSTA_RICA_TZ = ZoneInfo('America/Costa_Rica')
BCCR_TIMEOUT = 60

# The API gateway answers 403 to the default user agent of the requests
# library, which is why the BCCR sets one explicitly on its own example
BCCR_USER_AGENT = 'Odoo/19.0 (res_currency_cr_adapter)'

# Causes documented on Anexo C of the SDDE standard
BCCR_HTTP_ERRORS = {
    400: "invalid parameters, check the indicator code and that dates use yyyy/mm/dd",
    401: "the token is missing, invalid or expired",
    403: "the user has no valid subscription, or the gateway rejected the user agent",
    404: "wrong endpoint, or the 'idioma' parameter is missing",
    429: "too many requests, lower the frequency of the cron",
    500: "BCCR internal error, or the token was rejected",
}


def _as_date(value):
    """A date, a datetime or a 'YYYY-MM-DD' string as a date (falsy stays falsy)."""
    if isinstance(value, str):
        return datetime.strptime(value, '%Y-%m-%d').date()
    if isinstance(value, datetime):
        return value.date()
    return value


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    rate = fields.Float(digits='Currency Rate Precision')

    def _cron_create_missing_exchange_rates(self):
        for currency in self.env['res.currency'].search([('id', '!=', self.env.user.company_id.currency_id.id)]):
            currency.action_create_missing_exchange_rates()

    def action_create_missing_exchange_rates(self):
        # It is validated that the currency is dollars
        if self.id != self.env.ref('base.USD').id:
            return

        currency_rate_obj = self.env['res.currency.rate']
        today = fields.Date.context_today(self)

        first_day = currency_rate_obj.search([
            ('company_id', '=', self.env.user.company_id.id),
            ('currency_id', '=', self.id)
        ], limit=1, order='name asc')

        # If there is no record, you must fill the table with the current day
        first_date = first_day.name if first_day else today

        # Both sources accept a date range, so a single request covers every
        # missing day instead of one request per day
        currency_rate_obj._cron_update(first_date, today)

        # Any day the source did not publish is loaded on the last available day
        date = first_date
        while date <= today:
            if not currency_rate_obj.search([
                ('name', '=', date),
                ('currency_id', '=', self.id),
            ], limit=1):
                currency_rate_obj._create_the_latest_exchange_rate_to_date(self, date)
            date += timedelta(days=1)


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    # Change decimal presicion to work with CRC where 1 USD is more de 555 CRC
    rate = fields.Float(string='Selling Rate',
                        digits='Currency Rate Precision')

    # Costa Rica uses two exchange rates:
    #   - Buying exchange rate - used when a financial institutions buy USD from you (rate)
    #   - Selling exchange rate - used when financial institutions sell USD to you (rate_2)
    rate_2 = fields.Float(string='Buying Rate', digits='Currency Rate Precision',
                          help='The buying rate of the currency to the currency of rate 1.')

    # Rate as it is get
    original_rate = fields.Float(string='Selling Rate in Costa Rica', digits=(6, 2),
                                 help='The selling exchange rate from CRC to USD as it is send from BCCR')

    # Rate as it is get
    original_rate_2 = fields.Float(string='Buying Rate in Costa Rica', digits=(6, 2),
                                   help='The buying exchange rate from CRC to USD as it is send from BCCR')

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

        _logger.info("=========================================================")
        _logger.info("Executing exchange rate update from 1 CRC = X USD")

        first_date = _as_date(first_date)
        last_date = _as_date(last_date)

        exchange_source = self.env['ir.config_parameter'].sudo().get_param('exchange_source')
        if exchange_source == 'bccr':
            _logger.info("Getting exchange rates from BCCR")
            bccr_token = self.env['ir.config_parameter'].sudo().get_param('bccr_token')

            if not bccr_token:
                _logger.error("No BCCR token configured, generate one from the Indicadores "
                              "Economicos site under Mi Perfil -> Generar token")
                return False

            # Get current date to get exchange rate for today
            if first_date:
                initial_date = first_date
                end_date = last_date or first_date
            else:
                initial_date = datetime.now().date()
                end_date = initial_date

            selling_rates = self._bccr_get_series(
                BCCR_SELLING_INDICATOR, initial_date, end_date, bccr_token)
            buying_rates = self._bccr_get_series(
                BCCR_BUYING_INDICATOR, initial_date, end_date, bccr_token)

            currency_id = self.env.ref('base.USD')

            # A rate is only complete when both indicators published that date,
            # so pair them by date instead of walking both lists by position
            incomplete_dates = set(selling_rates) ^ set(buying_rates)
            if incomplete_dates:
                _logger.error("Error loading currency rates, buying and selling rates don't "
                              "match for %s", ', '.join(sorted(incomplete_dates)))

            for current_date_str in sorted(set(selling_rates) & set(buying_rates)):
                self._cr_set_rate(currency_id, current_date_str, selling_rates[current_date_str],
                                  buying_rates[current_date_str])

        if exchange_source == 'hacienda':
            _logger.info("Getting exchange rates from HACIENDA")

            # Get current date to get exchange rate for today
            if first_date:
                currency_rate_obj = self.env['res.currency.rate']
                currency_usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                companies = self.env['res.company'].search([])

                # Hacienda API returns ~60 days max per request; chunk into 60-day batches
                chunk_size = timedelta(days=60)
                all_data = []
                if not isinstance(first_date, date_type) or not isinstance(last_date, date_type):
                    return False
                chunk_start = first_date
                end = last_date

                while chunk_start <= end:
                    chunk_end = min(chunk_start + chunk_size - timedelta(days=1), end)
                    try:
                        url = ('https://api.hacienda.go.cr/indicadores/tc/dolar/historico/?d='
                               + chunk_start.strftime('%Y-%m-%d') + '&h=' + chunk_end.strftime('%Y-%m-%d'))
                        _logger.info('Hacienda request chunk %s → %s', chunk_start, chunk_end)
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            chunk_data = response.json()
                            _logger.info('Hacienda chunk returned %d records', len(chunk_data))
                            all_data.extend(chunk_data)
                        else:
                            _logger.error('Hacienda API returned %s for chunk %s-%s',
                                          response.status_code, chunk_start, chunk_end)
                    except requests.exceptions.RequestException as e:
                        _logger.error('RequestException %s', e)
                    chunk_start = chunk_end + timedelta(days=1)

                _logger.info('Hacienda total records collected: %d', len(all_data))

                for company in companies:
                    for rate_line in all_data:
                            fecha_str = rate_line['fecha']
                            try:
                                rate_date = datetime.strptime(fecha_str, '%Y-%m-%d %H:%M:%S').date()
                            except ValueError:
                                rate_date = datetime.strptime(fecha_str, '%Y-%m-%d').date()

                            vals = {
                                'original_rate': rate_line['venta'],
                                'rate': 1 / rate_line['venta'],
                                'original_rate_2': rate_line['compra'],
                                'rate_2': 1 / rate_line['compra'],
                                'currency_id': currency_usd.id,
                                'company_id': company.id,
                            }

                            rate_id = currency_rate_obj.search([
                                ('name', '=', rate_date),
                                ('currency_id', '=', currency_usd.id),
                                ('company_id', '=', company.id),
                            ], limit=1)

                            if rate_id:
                                rate_id.write(vals)
                            else:
                                vals['name'] = rate_date
                                currency_rate_obj.create(vals)
            else:
                try:
                    url = 'https://api.hacienda.go.cr/indicadores/tc'
                    response = requests.get(url, timeout=5)

                except requests.exceptions.RequestException as e:
                    _logger.error('RequestException %s', e)
                    return False

                if response.status_code in (200,):
                    # Save the exchange rate in database
                    today = datetime.now().strftime('%Y-%m-%d')
                    data = response.json()
                    companies = self.env['res.company'].search([])
                    for company in companies:
                        _logger.error(company.id)
                        vals = {}
                        vals['original_rate'] = data['dolar']['venta']['valor']

                        # Odoo utiliza un valor inverso,
                        # a cuantos dólares equivale 1 colón, por eso se divide 1 / tipo de cambio.

                        vals['rate'] = 1 / vals['original_rate']
                        vals['original_rate_2'] = data['dolar']['compra']['valor']
                        vals['rate_2'] = 1 / vals['original_rate_2']
                        vals['currency_id'] = self.env.ref('base.USD').id

                        rate_id = self.env['res.currency.rate'].search([('name', '=', today)], limit=1)

                        if rate_id:
                            rate_id.write(vals)
                        else:
                            vals['name'] = today
                            self.create(vals)

                _logger.info(vals)

        _logger.info("=========================================================")

    def _cr_set_rate(self, currency, date, selling_crc, buying_crc=None):
        """Create or update `currency`'s rate on `date` from its price in colones. The buying price is only for
        currencies the BCCR publishes one for (the dollar); without it the buying rate is left empty."""
        vals = {
            # Odoo uses the value of 1 unit of the base currency divided by the exchange rate
            'rate': 1 / selling_crc,
            'original_rate': selling_crc,
            'rate_2': 1 / buying_crc if buying_crc else 0.0,
            'original_rate_2': buying_crc or 0.0,
        }
        rate = self.search([('name', '=', date), ('currency_id', '=', currency.id)], limit=1)
        if rate:
            rate.write(vals)
        else:
            self.create(dict(vals, name=date, currency_id=currency.id))
        _logger.info("%s rate on %s: %s", currency.name, date, vals)

    @api.model
    def _cron_update_euro(self, first_date=False, last_date=False):
        """Load the euro in colones for each day of the range (today and tomorrow in Costa Rica by default). Each
        day takes the last euro the BCCR had published up to that day (333, USD per EUR) times that day's selling
        dollar (318), which is what is in force at any hour of that day: the euro of a day is published on that day
        in the morning, the dollar of a day the evening before. Run in the evening it leaves tomorrow's rate ready
        before midnight (today's euro times tomorrow's dollar); run in the morning, after the euro is out, it
        replaces today's rate with the new euro. A day without a euro (weekend, holiday) keeps the last one."""
        euro = self.env.ref('base.EUR')
        params = self.env['ir.config_parameter'].sudo()
        # EUR is activated for the whole database, not per company
        if not euro.active or params.get_param('exchange_source') != 'bccr':
            return False
        token = params.get_param('bccr_token')
        if not token:
            _logger.error("No BCCR token configured, the euro rate was not updated")
            return False

        first_date = _as_date(first_date) or datetime.now(COSTA_RICA_TZ).date()
        last_date = _as_date(last_date) or first_date + timedelta(days=1)
        selling_rates = self._bccr_get_series(BCCR_SELLING_INDICATOR, first_date, last_date, token)
        # A week earlier covers a range that starts on a day without a euro
        euro_in_dollars = self._bccr_get_series(
            BCCR_EUR_USD_INDICATOR, first_date - timedelta(days=7), last_date, token)
        published = sorted(euro_in_dollars)
        for day, selling_crc in sorted(selling_rates.items()):
            known = [published_day for published_day in published if published_day <= day]
            if known:
                self._cr_set_rate(euro, day, euro_in_dollars[known[-1]] * selling_crc)
        return True

    def _create_the_latest_exchange_rate_to_date(self, currency, date=None):
        name = date or datetime.now()
        currency_rate_obj = self.env['res.currency.rate'].search([
            ('company_id', '=', self.env.user.company_id.id),
            ('currency_id', '=', currency.id),
            ('name', '<=', name),
        ], limit=1, order='name desc')

        # With no earlier rate there is nothing to carry over
        if not currency_rate_obj or currency_rate_obj.name == name:
            return

        self.create({
            'name': name,
            'rate': currency_rate_obj.rate,
            'original_rate': currency_rate_obj.original_rate,
            'rate_2': currency_rate_obj.rate_2,
            'original_rate_2': currency_rate_obj.original_rate_2,
            'currency_id': currency_rate_obj.currency_id.id,
            'company_id': currency_rate_obj.company_id.id,
        })
        
        
    @api.model
    def _cron_update_usd(self, first_date=False, last_date=False):

        _logger.info("=========================================================")
        _logger.info("Executing exchange rate update from 1 CRC = X USD")

        # The callers of this method are not consistent about the type they
        # pass, normalize it the same way _cron_update does
        if isinstance(first_date, str):
            first_date = datetime.strptime(first_date, '%Y-%m-%d').date()
        elif isinstance(first_date, datetime):
            first_date = first_date.date()
        if isinstance(last_date, str):
            last_date = datetime.strptime(last_date, '%Y-%m-%d').date()
        elif isinstance(last_date, datetime):
            last_date = last_date.date()

        exchange_source = self.env['ir.config_parameter'].sudo().get_param('exchange_source')
        if exchange_source == 'bccr':
            _logger.info("Getting exchange rates from BCCR")
            bccr_token = self.env['ir.config_parameter'].sudo().get_param('bccr_token')

            if not bccr_token:
                _logger.error("No BCCR token configured, generate one from the Indicadores "
                              "Economicos site under Mi Perfil -> Generar token")
                return False

            # Get current date to get exchange rate for today
            if first_date:
                initial_date = first_date
                end_date = last_date or first_date
            else:
                initial_date = datetime.now().date()
                end_date = initial_date

            selling_rates = self._bccr_get_series(
                BCCR_SELLING_INDICATOR, initial_date, end_date, bccr_token)
            buying_rates = self._bccr_get_series(
                BCCR_BUYING_INDICATOR, initial_date, end_date, bccr_token)

            currency_id = self.env.ref('base.CRC')

            incomplete_dates = set(selling_rates) ^ set(buying_rates)
            if incomplete_dates:
                _logger.error("Error loading currency rates, buying and selling rates don't "
                              "match for %s", ', '.join(sorted(incomplete_dates)))

            for current_date_str in sorted(set(selling_rates) & set(buying_rates)):
                selling_rate = selling_rates[current_date_str]
                buying_rate = buying_rates[current_date_str]

                # Odoo uses the value of 1 unit of the base currency divided between the exchage rate
                selling_original_rate = 1 / selling_rate
                buying_original_rate = 1 / buying_rate

                # Get the rate for this date to know it is already registered
                rates_ids = self.env['res.currency.rate'].search([
                    ('name', '=', current_date_str),
                    ('currency_id', '=', currency_id.id),
                ], limit=1)

                if len(rates_ids) > 0:
                    rates_ids.write(
                        {'rate': selling_rate,
                         'original_rate': selling_original_rate,
                         'rate_2': buying_rate,
                         'original_rate_2': buying_original_rate,
                         'currency_id': currency_id.id}
                        )
                else:
                    self.create(
                        {'name': current_date_str,
                         'rate': selling_rate,
                         'original_rate': selling_original_rate,
                         'rate_2': buying_rate,
                         'original_rate_2': buying_original_rate,
                         'currency_id': currency_id.id})

                _logger.info({'name': current_date_str,
                              'rate': selling_rate,
                              'original_rate': selling_original_rate,
                              'rate_2': buying_rate,
                              'original_rate_2': buying_original_rate,
                              'currency_id': currency_id.id})

        if exchange_source == 'hacienda':
            _logger.info("Getting exchange rates from HACIENDA")

            # Get current date to get exchange rate for today
            if first_date:
                initial_date = first_date.strftime('%Y-%m-%d')
                end_date = last_date.strftime('%Y-%m-%d')

                try:
                    url = 'https://api.hacienda.go.cr/indicadores/tc/dolar/historico/?d='+initial_date+'&h='+end_date
                    response = requests.get(url, timeout=5)

                except requests.exceptions.RequestException as e:
                    _logger.error('RequestException %s', e)
                    return False
                if response.status_code in (200,):
                    data = response.json()
                    companies = self.env['res.company'].search([])
                    for company in companies:
                        _logger.error(company.id)

                        for rate_line in data:
                            today = datetime.strptime(rate_line['fecha'], '%Y-%m-%d %H:%M:%S')
                            vals = {}
                            vals['rate'] = rate_line['venta']
                            # Odoo utiliza un valor inverso,
                            # a cuantos dólares equivale 1 colón, por eso se divide 1 / tipo de cambio.
                            vals['original_rate'] = 1 / vals['rate']
                            vals['rate_2'] = rate_line['compra']
                            vals['original_rate_2'] = 1 / vals['rate_2']
                            vals['currency_id'] = self.env.ref('base.CRC').id

                            rate_id = self.env['res.currency.rate'].search([('name', '=', today.date())], limit=1)

                            if rate_id:
                                rate_id.write(vals)
                            else:
                                vals['name'] = today.date()
                                self.create(vals)
            else:
                try:
                    url = 'https://api.hacienda.go.cr/indicadores/tc'
                    response = requests.get(url, timeout=5)

                except requests.exceptions.RequestException as e:
                    _logger.error('RequestException %s', e)
                    return False

                if response.status_code in (200,):
                    # Save the exchange rate in database
                    today = datetime.now().strftime('%Y-%m-%d')
                    data = response.json()
                    companies = self.env['res.company'].search([])
                    for company in companies:
                        _logger.error(company.id)
                        vals = {}
                        vals['rate'] = data['dolar']['venta']['valor']

                        # Odoo utiliza un valor inverso,
                        # a cuantos dólares equivale 1 colón, por eso se divide 1 / tipo de cambio.

                        vals['original_rate'] = 1 / vals['rate']
                        vals['rate_2'] = data['dolar']['compra']['valor']
                        vals['original_rate_2'] = 1 / vals['rate_2']
                        vals['currency_id'] = self.env.ref('base.CRC').id

                        rate_id = self.env['res.currency.rate'].search([('name', '=', today)], limit=1)

                        if rate_id:
                            rate_id.write(vals)
                        else:
                            vals['name'] = today
                            self.create(vals)

                _logger.info(vals)

        _logger.info("=========================================================")
