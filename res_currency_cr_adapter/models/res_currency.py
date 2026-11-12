# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Odoo 20 converts with the last rate dated before the document (odoo/odoo@cba671d), so rates are stored a day early
RATE_DATE_OFFSET = timedelta(days=1)
# The BCCR's calendar is Costa Rica's, whatever the user's or the server's timezone
CR_TZ = 'America/Costa_Rica'


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    show_buying_rate = fields.Boolean(compute='_compute_show_buying_rate')

    @api.depends_context('company')
    def _compute_show_buying_rate(self):
        # Rates are stored on the root company, which its branches share
        rated_currency = self.env.company.root_id._l10n_cr_get_rated_currency()
        for currency in self:
            currency.show_buying_rate = currency._origin == rated_currency

    def action_view_rates(self):
        """Odoo's rate list, without the buying columns for a currency that doesn't use them."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('base.act_view_currency_rates')
        action['domain'] = [('currency_id', '=', self.id)]
        action['context'] = {'default_currency_id': self.id, 'hide_buying_rate': not self.show_buying_rate}
        return action


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    currency_show_buying_rate = fields.Boolean(related='currency_id.show_buying_rate')
    # Rates that existed before this field are taken as entered manually, since nothing tells them apart
    l10n_cr_source = fields.Selection(
        selection=[('manual', 'Entered manually'), ('bccr', 'BCCR')],
        string='Source',
        required=True,
        default='manual',
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

    @api.depends('buying_rate', 'name', 'currency_id', 'company_id', 'currency_id.rate_ids.buying_rate')
    @api.depends_context('company')
    def _compute_buying_company_rate(self):
        last_rate = self._get_last_rates_for_companies(self.company_id | self.env.company.root_id)
        for currency_rate in self:
            company = currency_rate.company_id or self.env.company.root_id
            buying_rate = currency_rate.buying_rate or currency_rate._get_latest_rate().buying_rate
            currency_rate.buying_company_rate = buying_rate / last_rate[company]

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

    def write(self, vals):
        # A rate changed by hand is no longer the BCCR's
        if {'rate', 'buying_rate'} & vals.keys() and 'l10n_cr_source' not in vals:
            vals = {**vals, 'l10n_cr_source': 'manual'}
        return super().write(vals)

    @api.model
    def _cron_update(self, first_date=False, last_date=False):
        """Load the BCCR rates from first_date to last_date for each company that updates them."""
        companies = self.env['res.company'].sudo().search([
            ('parent_id', '=', False),
            ('l10n_cr_update_rates', '=', True),
            ('l10n_cr_bccr_token', '!=', False),
        ]).filtered(lambda company: company._l10n_cr_get_rated_currency())
        if not companies:
            _logger.info("No company updates its exchange rates from the BCCR")
            return
        companies._l10n_cr_update_rates(first_date, last_date)

    def _l10n_cr_store_rates(self, company, rates, replace=False):
        """Store the BCCR's {date: (selling, buying)} for the company, each rate the day before it applies.

        :param replace: whether rates entered manually are also overwritten, not only the BCCR's
        """
        currency = company._l10n_cr_get_rated_currency()
        rate_dates = [date - RATE_DATE_OFFSET for date in rates]
        existing_rates = self.search([
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
            ('name', 'in', rate_dates),
        ]).grouped('name')

        for date, (selling, buying) in rates.items():
            rate_date = date - RATE_DATE_OFFSET
            # Odoo rates a currency against the company's: a colón company stores dollars per colón, the inverse
            # of the colones per dollar the BCCR publishes, and a dollar company stores the BCCR's values as they are
            if company.currency_id.name == 'CRC':
                vals = {'rate': 1 / selling, 'buying_rate': 1 / buying, 'l10n_cr_source': 'bccr'}
            else:
                vals = {'rate': selling, 'buying_rate': buying, 'l10n_cr_source': 'bccr'}
            if rate_date in existing_rates:
                existing_rate = existing_rates[rate_date]
                if replace or existing_rate.l10n_cr_source == 'bccr':
                    existing_rate.write(vals)
            else:
                self.create({**vals, 'name': rate_date, 'currency_id': currency.id, 'company_id': company.id})

        company.write({'l10n_cr_last_update': fields.Datetime.now(), 'l10n_cr_last_update_failed': False})
        _logger.info("BCCR exchange rates loaded for %s from %s to %s", company.name, min(rates), max(rates))
