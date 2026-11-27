from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.account_move import EXONERATION_FISCAL_POSITION

WINE = '2421200000100'  # CABYS: wine of fresh grapes
DELIVERY = '6803000000000'  # CABYS: local delivery services


@tagged('post_install', '-at_install')
class TestExoneration(TransactionCase):
    """A customer's authorization exonerates a percentage of the IVA, only on its CABYS codes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cr = cls.env.ref('base.cr')
        group = cls.env['account.tax.group'].create(
            {'name': "IVA de prueba", 'company_id': company.id, 'country_id': cr.id})
        cls.iva = cls.env['account.tax'].create({
            'name': "IVA de prueba", 'amount': 13, 'type_tax_use': 'sale', 'tax_code': '01', 'iva_tax_code': '08',
            'tax_group_id': group.id, 'company_id': company.id, 'country_id': cr.id,
        })
        cls.service = cls.env['account.tax'].create({
            'name': "Servicio de prueba", 'amount': 10, 'type_tax_use': 'sale', 'tax_code': 'service',
            'tax_group_id': group.id, 'company_id': company.id, 'country_id': cr.id,
        })
        cls.position = cls.env['account.fiscal.position'].create(
            {'name': EXONERATION_FISCAL_POSITION, 'company_id': company.id})
        cls.customer = cls.env['res.partner'].create({
            'name': "Cliente exonerado de prueba", 'percentage_exoneration': 50,
            'exoneration_cabys_codes': f"{WINE}\n2421100000000",
        })
        cls.wine = cls.env['product.product'].create(
            {'name': "Vino de prueba", 'cabys_code': WINE, 'taxes_id': [Command.set(cls.iva.ids)]})
        cls.delivery = cls.env['product.product'].create(
            {'name': "Envío de prueba", 'cabys_code': DELIVERY, 'taxes_id': [Command.set(cls.iva.ids)]})
        cls.env['account.journal'].create({'name': "Ventas exoneración", 'type': 'sale', 'code': 'TEXO'})
        cls.costa_rica, cls.group = cr, group

    def _exonerated(self, cabys, customer=None):
        return self.iva._cr_exonerated_for(customer or self.customer, cabys, self.position)

    def test_the_authorized_codes_are_read_from_any_layout(self):
        self.customer.exoneration_cabys_codes = f"{WINE}, 2421-1000-00000;\n 421300000100 texto"
        self.assertEqual(self.customer._cr_exoneration_cabys(), {WINE, '2421100000000', '0421300000100'})

    def test_half_of_the_iva_on_an_authorized_line(self):
        tax = self._exonerated(WINE)
        self.assertEqual((tax.amount, tax.percentage_exoneration, tax.has_exoneration, tax.tax_root),
                         (6.5, 6.5, True, self.iva))
        self.assertIn(self.position, tax.fiscal_position_ids, "offered only with the exoneration position")
        self.assertEqual(self._exonerated(WINE), tax, "created once per percentage")

    def test_in_full(self):
        self.customer.percentage_exoneration = 100
        tax = self._exonerated(WINE)
        self.assertEqual((tax.amount, tax.percentage_exoneration), (0, 13))

    def test_a_line_outside_the_authorization_keeps_the_full_iva(self):
        self.assertEqual(self._exonerated(DELIVERY), self.iva)
        self.assertEqual(self._exonerated(WINE)._cr_exonerated_for(self.customer, DELIVERY, self.position), self.iva,
                         "an exonerated tax goes back to the full IVA")
        self.assertEqual(self._exonerated(''), self.iva, "a line without CABYS")

    def test_a_percentage_out_of_range_exonerates_nothing(self):
        self.customer.percentage_exoneration = 130
        self.assertEqual(self._exonerated(WINE), self.iva)

    def test_another_exoneration_position_also_offers_the_tax(self):
        tax = self._exonerated(WINE)
        other = self.env['account.fiscal.position'].create({'name': EXONERATION_FISCAL_POSITION})
        self.assertEqual(self.iva._cr_exoneration_tax(50, other), tax)
        self.assertIn(other, tax.fiscal_position_ids)

    def test_a_price_with_the_iva_included_drops_with_the_exoneration(self):
        included = self.env['account.tax'].create({
            'name': "IVA incluido de prueba", 'amount': 13, 'type_tax_use': 'sale', 'tax_code': '01',
            'iva_tax_code': '08', 'price_include_override': 'tax_included', 'tax_group_id': self.group.id,
            'country_id': self.costa_rica.id,
        })
        self.wine.write({'lst_price': 113, 'taxes_id': [Command.set(included.ids)]})
        self.customer.percentage_exoneration = 100
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'invoice_line_ids': [Command.create({'product_id': self.wine.id})],
        })
        line = invoice.invoice_line_ids
        line._compute_tax_ids()
        line._compute_price_unit()
        self.assertEqual(line.tax_ids.amount, 0)
        self.assertAlmostEqual(line.price_unit, 100, 2, "the customer pays the price without the IVA")

    def test_no_authorized_code_exonerates_nothing(self):
        self.customer.exoneration_cabys_codes = False
        self.assertEqual(self._exonerated(WINE), self.iva)

    def test_other_taxes_are_kept(self):
        taxes = (self.iva | self.service)._cr_exonerated_for(self.customer, WINE, self.position)
        self.assertIn(self.service, taxes)
        self.assertEqual(len(taxes), 2)

    def test_an_invoice_line_follows_the_authorization(self):
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'invoice_line_ids': [Command.create({'product_id': self.wine.id}),
                                 Command.create({'product_id': self.delivery.id})],
        })
        wine, delivery = invoice.invoice_line_ids
        self.assertEqual(wine._get_computed_taxes().amount, 6.5)
        self.assertEqual(delivery._get_computed_taxes(), self.iva)

    def test_a_wrong_exoneration_is_reported_before_sending(self):
        full = self.iva._cr_exoneration_tax(100, self.position)
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'invoice_line_ids': [
                Command.create({'product_id': self.wine.id, 'name': "Vino", 'tax_ids': [Command.set(full.ids)]}),
                Command.create({'product_id': self.delivery.id, 'name': "Envío", 'tax_ids': [Command.set(full.ids)]}),
            ],
        })
        problems = invoice.with_context(lang='en_US')._cr_exoneration_problems()
        self.assertEqual(len(problems), 2)
        self.assertIn("50%", problems[0], "the customer's percentage changed: update the taxes")
        self.assertIn(DELIVERY, problems[1], "a CABYS the authorization does not cover")
        invoice.invoice_line_ids[0].tax_ids = self.iva
        invoice.invoice_line_ids[1].tax_ids = self.iva
        problems = invoice.with_context(lang='en_US')._cr_exoneration_problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("full IVA", problems[0], "an authorized line left with the full IVA (copied from an order)")
        invoice.invoice_line_ids[0].tax_ids = self._exonerated(WINE)
        self.assertEqual(invoice._cr_exoneration_problems(), [])
        self.customer.percentage_exoneration = 130
        self.assertEqual(len(invoice._cr_exoneration_problems()), 1, "said once, not once per line")

    def _refund(self, lines, reversed_entry=None):
        return self.env['account.move'].new({
            'move_type': 'out_refund', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'reversed_entry_id': reversed_entry,
            'invoice_line_ids': [Command.create({'product_id': product.id, 'name': product.name,
                                                 'tax_ids': [Command.set(taxes.ids)]}) for product, taxes in lines],
        })

    def test_a_credit_note_keeps_the_exoneration_of_its_invoice(self):
        """The authorization changed after the invoice (50 % then, 100 % now): the credit note keeps the invoice's."""
        half = self._exonerated(WINE)
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'invoice_line_ids': [Command.create({'product_id': self.wine.id, 'tax_ids': [Command.set(half.ids)]})],
        })
        self.customer.percentage_exoneration = 100
        self.assertEqual(self._refund([(self.wine, half)], invoice)._cr_exoneration_problems(), [])
        full = self.iva._cr_exoneration_tax(100, self.position)
        problems = self._refund([(self.wine, full)], invoice).with_context(lang='en_US')._cr_exoneration_problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("the invoice it reverses", problems[0])
        self.assertTrue(self._refund([(self.delivery, half)], invoice)._cr_exoneration_problems(),
                        "a CABYS the invoice did not exonerate")
        for taxes, why in ((self.iva, "the full IVA"), (self.env['account.tax'], "no IVA")):
            problems = self._refund([(self.wine, taxes)], invoice).with_context(lang='en_US')._cr_exoneration_problems()
            self.assertEqual(len(problems), 1, f"{why} where the invoice exonerated it")
            self.assertIn("must use the same tax", problems[0])

    def test_a_credit_note_of_its_own_follows_the_current_authorization(self):
        problems = self._refund([(self.delivery, self._exonerated(WINE))]).with_context(
            lang='en_US')._cr_exoneration_problems()
        self.assertEqual(len(problems), 1)
        self.assertIn(DELIVERY, problems[0], "a CABYS the authorization does not cover")
