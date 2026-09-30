from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.api_facturae import credit_term_days


@tagged('post_install', '-at_install')
class TestCreditTermDays(TransactionCase):
    """<PlazoCredito> in the invoice XML takes the payment term's days. Odoo 17 renamed
    account.payment.term.line.days to nb_days, and reading the old name blocked validating
    customer invoices with "'account.payment.term.line' object has no attribute 'days'"."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Customer'})

    def _invoice(self, payment_term=False):
        return self.env['account.move'].new({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'invoice_payment_term_id': payment_term and payment_term.id,
        })

    def test_payment_term_days(self):
        term = self.env['account.payment.term'].create({
            'name': '30 días',
            'line_ids': [Command.create({'value': 'percent', 'value_amount': 100.0, 'nb_days': 30})],
        })
        self.assertEqual(credit_term_days(self._invoice(term)), 30)

    def test_no_payment_term(self):
        self.assertEqual(credit_term_days(self._invoice()), 0)
