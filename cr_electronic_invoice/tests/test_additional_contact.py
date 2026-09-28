from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAdditionalContact(TransactionCase):
    """The additional contact of a customer invoice or a quotation receives its emails too,
    and a quotation hands it on to the invoices created from it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Partner = cls.env['res.partner']
        cls.customer = Partner.create({'name': 'Customer', 'email': 'customer@example.com'})
        cls.contact = Partner.create({'name': 'Accounting', 'email': 'accounting@example.com'})
        cls.product = cls.env['product.product'].create({
            'name': 'Consulting',
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 100.0,
        })

    def _create_move(self, move_type, **vals):
        return self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.customer.id,
            'invoice_date': '2026-01-01',
            'invoice_line_ids': [Command.create({'product_id': self.product.id, 'price_unit': 100.0})],
            **vals,
        })

    def _default_partner_ids(self, records):
        return records._message_get_default_recipients()[records.id]['partner_ids']

    def test_invoice_default_recipients(self):
        invoice = self._create_move('out_invoice', additional_contact_id=self.contact.id)
        self.assertEqual(self._default_partner_ids(invoice), [self.customer.id, self.contact.id])

        credit_note = self._create_move('out_refund', additional_contact_id=self.contact.id)
        self.assertIn(self.contact.id, self._default_partner_ids(credit_note))

    def test_invoice_without_contact_unchanged(self):
        invoice = self._create_move('out_invoice')
        self.assertEqual(self._default_partner_ids(invoice), [self.customer.id])

    def test_vendor_bill_ignores_contact(self):
        bill = self._create_move('in_invoice', additional_contact_id=self.contact.id)
        self.assertNotIn(self.contact.id, self._default_partner_ids(bill))

    def test_invoice_template_mail(self):
        """The path taken once Hacienda accepts the invoice: template.send_mail()."""
        invoice = self._create_move('out_invoice', additional_contact_id=self.contact.id)
        template = self.env.ref('account.email_template_edi_invoice')
        mail = self.env['mail.mail'].browse(template.send_mail(invoice.id))
        self.assertEqual(mail.recipient_ids, self.customer | self.contact)

    def test_invoice_send_wizard_partners(self):
        """The path taken by the invoice "Send" wizard."""
        invoice = self._create_move('out_invoice', additional_contact_id=self.contact.id)
        template = self.env.ref('account.email_template_edi_invoice')
        partners = self.env['account.move.send']._get_default_mail_partner_ids(invoice, template, 'en_US')
        self.assertEqual(partners, self.customer | self.contact)

    def test_invoice_message_post(self):
        """Portal notifications read a single customer from _mail_get_partners, so the
        contact must not end up there."""
        invoice = self._create_move('out_invoice', additional_contact_id=self.contact.id)
        invoice.message_post(body='Hello', message_type='comment', partner_ids=self.customer.ids)

    def test_sale_order_recipients_and_invoice(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'additional_contact_id': self.contact.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1})],
        })
        self.assertEqual(self._default_partner_ids(order), [self.customer.id, self.contact.id])

        template = self.env.ref('sale.email_template_edi_sale')
        mail = self.env['mail.mail'].browse(template.send_mail(order.id))
        self.assertEqual(mail.recipient_ids, self.customer | self.contact)

        order.action_confirm()
        invoice = order._create_invoices()
        self.assertEqual(invoice.additional_contact_id, self.contact)
