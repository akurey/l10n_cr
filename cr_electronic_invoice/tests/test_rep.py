import os

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae

XSD = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'xsd-4.4', 'ReciboElectronicoPago_V4.4.xsd')


def unsigned_schema(path):
    tree = etree.parse(path, etree.XMLParser(no_network=True))
    for signature in tree.xpath('//xs:element[@ref="ds:Signature"]',
                                namespaces={'xs': 'http://www.w3.org/2001/XMLSchema'}):
        signature.set('minOccurs', '0')
    return etree.XMLSchema(etree.fromstring(etree.tostring(tree), base_url=tree.docinfo.URL))


@tagged('post_install', '-at_install')
class TestRep(TransactionCase):
    """Nota 5: an invoice "Venta a crédito en IVA hasta 90 días" (10) is paid through a Recibo
    Electrónico de Pago with "Pago de venta a crédito en IVA hasta 90 días" (11); likewise 08 -> 09.
    The REP used to be generated only for invoices on condition 11, which Hacienda only allows on
    the REP itself, so it could never work."""

    def test_sale_condition_mapping(self):
        self.assertEqual(api_facturae.REP_SALE_CONDITIONS, {'10': '11', '08': '09'})
        self.assertNotIn('11', api_facturae.REP_SALE_CONDITIONS)

    def test_rep_validates_against_hacienda_schema(self):
        juridica = self.env['identification.type'].search([('code', '=', '02')], limit=1)
        fisica = self.env['identification.type'].search([('code', '=', '01')], limit=1)
        self.env.company.write({'vat': '3101123456', 'identification_id': juridica.id, 'email': 'fe@example.com'})
        customer = self.env['res.partner'].create({'name': 'Cliente', 'vat': '112345678', 'identification_id': fisica.id})
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice', 'partner_id': customer.id, 'tipo_documento': 'FE',
            'number_electronic': '50623102600310112345600100001010000000001100000001',
            'date_issuance': '2026-10-23T12:00:00-06:00',
            'payment_methods_id': self.env.ref('cr_electronic_invoice.PaymentMethods_1').id,
        })
        lines = {1: {'detalle': 'Servicio', 'montoTotal': 10000.0, 'subtotal': 10000.0, 'montoTotalLinea': 11300.0,
                     'impuestoNeto': 1300.0,
                     'impuesto': {1: {'codigo': '01', 'iva_tax_code': '08', 'tarifa': 13.0, 'monto': 1300.0}}},
                 2: {'detalle': 'Servicio 4%', 'montoTotal': 5000.0, 'subtotal': 5000.0, 'montoTotalLinea': 5200.0,
                     'impuestoNeto': 200.0,
                     'impuesto': {1: {'codigo': '01', 'iva_tax_code': '04', 'tarifa': 4.0, 'monto': 200.0}}}}
        xml = str(api_facturae.generate_rep_xml(
            invoice, 'REP', api_facturae.REP_SALE_CONDITIONS['10'], lines, 1,
            15000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 15000.0, 1500.0, 0.0, 0.0))
        # Clave, consecutivo and date are filled in when the payment is registered.
        xml = xml.replace('<Clave></Clave>', '<Clave>' + '5' * 50 + '</Clave>')
        xml = xml.replace('<NumeroConsecutivo></NumeroConsecutivo>', '<NumeroConsecutivo>' + '0' * 20 + '</NumeroConsecutivo>')
        xml = xml.replace('<FechaEmision></FechaEmision>', '<FechaEmision>2026-10-23T12:00:00-06:00</FechaEmision>')
        root = etree.fromstring(xml.encode())
        self.assertEqual(root.findtext('{*}CondicionVenta'), '11')
        self.assertEqual(root.find('{*}InformacionReferencia').findtext('{*}Codigo'), '17')
        summary = root.find('{*}ResumenFactura')
        self.assertEqual(summary.findtext('{*}TotalImpuesto'), '1500.0')
        self.assertEqual([b.findtext('{*}TotalMontoImpuesto') for b in summary.findall('{*}TotalDesgloseImpuesto')],
                         ['1300.0', '200.0'])
        self.assertEqual(summary.findtext('{*}TotalComprobante'), '16500.0')
        schema = unsigned_schema(XSD)
        self.assertTrue(schema.validate(root), schema.error_log.last_error)
