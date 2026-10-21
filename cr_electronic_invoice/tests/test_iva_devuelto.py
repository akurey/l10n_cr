from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestIvaDevuelto(TransactionCase):
    """Health services paid by card get their VAT back in an "IVA Devuelto" line. Creating
    that line used to fail ("invoice_id" is not an account.move.line field), and it was
    matched against the product.template id instead of its product.product."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.card = cls.env.ref('cr_electronic_invoice.PaymentMethods_2')
        cls.cash = cls.env.ref('cr_electronic_invoice.PaymentMethods_1')
        cls.tax_4 = cls.env['account.tax'].create({
            'name': 'IVA 4% salud', 'amount': 4.0, 'type_tax_use': 'sale', 'country_id': cls.env.company.account_fiscal_country_id.id,
        })
        cls.consult = cls.env['product.product'].create({
            'name': 'Consulta médica', 'iva_devuelto_tarjeta': True, 'taxes_id': [Command.set(cls.tax_4.ids)],
        })
        cls.medicine = cls.env['product.product'].create({
            'name': 'Medicamento', 'taxes_id': [Command.set(cls.tax_4.ids)],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Paciente'})
        cls.iva_devuelto = cls.env.ref('cr_electronic_invoice.product_iva_devuelto').product_variant_id

    def _invoice(self, payment_method):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'payment_methods_id': payment_method.id,
            'invoice_line_ids': [
                Command.create({'product_id': self.consult.id, 'quantity': 1, 'price_unit': 50000.0}),
                Command.create({'product_id': self.medicine.id, 'quantity': 1, 'price_unit': 10000.0}),
            ],
        })

    def _refund_lines(self, invoice):
        return invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.iva_devuelto)

    def test_card_payment_refunds_flagged_vat(self):
        invoice = self._invoice(self.card)
        invoice._update_iva_devuelto_line()
        line = self._refund_lines(invoice)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.price_unit, -2000.0)  # 4% of the consultation only
        self.assertEqual(line.product_id, self.iva_devuelto)

    def test_recomputing_replaces_the_line(self):
        invoice = self._invoice(self.card)
        invoice._update_iva_devuelto_line()
        invoice._update_iva_devuelto_line()
        self.assertEqual(len(self._refund_lines(invoice)), 1)

    def test_other_payment_method_has_no_refund(self):
        invoice = self._invoice(self.cash)
        invoice._update_iva_devuelto_line()
        self.assertFalse(self._refund_lines(invoice))

    def test_xml_matches_the_product_variant(self):
        self.assertEqual(self.env['account.move']._iva_devuelto_product()._name, 'product.product')
        self.assertEqual(self.env['account.move']._iva_devuelto_product(), self.iva_devuelto)
