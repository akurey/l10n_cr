import os

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae

XS = 'http://www.w3.org/2001/XMLSchema'
XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'xsd-4.4')


@tagged('post_install', '-at_install')
class TestRegistroFiscal8707(TransactionCase):
    """The company's alcoholic beverages register (Law 8707) goes in <Emisor> of its documents."""

    def _issuer_fragment(self, tipo_documento, company=None):
        move = self.env['account.move'].new({
            'move_type': 'out_invoice', 'company_id': (company or self.env.company).id,
            'tipo_documento': tipo_documento,
        })
        sb = api_facturae.StringBuilder()
        api_facturae.append_registro_fiscal_8707(sb, move)
        return str(sb)

    def test_register_is_sent_on_the_company_documents(self):
        self.env.company.registro_fiscal_8707 = ' 1234 '
        for tipo_documento in ('FE', 'TE', 'NC', 'ND', 'FEE'):
            self.assertEqual(self._issuer_fragment(tipo_documento),
                             '<Registrofiscal8707>1234</Registrofiscal8707>', tipo_documento)

    def test_branch_uses_its_main_company_register(self):
        self.env.company.registro_fiscal_8707 = '1234'
        branch = self.env['res.company'].create({'name': 'Branch', 'parent_id': self.env.company.id})
        self.assertEqual(self._issuer_fragment('FE', branch), '<Registrofiscal8707>1234</Registrofiscal8707>')
        branch.registro_fiscal_8707 = '5678'
        self.assertEqual(self._issuer_fragment('FE', branch), '<Registrofiscal8707>5678</Registrofiscal8707>')

    def test_register_is_left_out_on_fec_and_when_not_set(self):
        self.env.company.registro_fiscal_8707 = '1234'
        self.assertEqual(self._issuer_fragment('FEC'), '', 'On an FEC the issuer is the supplier')
        self.env.company.registro_fiscal_8707 = False
        self.assertEqual(self._issuer_fragment('FE'), '')

    def test_field_matches_the_xsd(self):
        """Registrofiscal8707 is an optional string of up to 12 characters in EmisorType, right after
        Identificacion, in every v4.4 schema that has an issuer of ours (XSDs of 22/04/2026)."""
        size = self.env['res.company']._fields['registro_fiscal_8707'].size
        for xsd_name in ('FacturaElectronica_V4.4.xsd', 'TiqueteElectronico_V4.4.xsd',
                         'NotaCreditoElectronica_V4.4.xsd', 'NotaDebitoElectronica_V4.4.xsd',
                         'FacturaElectronicaExportacion_V4.4.xsd'):
            root = etree.parse(os.path.join(XSD_DIR, xsd_name), etree.XMLParser(no_network=True)).getroot()
            sequence = root.xpath('//xs:complexType[@name="EmisorType"]/xs:sequence/xs:element/@name',
                                  namespaces={'xs': XS})
            self.assertEqual(sequence[sequence.index('Identificacion') + 1], 'Registrofiscal8707', xsd_name)
            max_length = root.xpath(
                '//xs:complexType[@name="EmisorType"]//xs:element[@name="Registrofiscal8707"]'
                '//xs:maxLength/@value', namespaces={'xs': XS})
            self.assertEqual(max_length, [str(size)], xsd_name)
