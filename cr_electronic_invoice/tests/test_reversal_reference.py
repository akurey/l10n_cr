from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestReversalReference(TransactionCase):
    """A credit note made outside the reversal wizard (a Point of Sale refund) refers to the document it reverses:
    without InformacionReferencia Hacienda rejects it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.code_06 = cls.env.ref('cr_electronic_invoice.ReferenceCode_6')
        cls.env['account.journal'].create({'name': "Ventas referencia", 'type': 'sale', 'code': 'TREF'})
        cls.customer = cls.env['res.partner'].create({'name': "Cliente de prueba"})

    def _move(self, move_type, **vals):
        return self.env['account.move'].new({'move_type': move_type, **vals})

    def test_reference_values_follow_the_reversed_document(self):
        for tipo, document in (('FE', '01'), ('TE', '04')):
            vals = self._move('out_invoice', tipo_documento=tipo)._cr_reversal_reference_vals(self.code_06)
            self.assertEqual(self.env['reference.document'].browse(vals['reference_document_id']).code, document,
                             tipo)
            self.assertEqual(vals['reference_code_id'], self.code_06.id, tipo)

    def _document(self, tipo, amount, move_type='out_invoice'):
        return self.env['account.move'].create({
            'move_type': move_type, 'tipo_documento': tipo, 'partner_id': self.customer.id,
            'invoice_line_ids': [Command.create({'name': "Vino", 'quantity': 1, 'price_unit': amount,
                                                 'tax_ids': [Command.clear()]})]})

    def _refund_of(self, document, amount):
        """A credit note as Odoo makes it outside the wizard (the Point of Sale refund of an invoiced order,
        without cr_electronic_invoice_pos): only reversed_entry_id."""
        note = self._document(False, amount, 'out_refund')
        note.reversed_entry_id = document
        note._cr_refer_to_reversed_entry()
        return note

    def test_a_credit_note_without_the_wizard_refers_to_what_it_reverses(self):
        """The refund of a whole ticket: it refers to it as a ticket (04) and annuls it (01), so posting finds
        complete reference data instead of stopping at «Incomplete reference data for credit note»."""
        ticket = self._document('TE', 9500)
        note = self._refund_of(ticket, 9500)
        self.assertEqual(note.invoice_id, ticket)
        self.assertEqual(note.reference_document_id.code, '04')
        self.assertEqual(note.reference_code_id.code, '01', "the whole amount: it annuls the ticket")

    def test_a_partial_refund_corrects_the_amount(self):
        invoice = self._document('FE', 9500)
        note = self._refund_of(invoice, 4750)
        self.assertEqual(note.reference_document_id.code, '01', "an electronic invoice")
        self.assertEqual(note.reference_code_id.code, '02', "part of the amount: it corrects it")

    def test_a_reference_code_already_set_is_kept(self):
        """cr_electronic_invoice_pos sets 06 «Devolución de mercancía» on its refunds: it stays."""
        note = self._document(False, 9500, 'out_refund')
        note.update({'reversed_entry_id': self._document('TE', 9500), 'reference_code_id': self.code_06})
        note._cr_refer_to_reversed_entry()
        self.assertEqual(note.reference_code_id, self.code_06)

    def test_what_the_wizard_or_the_user_set_is_kept(self):
        invoice, other = self._move('out_invoice'), self._move('out_invoice')
        note = self._move('out_refund')
        note.update({'reversed_entry_id': invoice, 'invoice_id': other})
        note._cr_refer_to_reversed_entry()
        self.assertEqual(note.invoice_id, other)
        self.assertFalse(note.reference_code_id, "it refers to another document: the user completes it")

    def test_only_customer_credit_notes(self):
        bill = self._move('in_invoice')
        vendor_note = self._move('in_refund')
        vendor_note.reversed_entry_id = bill
        vendor_note._cr_refer_to_reversed_entry()
        self.assertFalse(vendor_note.invoice_id, "a vendor's credit note comes with the vendor's own XML")
