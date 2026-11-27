from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestRefundReference(TransactionCase):
    """The credit note of a refunded, invoiced order refers to the invoice or ticket it reverses: Odoo only links
    it (reversed_entry_id), and without InformacionReferencia Hacienda rejects the note."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        journal = cls.env['account.journal'].create({'name': 'Ventas POS prueba', 'type': 'sale', 'code': 'VPOSP'})
        cls.ticket = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': journal.id, 'tipo_documento': 'TE'})
        cls.code_01 = cls.env.ref('cr_electronic_invoice.ReferenceCode_1')
        cls.code_06 = cls.env.ref('cr_electronic_invoice.ReferenceCode_6')

    def test_a_refund_refers_to_the_ticket_as_a_return_of_goods(self):
        vals = self.env['pos.order'].new({})._cr_refund_reference(
            {'reversed_entry_id': self.ticket.id, 'ref': 'Reversal of: T0001'})
        self.assertEqual(vals['invoice_id'], self.ticket.id)
        self.assertEqual(vals['reference_code_id'], self.code_06.id)
        self.assertEqual(self.env['reference.document'].browse(vals['reference_document_id']).code, '04')
        self.assertEqual(vals['tipo_documento'], 'NC')
        self.assertEqual(vals['ref'], 'Reversal of: T0001', "Odoo's own values are kept")

    def test_the_order_s_own_reference_code_wins(self):
        order = self.env['pos.order'].new({'reference_code_id': self.code_01.id})
        vals = order._cr_refund_reference({'reversed_entry_id': self.ticket.id})
        self.assertEqual(vals['reference_code_id'], self.code_01.id)

    def test_an_order_that_reverses_nothing_is_left_alone(self):
        vals = {'move_type': 'out_invoice', 'ref': 'S0001'}
        self.assertEqual(self.env['pos.order'].new({})._cr_refund_reference(dict(vals)), vals)
