
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    exchange_source = fields.Selection([
        ('disabled', 'Disabled'),
        ('bccr', 'BCCR (recommended)'),
        ('hacienda', 'Hacienda')
        ], default='disabled')

    # Kept for backwards compatibility: the retired SOAP service took the user
    # name as a request parameter, the SDDE REST API does not use it
    bccr_username = fields.Char(string="BCCR username")
    bccr_email = fields.Char(string="e-mail registered in the BCCR")
    bccr_token = fields.Char(
        string="BCCR access token",
        help="Bearer token generated on the Indicadores Economicos site "
             "under Mi Perfil -> Generar token. It is not the subscription "
             "token of the old SOAP web service.")

    @api.model
    def get_values(self):
        res = super().get_values()
        get_str = self.env['ir.config_parameter'].sudo().get_str
        res.update(
            bccr_username=get_str('bccr_username'),
            bccr_email=get_str('bccr_email'),
            bccr_token=get_str('bccr_token'),
            exchange_source=get_str('exchange_source') or 'disabled',
        )
        return res

    @api.model
    def set_values(self):
        super().set_values()
        set_str = self.env['ir.config_parameter'].sudo().set_str
        set_str('bccr_username', self.bccr_username)
        set_str('bccr_email', self.bccr_email)
        set_str('bccr_token', self.bccr_token)
        set_str('exchange_source', self.exchange_source)
