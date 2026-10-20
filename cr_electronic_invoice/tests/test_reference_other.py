from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae


@tagged('post_install', '-at_install')
class TestReferenceOther(TransactionCase):
    """Code 99 "Otros" in notas 9 and 10 must be described: CodigoReferenciaOTRO and
    TipoDocRefOTRO, 5 to 100 characters, or Hacienda rejects the document."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.code_99 = cls.env['reference.code'].search([('code', '=', '99')], limit=1)
        cls.code_01 = cls.env['reference.code'].search([('code', '=', '01')], limit=1)
        cls.document_99 = cls.env['reference.document'].search([('code', '=', '99')], limit=1)
        cls.document_01 = cls.env['reference.document'].search([('code', '=', '01')], limit=1)

    def _move(self, **vals):
        return self.env['account.move'].new({'move_type': 'out_refund', **vals})

    def _reference(self, move):
        sb = api_facturae.StringBuilder()
        api_facturae.append_reference_info(
            sb, move, move.reference_document_id.code, '5' * 50, '2026-10-20T12:00:00-06:00',
            move.reference_code_id.code, 'Motivo')
        return etree.fromstring(str(sb).encode())

    def test_other_descriptions_in_xml_order(self):
        move = self._move(
            reference_code_id=self.code_99.id, reference_code_other='  Ajuste por convenio  ',
            reference_document_id=self.document_99.id, reference_document_other='Orden de servicio',
        )
        reference = self._reference(move)
        self.assertEqual(
            [child.tag for child in reference],
            ['TipoDocIR', 'TipoDocRefOTRO', 'Numero', 'FechaEmisionIR', 'Codigo', 'CodigoReferenciaOTRO', 'Razon'])
        self.assertEqual(reference.findtext('TipoDocRefOTRO'), 'Orden de servicio')
        self.assertEqual(reference.findtext('CodigoReferenciaOTRO'), 'Ajuste por convenio')

    def test_other_text_is_escaped(self):
        move = self._move(reference_code_id=self.code_99.id, reference_code_other='Ajuste <A & B>',
                          reference_document_id=self.document_01.id)
        self.assertEqual(self._reference(move).findtext('CodigoReferenciaOTRO'), 'Ajuste <A & B>')

    def test_no_other_nodes_without_code_99(self):
        move = self._move(reference_code_id=self.code_01.id, reference_document_id=self.document_01.id,
                          reference_code_other='Ignorado', reference_document_other='Ignorado')
        tags = [child.tag for child in self._reference(move)]
        self.assertNotIn('TipoDocRefOTRO', tags)
        self.assertNotIn('CodigoReferenciaOTRO', tags)

    def test_code_99_needs_5_to_100_characters(self):
        for text in (False, '   ', 'abcd', 'x' * 101):
            with self.assertRaises(UserError, msg=repr(text)):
                self._move(reference_code_id=self.code_99.id, reference_code_other=text)._check_reference_other()
            with self.assertRaises(UserError, msg=repr(text)):
                self._move(reference_document_id=self.document_99.id,
                           reference_document_other=text)._check_reference_other()
        self._move(reference_code_id=self.code_99.id, reference_code_other='Ajuste',
                   reference_document_id=self.document_99.id, reference_document_other='x' * 100,
                   )._check_reference_other()
        self._move(reference_code_id=self.code_01.id, reference_document_id=self.document_01.id)._check_reference_other()

    def test_reversal_wizard_carries_other_descriptions(self):
        partner = self.env['res.partner'].create({'name': 'Cliente'})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id, 'invoice_date': '2026-10-01',
            'invoice_line_ids': [(0, 0, {'name': 'Servicio', 'quantity': 1, 'price_unit': 100.0})],
        })
        # Post without going through Hacienda.
        self.env.company.frm_ws_ambiente = 'disabled'
        invoice.action_post()
        wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=invoice.ids).create({
                'journal_id': invoice.journal_id.id,
                'reference_code_id': self.code_99.id, 'reference_code_other': 'Ajuste por convenio',
                'reference_document_id': self.document_99.id, 'reference_document_other': 'Orden de servicio',
            })
        values = wizard._prepare_default_reversal(invoice)
        self.assertEqual(values['reference_code_other'], 'Ajuste por convenio')
        self.assertEqual(values['reference_document_other'], 'Orden de servicio')
