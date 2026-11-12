# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.res_currency_cr_adapter.models.res_currency import RATE_DATE_OFFSET


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_cr_update_rates = fields.Boolean(string='Update Exchange Rates')
    l10n_cr_bccr_token = fields.Char(string='BCCR Token', groups='base.group_system')
    l10n_cr_last_update_failed = fields.Boolean(string='Last Exchange Rate Update Failed', readonly=True)

    def _l10n_cr_get_rated_currency(self):
        """Currency the BCCR rates for this company: the dollar for a colón company, the colón for a dollar one."""
        self.ensure_one()
        Currency = self.env['res.currency']
        if self.account_fiscal_country_id.code != 'CR':
            return Currency
        return {'CRC': self.env.ref('base.USD'), 'USD': self.env.ref('base.CRC')}.get(self.currency_id.name, Currency)

    def _l10n_cr_get_rates_ready_until(self):
        """Last date whose documents have a rate of the currency the BCCR rates, or False without any."""
        self.ensure_one()
        last_rate = self.env['res.currency.rate'].search([
            ('company_id', 'in', [False, self.id]),
            ('currency_id', '=', self._l10n_cr_get_rated_currency().id),
        ], order='name desc', limit=1)
        return last_rate and last_rate.name + RATE_DATE_OFFSET
