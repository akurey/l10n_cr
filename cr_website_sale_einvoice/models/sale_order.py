from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cr_einvoice_requested = fields.Boolean(
        string="Electronic Invoice", compute='_compute_cr_einvoice_requested', store=True, readonly=False,
        copy=False, tracking=True,
        help="The customer asked for an electronic invoice (FE) in their name. Otherwise the order is invoiced "
             "with an electronic ticket (TE).")
    cr_einvoice_verified = fields.Boolean(
        string="Checked with Hacienda", copy=False,
        help="The customer's identification was found in Hacienda's registry when they asked for the "
             "electronic invoice. If not, check their data before invoicing.")

    @api.depends('partner_invoice_id')
    def _compute_cr_einvoice_requested(self):
        # A customer who gave their data before gets the electronic invoice again by default.
        for order in self:
            partner = order.partner_invoice_id
            order.cr_einvoice_requested = bool(partner) and partner._cr_einvoice_ready()

    def _prepare_invoice(self):
        """Website orders follow the customer's choice. Orders entered in the backend, and export
        customers (FEE), keep cr_electronic_invoice's own choice."""
        invoice_vals = super()._prepare_invoice()
        if self.website_id and not self.partner_invoice_id.commercial_partner_id.export:
            ready = self.cr_einvoice_requested and self.partner_invoice_id._cr_einvoice_ready()
            invoice_vals['tipo_documento'] = 'FE' if ready else 'TE'
        return invoice_vals
