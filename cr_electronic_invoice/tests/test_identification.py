import os
import re

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae
from ..models.identification import clean_clave, clean_identification, is_legal_id

XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'xsd-4.4')


def unsigned_schema(xsd_name):
    """Hacienda's schema with ds:Signature optional: the tests do not sign."""
    tree = etree.parse(os.path.join(XSD_DIR, xsd_name), etree.XMLParser(no_network=True))
    for signature in tree.xpath('//xs:element[@ref="ds:Signature"]',
                                namespaces={'xs': 'http://www.w3.org/2001/XMLSchema'}):
        signature.set('minOccurs', '0')
    return etree.XMLSchema(etree.fromstring(etree.tostring(tree), base_url=tree.docinfo.URL))


def old_clean(number):
    """What every place did before: keep the digits only."""
    return re.sub('[^0-9]', '', number)


@tagged('post_install', '-at_install')
class TestIdentification(TransactionCase):
    """Registro Nacional's alphanumeric cédula jurídica (3-101-A00001), accepted by Hacienda since
    the v4.4 update of 22/04/2026. Today's numeric identifications must come out unchanged."""

    def test_current_identifications_unchanged(self):
        samples = {
            '01': ['112345678', '1-1234-5678', '1 1234 5678'],
            '02': ['3101123456', '3-101-123456', '3.101.123456', '2-100-042005', '4-000-042139'],
            '03': ['155812345678', '15581234567'],
            '04': ['1234567890'],
            False: ['112345678', '3-101-123456', '155812345678', 'ESB12345678', 'CHE-123.456.789'],
        }
        for id_code, numbers in samples.items():
            for number in numbers:
                self.assertEqual(clean_identification(number, id_code), old_clean(number), (id_code, number))

    def test_alphanumeric_legal_id(self):
        for number in ('3-101-A00001', '3101a00001', ' 3.102.A00002 '):
            self.assertTrue(is_legal_id(clean_identification(number, '02')), number)
        self.assertEqual(clean_identification('3-101-a00001', '02'), '3101A00001')
        # Type unknown: kept only with the cédula jurídica shape.
        self.assertEqual(clean_identification('3-101-A00001'), '3101A00001')
        # Other types never keep letters.
        self.assertEqual(clean_identification('1-1234-567A', '01'), '11234567')

    def test_legal_id_shape(self):
        for number in ('3101123456', '3101A00001', '2100042005', '3102ZZ9999'):
            self.assertTrue(is_legal_id(number), number)
        for number in ('3101A0000', '3101123456A', 'A101123456', '31O1123456', '', False):
            self.assertFalse(is_legal_id(number), number)

    def test_partner_keeps_legal_id_letters(self):
        juridica = self.env['identification.type'].search([('code', '=', '02')], limit=1)
        partner = self.env['res.partner'].new({'name': 'Nueva S.A.', 'identification_id': juridica.id,
                                               'vat': '3-101-a00001'})
        partner._onchange_vat()
        self.assertEqual(partner.vat, '3101A00001')
        partner.vat = '3-101-123456'
        partner._onchange_vat()
        self.assertEqual(partner.vat, '3101123456')
        partner.vat = '3101123456A'
        with self.assertRaises(UserError):
            partner._onchange_vat()

    def test_clave_of_an_alphanumeric_issuer(self):
        juridica = self.env['identification.type'].search([('code', '=', '02')], limit=1)
        self.env.company.write({'vat': '3101A00001', 'identification_id': juridica.id, 'phone': '+506 2222 2222'})
        invoice = self.env['account.move'].new({'move_type': 'out_invoice', 'invoice_date': '2026-11-02'})
        clave = api_facturae.get_clave_hacienda(invoice, 'FE', '0000000001', '1', '1')['clave']
        self.assertEqual(len(clave), 50)
        self.assertEqual(clave[9:21], '003101A00001')
        self.assertTrue(re.fullmatch('[a-zA-Z0-9]{50}', clave))
        self.assertEqual(clean_clave('-'.join([clave[:25], clave[25:]])), clave)

    def test_receiver_message_for_an_alphanumeric_vendor(self):
        """Accepting the bill of a vendor with a new cédula jurídica: its clave and identification
        keep their letters and the message validates against Hacienda's XSD. Our own cédula
        (NumeroCedulaReceptor) is still digits-only in the XSD (\\d{9,12})."""
        clave = '50602112600' + '3101A00001' + '00100001010000000123' + '1' + '12345678'
        self.assertEqual(len(clave), 50)
        xml = api_facturae.gen_xml_mr_4_4(
            clave, '3-101-A00001', '2026-11-02T10:00:00-06:00', '1', 'Aceptado', '3-101-123456',
            '00100001050000000001', monto_impuesto=130.0, total_factura=1130.0,
            codigo_actividad='620100', condicion_impuesto='01')
        root = etree.fromstring(xml.encode())
        self.assertEqual(root.findtext('{*}Clave'), clave)
        self.assertEqual(root.findtext('{*}NumeroCedulaEmisor'), '3101A00001')
        self.assertEqual(root.findtext('{*}NumeroCedulaReceptor'), '3101123456')
        schema = unsigned_schema('MensajeReceptor_V4.4.xsd')
        self.assertTrue(schema.validate(root), schema.error_log.last_error)
