import copy
import os

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae

XS = 'http://www.w3.org/2001/XMLSchema'
XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'xsd-4.4')


def reference_schema(xsd_name):
    """The document's schema with <InformacionReferencia> as its only global element,
    so the fragment built by append_reference_info() validates against Hacienda's own
    definition (node order, sizes and code enumerations)."""
    tree = etree.parse(os.path.join(XSD_DIR, xsd_name), etree.XMLParser(no_network=True))
    root = tree.getroot()
    element = copy.deepcopy(root.xpath('//xs:element[@name="InformacionReferencia"]', namespaces={'xs': XS})[0])
    for attribute in ('minOccurs', 'maxOccurs'):
        element.attrib.pop(attribute, None)
    for top_level in root.findall('{%s}element' % XS):
        root.remove(top_level)
    root.append(element)
    # Imports resolve relative to the original file.
    schema = etree.XMLSchema(etree.fromstring(etree.tostring(tree), base_url=tree.docinfo.URL))
    return schema, root.get('targetNamespace')


@tagged('post_install', '-at_install')
class TestReferenceXsd(TransactionCase):
    """<InformacionReferencia> as generated validates against the v4.4 XSDs of 22/04/2026."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schemas, cls.namespaces = {}, {}
        for name in ('FacturaElectronica_V4.4.xsd', 'NotaCreditoElectronica_V4.4.xsd',
                     'NotaDebitoElectronica_V4.4.xsd'):
            cls.schemas[name], cls.namespaces[name] = reference_schema(name)

    def _fragment(self, code, document, xsd_name):
        move = self.env['account.move'].new({
            'move_type': 'out_refund',
            'reference_code_id': code.id, 'reference_code_other': 'Ajuste por convenio <especial>',
            'reference_document_id': document.id, 'reference_document_other': 'Orden de servicio',
        })
        sb = api_facturae.StringBuilder()
        api_facturae.append_reference_info(
            sb, move, document.code, '5' * 50, '2026-10-20T12:00:00-06:00', code.code, 'Motivo')
        xml = str(sb).replace('<InformacionReferencia>',
                              '<InformacionReferencia xmlns="%s">' % self.namespaces[xsd_name], 1)
        return etree.fromstring(xml.encode())

    def _assert_valid(self, fragment, xsd_name):
        schema = self.schemas[xsd_name]
        self.assertTrue(schema.validate(fragment), '%s: %s' % (xsd_name, schema.error_log.last_error))

    def test_code_99_descriptions_validate(self):
        code = self.env['reference.code'].search([('code', '=', '99')])
        document = self.env['reference.document'].search([('code', '=', '99')])
        for xsd_name in self.schemas:
            self._assert_valid(self._fragment(code, document, xsd_name), xsd_name)

    def test_every_catalog_code_is_accepted(self):
        """Each reference code and document type we ship is in Hacienda's enumerations.
        Code 17 only exists in the Recibo Electrónico de Pago schema."""
        invoice_type = self.env['reference.document'].search([('code', '=', '01')])
        cancel = self.env['reference.code'].search([('code', '=', '01')])
        for xsd_name in self.schemas:
            for code in self.env['reference.code'].search([('code', '!=', '17')]):
                self._assert_valid(self._fragment(code, invoice_type, xsd_name), xsd_name)
            for document in self.env['reference.document'].search([]):
                self._assert_valid(self._fragment(cancel, document, xsd_name), xsd_name)

    def test_short_description_is_rejected(self):
        """The check really validates: a 3-character CodigoReferenciaOTRO fails (min 5)."""
        code = self.env['reference.code'].search([('code', '=', '99')])
        document = self.env['reference.document'].search([('code', '=', '01')])
        fragment = self._fragment(code, document, 'NotaCreditoElectronica_V4.4.xsd')
        fragment.find('{*}CodigoReferenciaOTRO').text = 'abc'
        self.assertFalse(self.schemas['NotaCreditoElectronica_V4.4.xsd'].validate(fragment))
