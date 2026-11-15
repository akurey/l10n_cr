from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cr_einvoice_requested = fields.Boolean(
        string="Electronic Invoice", compute='_compute_cr_einvoice_requested', store=True, readonly=False,
        copy=False, tracking=True,
        help="The customer asked for an electronic invoice (FE), in their name or a third party's. Otherwise the "
             "order is invoiced with an electronic ticket (TE).")
    cr_einvoice_partner_id = fields.Many2one(
        'res.partner', string="Invoice in the Name of", copy=False,
        help="A third party (another person or a company) the customer asked to invoice. Empty: the customer.")
    cr_einvoice_choice_made = fields.Boolean(
        copy=False, help="Technical: the customer chose explicitly, so a new billing address keeps their choice.")
    cr_einvoice_verified = fields.Boolean(
        string="Billing Data Checked", compute='_compute_cr_einvoice_verified', store=True, readonly=False,
        copy=False,
        help="The customer's identification was confirmed by Hacienda's registry, or is a company's data kept "
             "by the sales team. If not, check it before invoicing, then tick this box.")

    @api.depends('partner_invoice_id')
    def _compute_cr_einvoice_requested(self):
        # Taxpayers (registered with an economic activity) get the FE by default, until they choose
        # otherwise for this order; anyone can ask for it.
        for order in self:
            if not order.cr_einvoice_choice_made:
                partner = order.partner_invoice_id
                order.cr_einvoice_requested = bool(partner) and partner._cr_einvoice_ready() \
                    and bool(partner.commercial_partner_id.activity_id)
            else:
                order.cr_einvoice_requested = order.cr_einvoice_requested

    @api.depends('partner_invoice_id.commercial_partner_id.cr_einvoice_checked',
                 'partner_invoice_id.commercial_partner_id.is_company', 'cr_einvoice_partner_id.cr_einvoice_checked')
    def _compute_cr_einvoice_verified(self):
        for order in self:
            if order.cr_einvoice_partner_id:
                order.cr_einvoice_verified = order.cr_einvoice_partner_id.cr_einvoice_checked
                continue
            commercial = order.partner_invoice_id.commercial_partner_id
            order.cr_einvoice_verified = commercial.is_company or commercial.cr_einvoice_checked

    def _prepare_invoice(self):
        """Website orders follow the customer's choice: FE in their name or a third party's, or TE. The FE
        is issued to a commercial partner, which holds the identification type, number and activities (a
        contact or an invoice address only shares the number). Orders entered in the backend keep
        cr_electronic_invoice's own choice."""
        invoice_vals = super()._prepare_invoice()
        if not self.website_id:
            return invoice_vals
        commercial = self.partner_invoice_id.commercial_partner_id
        # The FE goes to the third party the customer named, or to the customer's commercial partner.
        receptor = self.cr_einvoice_partner_id or commercial
        if commercial.export:
            invoice_vals['tipo_documento'] = 'FEE'
        elif self.cr_einvoice_requested and receptor._cr_einvoice_ready():
            invoice_vals.update(tipo_documento='FE', partner_id=receptor.id)
        else:
            invoice_vals['tipo_documento'] = 'TE'
        return invoice_vals
