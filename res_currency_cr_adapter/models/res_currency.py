# copyright  2018 Carlos Wong, Akurey S.A.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Odoo 20 converts with the last rate dated before the document (odoo/odoo@cba671d), so rates are stored a day early
RATE_DATE_OFFSET = timedelta(days=1)
# The BCCR's calendar is Costa Rica's, whatever the user's or the server's timezone
CR_TZ = 'America/Costa_Rica'
# The BCCR publishes tomorrow's rate around 17:30, and the update first runs at 18:00
UPDATE_TIME = time(18)
RATES_STATUSES = [
    ('error', 'Failed'),
    ('ready', 'Ready'),
    ('late', 'Tomorrow missing'),
    ('today', 'Ready for today'),
    ('missing', 'Missing'),
]
# A failed or early update is retried every hour until the working day starts, in Costa Rica
RETRY_INTERVAL = timedelta(hours=1)
RETRY_UNTIL = time(6)


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    show_buying_rate = fields.Boolean(compute='_compute_show_buying_rate')
    # The update's status, also for accounting administrators, who can't open Settings
    l10n_cr_show_update = fields.Boolean(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_status = fields.Selection(selection=RATES_STATUSES, compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_ready_until = fields.Date(compute='_compute_l10n_cr_rates_status')
    l10n_cr_rates_entered_manually = fields.Boolean(compute='_compute_l10n_cr_rates_status')
    l10n_cr_last_update = fields.Char(compute='_compute_l10n_cr_rates_status')
    l10n_cr_retry_at = fields.Char(compute='_compute_l10n_cr_rates_status')

    @api.depends_context('company')
    def _compute_show_buying_rate(self):
        # Rates are stored on the root company, which its branches share
        rated_currency = self.env.company.root_id._l10n_cr_get_rated_currency()
        for currency in self:
            currency.show_buying_rate = currency._origin == rated_currency

    @api.depends('show_buying_rate')
    @api.depends_context('company')
    def _compute_l10n_cr_rates_status(self):
        # The token is only readable by Settings administrators
        company = self.env.company.root_id.sudo()
        status = company.l10n_cr_update_rates and company.l10n_cr_bccr_token and company._l10n_cr_get_rates_status()
        for currency in self:
            show_update = bool(status) and currency.show_buying_rate
            currency.l10n_cr_show_update = show_update
            currency.l10n_cr_rates_status = show_update and status['status']
            currency.l10n_cr_rates_ready_until = show_update and status['ready_until']
            currency.l10n_cr_rates_entered_manually = show_update and status['entered_manually']
            currency.l10n_cr_last_update = show_update and status['last_update']
            currency.l10n_cr_retry_at = show_update and status['retry_at']

    def _compute_current_rate(self):
        super()._compute_current_rate()
        company = self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company
        rated_currency = company.root_id._l10n_cr_get_rated_currency()
        for currency in self:
            if currency._origin == rated_currency and currency.rate_date:
                currency.rate_date += RATE_DATE_OFFSET

    def action_view_rates(self):
        """Odoo's rate list, without the buying columns for a currency that doesn't use them."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('base.act_view_currency_rates')
        action['domain'] = [('currency_id', '=', self.id)]
        action['context'] = {'default_currency_id': self.id, 'hide_buying_rate': not self.show_buying_rate}
        return action

    def action_l10n_cr_update_rates(self):
        # Whoever may enter rates by hand may load them, with a token only Settings administrators can read
        self.env['res.currency.rate'].check_access('create')
        return self.env.company.root_id.sudo()._l10n_cr_action_update_rates()

    def action_l10n_cr_open_rate_load_wizard(self):
        self.env['res.currency.rate'].check_access('create')
        return self.env.company.root_id._l10n_cr_action_open_rate_load_wizard()


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    currency_show_buying_rate = fields.Boolean(related='currency_id.show_buying_rate')
    # The rated currency's rates are shown with the BCCR's date, the day after the one Odoo applies them from
    l10n_cr_date = fields.Date(
        string='BCCR Date',
        compute='_compute_l10n_cr_date',
        inverse='_inverse_l10n_cr_date',
        help="Day this rate applies to documents, as the BCCR dates it.",
    )
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

    @api.depends('name')
    def _compute_l10n_cr_date(self):
        for currency_rate in self:
            currency_rate.l10n_cr_date = currency_rate.name and currency_rate.name + RATE_DATE_OFFSET

    @api.onchange('currency_id')
    def _onchange_currency_id_l10n_cr_date(self):
        if not self._origin and self.currency_show_buying_rate and self.name == fields.Date.context_today(self):
            self.name -= RATE_DATE_OFFSET

    def _inverse_l10n_cr_date(self):
        for currency_rate in self.filtered('l10n_cr_date'):
            currency_rate.name = currency_rate.l10n_cr_date - RATE_DATE_OFFSET

    @api.model_create_multi
    def create(self, vals_list):
        # Set Odoo's date before creating, as the default one could clash with an existing rate
        for vals in vals_list:
            if vals.get('l10n_cr_date'):
                vals['name'] = fields.Date.to_date(vals.pop('l10n_cr_date')) - RATE_DATE_OFFSET
        return super().create(vals_list)

    def write(self, vals):
        # A rate changed by hand is no longer the BCCR's
        if {'rate', 'buying_rate'} & vals.keys() and 'l10n_cr_source' not in vals:
            vals = {**vals, 'l10n_cr_source': 'manual'}
        return super().write(vals)

    @api.model
    def _cron_update(self, first_date=False, last_date=False):
        """Load the BCCR rates from first_date to last_date for each company that updates them.

        Without dates, only the companies still missing the rate the update is after are loaded, and the update is
        retried every hour while any of them still misses it, until the morning.
        """
        companies = self.env['res.company'].sudo().search([
            ('parent_id', '=', False),
            ('l10n_cr_update_rates', '=', True),
            ('l10n_cr_bccr_token', '!=', False),
        ]).filtered(lambda company: company._l10n_cr_get_rated_currency())
        if not companies:
            _logger.info("No company updates its exchange rates from the BCCR")
            return
        if first_date or last_date:
            companies._l10n_cr_update_rates(first_date, last_date)
            return

        now = datetime.now(ZoneInfo(CR_TZ))
        # The evening update is after tomorrow's rate, and its retries after midnight are still after that same day's
        target_date = now.date() + timedelta(days=1) if now.time() >= RETRY_UNTIL else now.date()

        def is_missing(company):
            ready_until = company._l10n_cr_get_rates_ready_until()
            return not ready_until or ready_until < target_date

        companies.filtered(is_missing)._l10n_cr_update_rates()
        missing_companies = companies.filtered(is_missing)
        retry_at = now + RETRY_INTERVAL
        cron = self.env.ref('res_currency_cr_adapter.ir_cron_currency_rate_update', raise_if_not_found=False)
        if missing_companies and cron and retry_at <= datetime.combine(target_date, RETRY_UNTIL, now.tzinfo):
            cron.sudo()._trigger(retry_at.astimezone(timezone.utc).replace(tzinfo=None))
            _logger.info(
                "Exchange rates of %s still missing for %s, retrying at %s",
                ', '.join(missing_companies.mapped('name')), target_date, retry_at.strftime('%H:%M'))

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
