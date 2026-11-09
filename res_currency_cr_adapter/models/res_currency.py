# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.res_currency_cr_adapter.tools.bccr_api import BccrApi

_logger = logging.getLogger(__name__)

# Odoo 20 converts with the last rate dated before the document (odoo/odoo@cba671d), so rates are stored a day early
RATE_DATE_OFFSET = timedelta(days=1)


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    show_buying_rate = fields.Boolean(compute='_compute_show_buying_rate')

    @api.depends('rate_ids.buying_rate')
    @api.depends_context('company')
    def _compute_show_buying_rate(self):
        # Any currency with buying rates shows their columns, whatever their source
        groups = self.env['res.currency.rate']._read_group(
            [
                ('currency_id', 'in', self.ids),
                ('buying_rate', '!=', 0),
                '|',
                ('company_id', '=', False),
                ('company_id', 'parent_of', self.env.company.id),
            ],
            groupby=['currency_id'],
        )
        currencies_with_buying_rate = {currency for currency, in groups}
        for currency in self:
            currency.show_buying_rate = currency._origin in currencies_with_buying_rate


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    # Odoo's rate columns, labelled as the selling rate next to the buying rate
    selling_company_rate = fields.Float(
        string='Selling Company Rate',
        related='company_rate',
        readonly=False,
        digits=0,
    )
    selling_inverse_company_rate = fields.Float(
        string='Selling Inverse Company Rate',
        related='inverse_company_rate',
        readonly=False,
        digits=0,
    )

    # Costa Rica also publishes a buying rate, stored and shown like Odoo's rate
    buying_rate = fields.Float(
        string='Technical Buying Rate',
        digits=0,
        aggregator='avg',
        help="Buying rate, expressed like the Technical Rate.",
    )
    buying_company_rate = fields.Float(
        string='Buying Company Rate',
        digits=0,
        compute='_compute_buying_company_rate',
        inverse='_inverse_buying_company_rate',
        aggregator='avg',
        help="Buying rate, expressed like Unit/Base.",
    )
    buying_inverse_company_rate = fields.Float(
        string='Buying Inverse Company Rate',
        digits=0,
        compute='_compute_buying_inverse_company_rate',
        inverse='_inverse_buying_inverse_company_rate',
        aggregator='avg',
        help="Buying rate, expressed like Base/Unit.",
    )

    @api.depends('buying_rate', 'currency_id', 'company_id')
    @api.depends_context('company')
    def _compute_buying_company_rate(self):
        last_rate = self._get_last_rates_for_companies(self.company_id | self.env.company.root_id)
        for currency_rate in self:
            company = currency_rate.company_id or self.env.company.root_id
            currency_rate.buying_company_rate = currency_rate.buying_rate / last_rate[company]

    @api.onchange('buying_company_rate')
    def _inverse_buying_company_rate(self):
        last_rate = self._get_last_rates_for_companies(self.company_id | self.env.company.root_id)
        for currency_rate in self:
            company = currency_rate.company_id or self.env.company.root_id
            currency_rate.buying_rate = currency_rate.buying_company_rate * last_rate[company]

    @api.depends('buying_company_rate')
    def _compute_buying_inverse_company_rate(self):
        for currency_rate in self:
            buying_company_rate = currency_rate.buying_company_rate
            currency_rate.buying_inverse_company_rate = 1 / buying_company_rate if buying_company_rate else 0

    @api.onchange('buying_inverse_company_rate')
    def _inverse_buying_inverse_company_rate(self):
        for currency_rate in self:
            buying_inverse_company_rate = currency_rate.buying_inverse_company_rate
            currency_rate.buying_company_rate = 1 / buying_inverse_company_rate if buying_inverse_company_rate else 0

    @api.model
    def _cron_update(self, first_date=False, last_date=False):
        """Load the BCCR rates from first_date to last_date, by default today's."""
        bccr_token = self.env['ir.config_parameter'].sudo().get_str('bccr_token')

        # The token turns the update on: without one there is nothing to do yet
        if not bccr_token:
            _logger.info("No BCCR token configured, the exchange rate is not updated")
            return

        first_date = first_date or fields.Date.today()
        last_date = last_date or first_date

        # Odoo deactivates a cron after repeated failures, so a BCCR outage is only logged
        try:
            rates = BccrApi(self.env, bccr_token).get_rates(first_date, last_date)
        except UserError as e:
            _logger.error("Exchange rate update failed: %s", e)
            return

        currency = self.env.ref('base.USD')
        for date, (selling, buying) in rates.items():
            rate_date = date - RATE_DATE_OFFSET

            # Odoo stores dollars per colón, the inverse of the colones per dollar the BCCR publishes
            vals = {'rate': 1 / selling, 'buying_rate': 1 / buying}
            existing_rate = self.search([('name', '=', rate_date), ('currency_id', '=', currency.id)], limit=1)
            if existing_rate:
                existing_rate.write(vals)
            else:
                self.create({**vals, 'name': rate_date, 'currency_id': currency.id})

        _logger.info("BCCR exchange rates loaded for %s to %s", min(rates), max(rates))
