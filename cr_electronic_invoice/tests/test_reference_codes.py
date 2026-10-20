from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae


@tagged('post_install', '-at_install')
class TestReferenceCodes(TransactionCase):
    """Anexos y Estructuras v4.4, bitácora del 22/04/2026 (mandatory from 2026-11-01):
    new codes in nota 9 (código de referencia) and nota 10 (tipo de documento de referencia)."""

    def _names(self, model):
        return dict(self.env[model].search([]).mapped(lambda r: (r.code, r.name)))

    def test_nota_9_reference_codes(self):
        codes = self._names('reference.code')
        self.assertEqual(codes['12'], 'Nota de crédito financiera por exoneración posterior a la facturación')
        self.assertEqual(codes['13'], 'Anula documento de referencia por error material')
        self.assertEqual(codes['14'], 'Corrige monto por error material')
        self.assertEqual(codes['15'], 'Sustituye comprobante electrónico por error material')
        self.assertEqual(codes['16'], 'Sustituye comprobante electrónico rechazado')
        self.assertEqual(codes['17'], 'Pago a comprobante electrónico')

    def test_nota_10_reference_documents(self):
        documents = self._names('reference.document')
        self.assertEqual(documents['19'], 'Factura Electrónica de Exportación')
        self.assertEqual(documents['20'], 'Recibo Electrónico de Pago')

    def test_payment_code_not_offered_on_notes(self):
        """Code 17 is exclusive to the Recibo Electrónico de Pago, which is generated."""
        for model in ('account.move', 'account.move.reversal'):
            field = self.env[model]._fields['reference_code_id']
            offered = self.env['reference.code'].search(field.domain)
            self.assertNotIn('17', offered.mapped('code'), model)
            self.assertIn('13', offered.mapped('code'), model)

    def test_rep_references_invoice_with_payment_code(self):
        juridica = self.env['identification.type'].search([('code', '=', '02')], limit=1)
        fisica = self.env['identification.type'].search([('code', '=', '01')], limit=1)
        self.env.company.write({
            'vat': '3101123456', 'identification_id': juridica.id, 'email': 'fe@example.com',
        })
        customer = self.env['res.partner'].create({
            'name': 'Cliente', 'vat': '112345678', 'identification_id': fisica.id,
        })
        invoice = self.env['account.move'].new({
            'move_type': 'out_invoice',
            'partner_id': customer.id,
            'tipo_documento': 'FE',
            'number_electronic': '5' * 50,
            'date_issuance': '2026-10-20T12:00:00-06:00',
        })
        lines = {1: {'detalle': 'Servicio', 'montoTotal': 100.0, 'subtotal': 100.0, 'montoTotalLinea': 100.0}}
        xml = str(api_facturae.generate_rep_xml(
            invoice, 'REP', '11', lines, 1, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0))

        reference = etree.fromstring(xml.encode()).find('{*}InformacionReferencia')
        self.assertEqual(reference.findtext('{*}TipoDocIR'), '01')
        self.assertEqual(reference.findtext('{*}Numero'), '5' * 50)
        self.assertEqual(reference.findtext('{*}Codigo'), '17')
