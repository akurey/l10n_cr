from odoo import models


class AccountInvoiceSend(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    def action_send_and_print(self, allow_fallback_pdf=False):
        self.ensure_one()
        move = self.move_id
        if move.company_id.frm_ws_ambiente != 'disabled' and move.state_tributacion == 'aceptado':
            move.action_invoice_sent_mass()
            return {'type': 'ir.actions.act_window_close'}
        return super().action_send_and_print(allow_fallback_pdf=allow_fallback_pdf)
