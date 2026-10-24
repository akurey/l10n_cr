import copy
import os

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae

XS = 'http://www.w3.org/2001/XMLSchema'
XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'xsd-4.4')


def summary_schema(xsd_name):
    """The document's schema with a <Desglose> root holding its TotalDesgloseImpuesto element,
    so the breakdown validates against Hacienda's own definition (cardinality and content)."""
    tree = etree.parse(os.path.join(XSD_DIR, xsd_name), etree.XMLParser(no_network=True))
    root = tree.getroot()
    element = copy.deepcopy(root.xpath('//xs:element[@name="TotalDesgloseImpuesto"]', namespaces={'xs': XS})[0])
    for top_level in root.findall('{%s}element' % XS):
        root.remove(top_level)
    wrapper = etree.SubElement(root, '{%s}element' % XS, name='Desglose')
    sequence = etree.SubElement(etree.SubElement(wrapper, '{%s}complexType' % XS), '{%s}sequence' % XS)
    sequence.append(element)
    schema = etree.XMLSchema(etree.fromstring(etree.tostring(tree), base_url=tree.docinfo.URL))
    return schema, root.get('targetNamespace')


@tagged('post_install', '-at_install')
class TestTaxBreakdown(TransactionCase):
    """A document with two VAT rates (13% and 4%) gets one TotalDesgloseImpuesto per rate. They
    all went in a single element, which Hacienda rejected (cvc-complex-type.2.4.d on Codigo)."""

    summary = {
        '08': {'Codigo': '01', 'CodigoTarifaIVA': '08', 'TotalMontoImpuesto': 1170.0},
        '04': {'Codigo': '01', 'CodigoTarifaIVA': '04', 'TotalMontoImpuesto': 200.0},
    }

    def _breakdown(self, namespace):
        sb = api_facturae.StringBuilder()
        api_facturae.append_tax_breakdown(sb, self.summary)
        return etree.fromstring(('<Desglose xmlns="%s">%s</Desglose>' % (namespace, sb)).encode())

    def test_one_element_per_rate(self):
        root = self._breakdown('urn:test')
        blocks = root.findall('{*}TotalDesgloseImpuesto')
        self.assertEqual([b.findtext('{*}CodigoTarifaIVA') for b in blocks], ['08', '04'])
        self.assertEqual([b.findtext('{*}TotalMontoImpuesto') for b in blocks], ['1170.0', '200.0'])

    def test_validates_against_hacienda_schemas(self):
        for xsd_name in ('FacturaElectronica_V4.4.xsd', 'NotaCreditoElectronica_V4.4.xsd',
                         'NotaDebitoElectronica_V4.4.xsd', 'TiqueteElectronico_V4.4.xsd'):
            schema, namespace = summary_schema(xsd_name)
            self.assertTrue(schema.validate(self._breakdown(namespace)), '%s: %s' % (xsd_name, schema.error_log.last_error))
