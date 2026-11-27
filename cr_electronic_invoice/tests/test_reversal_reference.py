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

    def _move(self, move_type, **vals):
        return self.env['account.move'].new({'move_type': move_type, **vals})

    def test_reference_values_follow_the_reversed_document(self):
        for tipo, document in (('FE', '01'), ('TE', '04')):
            vals = self._move('out_invoice', tipo_documento=tipo)._cr_reversal_reference_vals(self.code_06)
            self.assertEqual(self.env['reference.document'].browse(vals['reference_document_id']).code, document,
                             tipo)
            self.assertEqual(vals['reference_code_id'], self.code_06.id, tipo)

    def test_a_credit_note_without_the_wizard_refers_to_what_it_reverses(self):
        invoice = self._move('out_invoice', tipo_documento='TE')
        note = self._move('out_refund')
        note.reversed_entry_id = invoice
        note._cr_refer_to_reversed_entry()
        self.assertEqual(note.invoice_id, invoice)
        # posting checks reference data whenever there is a referenced document: no code means a clear error
        self.assertFalse(note.reference_code_id)

    def test_what_the_wizard_or_the_user_set_is_kept(self):
        invoice, other = self._move('out_invoice'), self._move('out_invoice')
        note = self._move('out_refund')
        note.update({'reversed_entry_id': invoice, 'invoice_id': other})
        note._cr_refer_to_reversed_entry()
        self.assertEqual(note.invoice_id, other)

    def test_only_customer_credit_notes(self):
        bill = self._move('in_invoice')
        vendor_note = self._move('in_refund')
        vendor_note.reversed_entry_id = bill
        vendor_note._cr_refer_to_reversed_entry()
        self.assertFalse(vendor_note.invoice_id, "a vendor's credit note comes with the vendor's own XML")
