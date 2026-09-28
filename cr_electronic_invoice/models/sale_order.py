from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    additional_contact_id = fields.Many2one(
        "res.partner", string="Additional Contact", tracking=True,
        help="Contact that receives the quotation and order emails in addition to the customer. "
             "It is carried over to the invoices created from this order.")

    def _message_add_default_recipients(self):
        # Same hook as account.move: the sale mail templates use use_default_to=True.
        results = super()._message_add_default_recipients()
        for order in self:
            if order.additional_contact_id:
                results[order.id]['partners'] |= order.additional_contact_id
        return results

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['additional_contact_id'] = self.additional_contact_id.id
        return invoice_vals
