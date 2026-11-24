from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

SELLING = '318'
BUYING = '317'
EUR_USD = '333'

# Friday 2026-11-13 and Monday 2026-11-16 have a euro, the weekend between them does not. The dollar of
# Tuesday 2026-11-17 is published (the evening before) but its euro is not yet; Wednesday's dollar is not either
SERIES = {
    SELLING: {'2026-11-13': 450.0, '2026-11-14': 451.0, '2026-11-15': 452.0, '2026-11-16': 448.0,
              '2026-11-17': 449.0},
    BUYING: {'2026-11-13': 440.0, '2026-11-14': 441.0, '2026-11-15': 442.0, '2026-11-16': 438.0,
             '2026-11-17': 439.0},
    EUR_USD: {'2026-11-12': 1.09, '2026-11-13': 1.10, '2026-11-16': 1.20},
}


@tagged('post_install', '-at_install')
class TestEuroRates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('exchange_source', 'bccr')
        params.set_param('bccr_token', 'token')
        cls.euro = cls.env.ref('base.EUR')
        cls.euro.active = True
        cls.Rate = cls.env['res.currency.rate']

    def _fake_series(self, indicator, first_date, last_date, token):
        return {day: value for day, value in SERIES[indicator].items()
                if first_date.isoformat() <= day <= last_date.isoformat()}

    def _run_euro(self, first, last):
        with patch.object(type(self.Rate), '_bccr_get_series', autospec=True,
                          side_effect=lambda rate, *args: self._fake_series(*args)):
            self.Rate._cron_update_euro(first, last)

    def _euro_rate(self, day):
        return self.Rate.search([('currency_id', '=', self.euro.id), ('name', '=', day)])

    def test_business_day_takes_that_days_euro_times_that_days_dollar(self):
        self._run_euro('2026-11-16', '2026-11-16')
        rate = self._euro_rate('2026-11-16')
        self.assertAlmostEqual(rate.original_rate, 1.20 * 448.0)
        self.assertAlmostEqual(rate.rate, 1 / (1.20 * 448.0))

    def test_weekend_takes_the_last_euro_published_times_each_days_dollar(self):
        self._run_euro('2026-11-13', '2026-11-16')
        self.assertAlmostEqual(self._euro_rate('2026-11-13').original_rate, 1.10 * 450.0)
        self.assertAlmostEqual(self._euro_rate('2026-11-14').original_rate, 1.10 * 451.0)
        self.assertAlmostEqual(self._euro_rate('2026-11-15').original_rate, 1.10 * 452.0)
        self.assertAlmostEqual(self._euro_rate('2026-11-16').original_rate, 1.20 * 448.0)

    def test_evening_run_leaves_tomorrows_rate_with_the_last_euro_times_tomorrows_dollar(self):
        # no end date: today and tomorrow
        self._run_euro('2026-11-16', False)
        self.assertAlmostEqual(self._euro_rate('2026-11-16').original_rate, 1.20 * 448.0)
        self.assertAlmostEqual(self._euro_rate('2026-11-17').original_rate, 1.20 * 449.0)

    def test_morning_run_replaces_the_rate_with_the_euro_published_that_day(self):
        self._run_euro('2026-11-16', False)
        with patch.dict(SERIES[EUR_USD], {'2026-11-17': 1.25}):
            self._run_euro('2026-11-17', '2026-11-17')
        rate = self._euro_rate('2026-11-17')
        self.assertEqual(len(rate), 1)
        self.assertAlmostEqual(rate.original_rate, 1.25 * 449.0)

    def test_a_day_without_a_published_dollar_gets_no_rate(self):
        self._run_euro('2026-11-17', False)
        self.assertTrue(self._euro_rate('2026-11-17'))
        self.assertFalse(self._euro_rate('2026-11-18'))

    def test_euro_has_no_buying_rate_and_a_stale_one_is_cleared(self):
        self.Rate.create({'name': '2026-11-16', 'currency_id': self.euro.id, 'rate': 0.5, 'original_rate': 2.0,
                          'rate_2': 0.4, 'original_rate_2': 2.5})
        self._run_euro('2026-11-16', '2026-11-16')
        rate = self._euro_rate('2026-11-16')
        self.assertEqual(len(rate), 1)
        self.assertEqual((rate.rate_2, rate.original_rate_2), (0.0, 0.0))

    def test_inactive_euro_is_not_loaded(self):
        self.euro.active = False
        self._run_euro('2026-11-16', '2026-11-16')
        self.assertFalse(self._euro_rate('2026-11-16'))

    def test_dollar_keeps_both_rates(self):
        with patch.object(type(self.Rate), '_bccr_get_series', autospec=True,
                          side_effect=lambda rate, *args: self._fake_series(*args)):
            self.Rate._cron_update('2026-11-16', '2026-11-16')
        rate = self.Rate.search([('currency_id', '=', self.env.ref('base.USD').id), ('name', '=', '2026-11-16')])
        self.assertEqual((rate.original_rate, rate.original_rate_2), (448.0, 438.0))
        self.assertFalse(self._euro_rate('2026-11-16'), "the daily cron no longer loads the euro")
