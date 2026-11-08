# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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
            bccr_token=get_str('bccr_token'),
        )
        return res

    @api.model
    def set_values(self):
        super().set_values()
        set_str = self.env['ir.config_parameter'].sudo().set_str
        set_str('bccr_token', self.bccr_token)
