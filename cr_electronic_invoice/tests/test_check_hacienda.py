import base64
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae

CLAVE = '50626112600310112345600200001010000000007100000007'


@tagged('post_install', '-at_install')
class TestCheckHacienda(TransactionCase):
    """The "check Hacienda" button (action_check_hacienda -> consulta_documentos) on a document that
    Hacienda has just accepted: the customer gets the e-mail with both XMLs, and the issue date stays."""

    def setUp(self):
        super().setUp()
        journal = self.env['account.journal'].create({'name': 'Ventas CR', 'type': 'sale', 'code': 'TCRV'})
        customer = self.env['res.partner'].create({'name': 'Cliente', 'email': 'cliente@example.com'})
        self.invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': journal.id, 'partner_id': customer.id,
            'tipo_documento': 'FE', 'number_electronic': CLAVE, 'state_tributacion': 'procesando',
            'date_issuance': '2026-11-26T10:00:00-06:00', 'fname_xml_comprobante': 'FE_' + CLAVE + '.xml',
        })
        # As generate_and_send_invoices stores the signed XML
        self.env['ir.attachment'].create({
            'name': 'FE_' + CLAVE + '.xml', 'datas': base64.b64encode(b'<FacturaElectronica/>'),
            'res_model': 'account.move', 'res_id': self.invoice.id, 'res_field': 'xml_comprobante',
            'mimetype': 'text/xml',
        })

    def _check_hacienda(self, answer=None):
        """Runs the button's check (Hacienda answers 'aceptado' unless told otherwise); returns the attachment
        names of each e-mail sent."""
        sent = []

        def send_mail(template, res_id, **kwargs):
            ids = [command[1] for command in kwargs.get('email_values', {}).get('attachment_ids', [])]
            sent.append(sorted(self.env['ir.attachment'].browse(ids).mapped('name')))
            return 1

        if answer is None:
            answer = {'ind-estado': 'aceptado', 'respuesta-xml': base64.b64encode(b'<MensajeHacienda/>')}
        with patch.object(api_facturae, 'consulta_clave', return_value=answer), \
                patch.object(type(self.env['mail.template']), 'send_mail', send_mail):
            api_facturae.consulta_documentos(self.invoice, self.invoice, 'api-stag', 'token', False, False)
        return sent

    def test_acceptance_sends_the_e_mail_with_both_xml(self):
        sent = self._check_hacienda()
        self.assertEqual(self.invoice.state_tributacion, 'aceptado')
        self.assertEqual(sent, [['AHC_' + CLAVE + '.xml', 'FE_' + CLAVE + '.xml']])

    def test_issue_date_is_kept(self):
        self._check_hacienda()
        self.assertEqual(self.invoice.date_issuance, '2026-11-26T10:00:00-06:00')

    def test_an_accepted_document_is_not_mailed_again(self):
        self.invoice.state_tributacion = 'aceptado'
        self.assertEqual(self._check_hacienda(), [])

    def test_accepted_after_an_error_is_mailed_too(self):
        """As the cron: once the button makes it 'aceptado' the cron skips it, so this is the only chance."""
        self.invoice.state_tributacion = 'error'
        self.assertEqual(len(self._check_hacienda()), 1)

    def test_customer_without_e_mail_gets_nothing(self):
        self.invoice.partner_id.email = False
        self.assertEqual(self._check_hacienda(), [])
        self.assertEqual(self.invoice.state_tributacion, 'aceptado')

    def test_no_answer_keeps_the_state_and_mails_nothing(self):
        """Hacienda down: the state is kept, so a later check does not take it for a first acceptance."""
        self.invoice.state_tributacion = 'aceptado'
        self.assertEqual(self._check_hacienda({'status': 503}), [])
        self.assertEqual(self.invoice.state_tributacion, 'aceptado')
        self.assertEqual(self._check_hacienda(), [], "not mailed a second time")

    def test_the_shared_template_is_left_untouched(self):
        template = self.env.ref('account.email_template_edi_invoice')
        before = template.attachment_ids
        self._check_hacienda()
        self.assertEqual(template.attachment_ids, before)
