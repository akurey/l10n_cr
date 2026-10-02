from odoo import fields, models


class ValidateAccountMove(models.TransientModel):
    _inherit = 'validate.account.move'

    def validate_move(self):
        """Post Costa Rica electronic documents through action_post.

        Core's "Confirm Entries" dialog (shown for abnormal amounts/dates, and by the list
        view's Confirm Entries action) posts with _post() directly. That skips
        AccountInvoiceElectronic.action_post, so the document would be posted without its
        tipo_documento, consecutive and Hacienda key. Moves core would post right away go
        through action_post instead, with abnormal detection off since the user has just
        confirmed. Moves core would only schedule (future-dated without "Force") or skip
        (hash-locked without "Force Hash") are left to core, as are journal entries and
        companies with electronic invoicing disabled.
        """
        today = fields.Date.context_today(self)
        cr_moves = self.move_ids.filtered(
            lambda m: m.state == 'draft'
            and m.move_type != 'entry'
            and m.company_id.frm_ws_ambiente != 'disabled'
            and (self.force_post or (m.date or m.invoice_date or today) <= today)
            and (self.force_hash or not m.restrict_mode_hash_table)
        )
        if not cr_moves:
            return super().validate_move()

        if self.ignore_abnormal_amount:
            self.abnormal_amount_partner_ids.ignore_abnormal_invoice_amount = True
        if self.ignore_abnormal_date:
            self.abnormal_date_partner_ids.ignore_abnormal_invoice_date = True
        if self.force_post:
            cr_moves.auto_post = 'no'
        result = cr_moves.with_context(disable_abnormal_invoice_detection=True).action_post()

        rest = self.move_ids - cr_moves
        if rest:
            self.move_ids = rest
            return super().validate_move()
        return result or {'type': 'ir.actions.act_window_close'}
