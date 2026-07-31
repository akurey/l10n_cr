
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
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res.update(
            bccr_username=get_param('bccr_username'),
            bccr_email=get_param('bccr_email'),
            bccr_token=get_param('bccr_token'),
            exchange_source=get_param('exchange_source') or 'disabled',
        )
        return res

    @api.model
    def set_values(self):
        super().set_values()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('bccr_username', self.bccr_username)
        set_param('bccr_email', self.bccr_email)
        set_param('bccr_token', self.bccr_token)
        set_param('exchange_source', self.exchange_source)
