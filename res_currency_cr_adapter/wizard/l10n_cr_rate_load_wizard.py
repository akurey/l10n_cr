# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.res_currency_cr_adapter.models.res_company import CR_TZ


class L10nCrRateLoadWizard(models.TransientModel):
    _name = 'l10n_cr.rate.load.wizard'
    _description = "Load Past BCCR Exchange Rates"

    def _get_today(self):
        return datetime.now(ZoneInfo(CR_TZ)).date()

    company_id = fields.Many2one('res.company', required=True, readonly=True)
    date_from = fields.Date(string='From', required=True, default=lambda self: self._get_today().replace(day=1))
    date_to = fields.Date(string='To', required=True, default=lambda self: self._get_today())
    replace = fields.Boolean(
        string='Replace Rates',
        help="Also overwrite the rates entered manually in the period with the BCCR's. "
             "Missing days and rates from the BCCR are always loaded.",
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        today = self._get_today()
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(self.env._("The start date must be before the end date."))
            if wizard.date_to > today:
                raise ValidationError(self.env._("Past rates can be loaded up to today."))

    def action_load(self):
        self.ensure_one()
        # Whoever may enter rates by hand may load them, with a token only Settings administrators can read
        self.env['res.currency.rate'].check_access('create')
        if self.company_id not in self.env.user.company_ids.root_id:
            raise AccessError(self.env._("You can only load the exchange rates of your own companies."))
        return self.company_id.sudo()._l10n_cr_action_update_rates(self.date_from, self.date_to, self.replace)
