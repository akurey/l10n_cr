from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae
from ..models.account_move import EXONERATION_FISCAL_POSITION

WINE = '2421200000100'  # CABYS: wine of fresh grapes
SERVICE = '6339100000000'  # CABYS of the test service, outside the authorization


@tagged('post_install', '-at_install')
class TestSummaryTotals(TransactionCase):
    """The ResumenFactura adds up as Hacienda checks it (-53: TotalVenta - TotalDescuentos = TotalVentaNeta),
    also when a line is exonerated in part and its amount has an odd last decimal."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cr = cls.env.ref('base.cr')
        company = cls.env.company
        group = cls.env['account.tax.group'].create(
            {'name': "IVA de prueba", 'company_id': company.id, 'country_id': cr.id})
        cls.iva = cls.env['account.tax'].create({
            'name': "IVA de prueba", 'amount': 13, 'type_tax_use': 'sale', 'tax_code': '01',
            'iva_tax_code': '08', 'tax_group_id': group.id,
            'company_id': company.id, 'country_id': cr.id,
        })
        cls.position = cls.env['account.fiscal.position'].create(
            {'name': EXONERATION_FISCAL_POSITION, 'company_id': company.id, 'country_id': cr.id})
        juridica = cls.env['identification.type'].search([('code', '=', '02')], limit=1)
        district = cls.env['res.country.district'].search([], limit=1)
        address = {'district_id': district.id, 'county_id': district.county_id.id,
                   'state_id': district.county_id.state_id.id, 'identification_id': juridica.id}
        company.write({
            'account_fiscal_country_id': cr.id, 'frm_ws_ambiente': 'api-stag',
            'date_expiration_sign': fields.Datetime.add(fields.Datetime.now(), days=365),
            'vat': '3101000001', 'email': 'fe@example.com', 'street': "Calle 1",
            'activity_id': cls.env['economic.activity'].search([], limit=1).id, **address,
        })
        cls.customer = cls.env['res.partner'].create({
            'name': "Cliente exonerado al 50 % de prueba", 'vat': '3101000099', 'email': 'cliente@example.com',
            'street': "Calle 2", 'has_exoneration': True, 'percentage_exoneration': 50,
            'exoneration_cabys_codes': WINE, 'type_exoneration': cls.env.ref('cr_electronic_invoice.AutEx_1').id,
            'exoneration_number': 'AL-0001', 'exoneration_issuer': cls.env['issuer.ex'].search([], limit=1).id,
            'date_issue': '2026-01-15', 'date_expiration': '2027-01-15', **address,
        })
        cls.wine = cls.env['product.product'].create({
            'name': "Vino de prueba", 'type': 'consu', 'cabys_code': WINE,
            'taxes_id': [Command.set(cls.iva.ids)]})
        cls.service = cls.env['product.product'].create({
            'name': "Servicio de prueba", 'type': 'service', 'cabys_code': SERVICE,
            'taxes_id': [Command.set(cls.iva.ids)]})

    def _summary(self, lines, document='FE'):
        """The ResumenFactura of the XML built for an FE to the customer with these (product, quantity, taxes)
        lines at 1 each, so a line amount has as many decimals as its quantity; signing and sending are
        intercepted."""
        self.env.ref('uom.decimal_product_uom').digits = 5
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.customer.id, 'fiscal_position_id': self.position.id,
            'tipo_documento': document, 'number_electronic': '50628112600310112345600200001010000000009100000009',
            'sequence': '00200001010000000009', 'invoice_date': '2026-11-28',
            'invoice_line_ids': [Command.create({'product_id': product.id, 'name': product.name, 'price_unit': 1,
                                                 'quantity': quantity,
                                                 'tax_ids': [Command.set(taxes.ids)]})
                                 for product, quantity, taxes in lines],
        })
        signed = []

        def sign(cert, password, xml):
            signed.append(xml)
            return xml.encode()

        with patch.object(api_facturae, 'sign_xml', side_effect=sign), \
                patch.object(api_facturae, 'get_token_hacienda',
                             side_effect=api_facturae.HaciendaUnavailable('not sent in a test')):
            invoice.generate_and_send_invoice()
        self.assertEqual(len(signed), 1, invoice.einvoice_error_detail)
        summary = etree.fromstring(signed[0].encode()).xpath('//*[local-name()="ResumenFactura"]')[0]
        return {node.xpath('local-name()'): node.text for node in summary.iterchildren()}

    def test_a_partial_exoneration_adds_up(self):
        """A wine line of 8920.18779 (an odd last decimal) half exonerated and a service with the full IVA, as
        the FE that Hacienda rejected: the taxed and the exonerated halves add up to the line, and the net sale
        to the total minus discounts."""
        half = self.iva._cr_exonerated_for(self.customer, WINE, self.position)
        self.assertEqual(half.amount, 6.5)
        summary = self._summary([(self.wine, 8920.18779, half), (self.service, 6637.16814, self.iva)])
        amount = {name: float(value) for name, value in summary.items()
                  if name.startswith('Total') and value and value.replace('.', '').replace('-', '').isdigit()}
        self.assertAlmostEqual(amount['TotalMercanciasGravadas'] + amount['TotalMercExonerada'], 8920.18779, 5)
        self.assertGreater(amount['TotalMercExonerada'], 0, "the wine is exonerated in part")
        self.assertEqual(amount['TotalServGravados'], 6637.16814)
        self.assertEqual(round(amount['TotalVenta'] - amount['TotalDescuentos'], 5), amount['TotalVentaNeta'])
        self.assertEqual(summary['TotalVentaNeta'], summary['TotalVenta'], "no discounts: the same figure")

    def test_a_line_at_tarifa_01_is_no_sujeto(self):
        """A service at VAT tarifa 01 (0 %) with a wine at 13 %, as the FE that Hacienda rejected with -111, -483
        and -485: the service goes to the no sujeto totals, not to the taxed ones, and still adds up to the sale."""
        summary = self._summary([(self.service, 6637.16814, self._zero()), (self.wine, 8407.07965, self.iva)])
        self.assertEqual(float(summary['TotalServGravados']), 0)
        self.assertEqual(float(summary['TotalServNoSujeto']), 6637.16814)
        self.assertEqual(float(summary['TotalMercanciasGravadas']), 8407.07965)
        self.assertEqual(float(summary['TotalMercNoSujeta']), 0)
        self.assertEqual(float(summary['TotalNoSujeto']), 6637.16814)
        self.assertEqual(float(summary['TotalVenta']), round(6637.16814 + 8407.07965, 5))
        names = list(summary)
        self.assertLess(names.index('TotalServExonerado'), names.index('TotalServNoSujeto'))
        self.assertLess(names.index('TotalServNoSujeto'), names.index('TotalMercanciasGravadas'))
        self.assertLess(names.index('TotalExonerado'), names.index('TotalNoSujeto'))
        self.assertLess(names.index('TotalNoSujeto'), names.index('TotalVenta'))

    def _zero(self):
        return self.env['account.tax'].create({
            'name': "IVA 0 % de prueba", 'amount': 0, 'type_tax_use': 'sale', 'tax_code': '01',
            'iva_tax_code': '01', 'tax_group_id': self.iva.tax_group_id.id,
            'company_id': self.env.company.id, 'country_id': self.env.ref('base.cr').id,
        })

    def test_the_export_invoice_keeps_tarifa_01_as_taxed(self):
        """Codex: the FEE has no no sujeto totals, so a line at tarifa 01 stays in the taxed ones there (it used to
        vanish from them while still counting in TotalVenta)."""
        zero = self._zero()
        summary = self._summary([(self.service, 100, zero), (self.wine, 200, zero)], document='FEE')
        self.assertEqual(float(summary['TotalServGravados']), 100)
        self.assertEqual(float(summary['TotalMercanciasGravadas']), 200)
        self.assertEqual(float(summary['TotalGravado']), 300)
        self.assertEqual(float(summary['TotalVenta']), 300)
        self.assertFalse([name for name in summary if 'NoSujet' in name])

    def test_without_tarifa_01_there_are_no_no_sujeto_totals(self):
        summary = self._summary([(self.service, 100, self.iva)])
        self.assertNotIn('TotalServNoSujeto', summary)
        self.assertNotIn('TotalNoSujeto', summary)
