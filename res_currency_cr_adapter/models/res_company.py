# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_cr_update_rates = fields.Boolean(string='Update Exchange Rates')
    l10n_cr_last_rate_date = fields.Date(string='Last Exchange Rate Date', readonly=True)
    l10n_cr_bccr_token = fields.Char(string='BCCR Token', groups='base.group_system')

    def _l10n_cr_get_rated_currency(self):
        """Currency the BCCR rates for this company: the dollar for a colón company, the colón for a dollar one."""
        self.ensure_one()
        Currency = self.env['res.currency']
        if self.account_fiscal_country_id.code != 'CR':
            return Currency
        return {'CRC': self.env.ref('base.USD'), 'USD': self.env.ref('base.CRC')}.get(self.currency_id.name, Currency)
