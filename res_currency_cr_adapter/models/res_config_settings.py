# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bccr_token = fields.Char(
        string="BCCR access token",
        config_parameter='bccr_token',
        help="Bearer token generated on the Indicadores Economicos site "
             "under Mi Perfil -> Generar token. It is not the subscription "
             "token of the old SOAP web service.")
