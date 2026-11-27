import base64
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..models import api_facturae
from ..models.account_move import MAX_SEND_ATTEMPTS

CLAVE = '50626112600310112345600200001010000000007100000007'
NEW_CLAVE = '50627112600310112345600200001010000000009100000009'
NEW_CONSECUTIVO = '00200001010000000009'
THIRD_CLAVE = '50627112600310112345600200001010000000010100000010'
THIRD_CONSECUTIVO = '00200001010000000010'
NOTE_CLAVE = '50626112600310112345600200001030000000001100000001'
ISSUE_EMAIL = 'billing-problems@example.com'


def answer_xml(detail):
    return base64.b64encode(f'<MensajeHacienda><DetalleMensaje>{detail}</DetalleMensaje></MensajeHacienda>'.encode())


@tagged('post_install', '-at_install')
class TestSendErrors(TransactionCase):
    """What happens when an electronic document is not accepted: Hacienda down goes back to the queue;
    errors and rejections say why, alert the company (activity and urgent e-mail) and can be retried or
    replaced from the document."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The messages are checked in English: a database created in Spanish may not even have it active
        cls.env['res.lang']._activate_lang('en_US')
        cls.env = cls.env(context=dict(cls.env.context, lang='en_US'))
        cls.responsible = cls.env['res.users'].create({
            'name': 'Responsable FE', 'login': 'fe_issues', 'email': 'responsable@example.com', 'lang': 'en_US',
            'group_ids': [(6, 0, cls.env.ref('account.group_account_invoice').ids)],
        })
        cls.company = cls.env.company
        cls.company.write({
            'frm_ws_ambiente': 'api-stag',
            'date_expiration_sign': fields.Datetime.add(fields.Datetime.now(), days=365),
            'einvoice_issue_user_id': cls.responsible.id,
            'einvoice_issue_email': ISSUE_EMAIL,
        })
        cls.journal = cls.env['account.journal'].create({'name': 'Ventas CR', 'type': 'sale', 'code': 'TCRE'})
        cls.purchases = cls.env['account.journal'].create({'name': 'Compras CR', 'type': 'purchase', 'code': 'TCRP'})
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente', 'email': 'cliente@example.com'})

    def setUp(self):
        super().setUp()
        self.invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'journal_id': self.journal.id, 'partner_id': self.customer.id,
            'tipo_documento': 'FE', 'number_electronic': CLAVE, 'sequence': '00200001010000000007',
            'date_issuance': '2026-11-26T10:00:00-06:00', 'fname_xml_comprobante': 'FE_' + CLAVE + '.xml',
            'invoice_date': '2026-11-20',  # issued to Hacienda later, on the date of its key
        })
        # As generate_and_send_invoices stores the signed XML: the send flow reuses it.
        self.env['ir.attachment'].create({
            'name': 'FE_' + CLAVE + '.xml', 'datas': base64.b64encode(b'<FacturaElectronica/>'),
            'res_model': 'account.move', 'res_id': self.invoice.id, 'res_field': 'xml_comprobante',
            'mimetype': 'text/xml',
        })
        self.invoice.invalidate_recordset(['xml_comprobante'])

    def test_the_supplier_acceptance_message_does_not_wait_forever(self):
        """Sending the acceptance of a supplier's document has a time limit, like every other call to Hacienda."""
        with patch.object(api_facturae, 'clean_identification', return_value='ID-DE-PRUEBA'), \
                patch.object(api_facturae.requests, 'post',
                             side_effect=api_facturae.requests.exceptions.Timeout('no answer')) as post:
            result = api_facturae.send_message(self.invoice, '2026-11-27T10:00:00-06:00', b'<MensajeReceptor/>',
                                               'token', 'api-stag')
        self.assertEqual(post.call_args.kwargs.get('timeout'), api_facturae.HACIENDA_TIMEOUT)
        self.assertEqual(result['status'], 400)

    def _alert_mails(self):
        return self.env['mail.mail'].search([('email_to', '=', ISSUE_EMAIL), ('res_id', '=', self.invoice.id)])

    def _issue_activities(self):
        return self.invoice.activity_ids.filtered(
            lambda a: a.activity_type_id == self.env.ref('cr_electronic_invoice.mail_activity_einvoice_issue'))

    def _send(self):
        down = api_facturae.HaciendaUnavailable('connection refused')
        with patch.object(api_facturae, 'get_token_hacienda', side_effect=down):
            self.invoice.generate_and_send_invoice()

    def test_hacienda_down_goes_back_to_the_queue(self):
        self._send()
        self.assertFalse(self.invoice.state_tributacion, "the send cron takes it again")
        self.assertEqual(self.invoice.error_count, 1)
        self.assertIn('sent again automatically', self.invoice.einvoice_error_detail)
        self.assertTrue(self.invoice.xml_comprobante, "the signed XML is kept, with its key")
        self.assertFalse(self._alert_mails())
        self.assertFalse(self._issue_activities())

    @mute_logger('odoo.addons.cr_electronic_invoice.models.account_move')
    def test_a_server_error_while_sending_goes_back_to_the_queue(self):
        """A 5xx from Hacienda's reception is Hacienda down, not a refusal: no error count towards a refusal."""
        down = Mock(status_code=503, headers={}, reason='Service Unavailable')
        with patch.object(api_facturae, 'get_token_hacienda', return_value='token'), \
                patch.object(api_facturae.requests, 'request', return_value=down):
            self.invoice.generate_and_send_invoice()
        self.assertFalse(self.invoice.state_tributacion, "back to the send queue")
        self.assertIn('sent again automatically', self.invoice.einvoice_error_detail)
        self.assertIn('HTTP 503', self.invoice.einvoice_error_detail)
        self.assertFalse(self._alert_mails())

    def test_hacienda_down_too_many_times_is_an_error_and_alerts(self):
        self.invoice.error_count = MAX_SEND_ATTEMPTS - 1
        self._send()
        self.assertEqual(self.invoice.state_tributacion, 'error')
        self.assertIn(f'after {MAX_SEND_ATTEMPTS} attempts', self.invoice.einvoice_error_detail)
        mail = self._alert_mails()
        self.assertEqual(len(mail), 1)
        self.assertIn('URGENT', mail.subject)
        self.assertIn('Retry Sending', mail.body_html)
        self.assertIn('connection refused', mail.body_html)
        activity = self._issue_activities()
        self.assertEqual(activity.user_id, self.responsible)

    def test_one_activity_per_document_one_mail_per_problem(self):
        self.invoice._cr_einvoice_fail('first')
        self.invoice.state_tributacion = 'procesando'
        self.invoice._cr_einvoice_fail('second')
        self.assertEqual(len(self._issue_activities()), 1)
        self.assertEqual(len(self._alert_mails()), 2)

    def test_acceptance_closes_the_activity(self):
        self.invoice._cr_einvoice_fail('CABYS missing')
        self.invoice.state_tributacion = 'aceptado'
        self.assertFalse(self._issue_activities())
        self.assertFalse(self.invoice.einvoice_error_detail)

    def test_alert_in_the_language_of_the_responsible(self):
        self.env['res.lang']._activate_lang('es_CR')
        self.responsible.lang = 'es_CR'
        self.invoice._cr_einvoice_fail('CABYS missing')
        mail = self._alert_mails()
        self.assertIn('URGENTE', mail.subject)
        self.assertIn('Reintentar envío', mail.body_html)

    def test_no_alert_without_company_settings(self):
        self.company.write({'einvoice_issue_user_id': False, 'einvoice_issue_email': False})
        self.invoice._cr_einvoice_fail('CABYS missing')
        self.assertEqual(self.invoice.state_tributacion, 'error')
        self.assertFalse(self._alert_mails())
        self.assertFalse(self._issue_activities())

    def test_vendor_bills_do_not_alert(self):
        bill = self.env['account.move'].create({'move_type': 'in_invoice', 'partner_id': self.customer.id,
                                                'journal_id': self.purchases.id})
        bill.state_tributacion = 'error'
        self.assertFalse(self.env['mail.mail'].search([('email_to', '=', ISSUE_EMAIL), ('res_id', '=', bill.id)]))

    def test_rejection_from_the_cron_carries_hacienda_detail(self):
        self.env.cr.execute("UPDATE account_move SET state = 'posted', state_tributacion = 'procesando' WHERE id = %s",
                            (self.invoice.id,))
        self.invoice.invalidate_recordset()
        answer = {'status': 200, 'ind-estado': 'rechazado', 'respuesta-xml': answer_xml('CABYS 123 no existe')}
        with patch.object(api_facturae, 'get_token_hacienda', return_value='token'), \
                patch.object(api_facturae, 'consulta_clave', return_value=answer):
            self.env['account.move']._check_hacienda_for_invoices_company(self.company)
        self.assertEqual(self.invoice.state_tributacion, 'rechazado')
        self.assertEqual(self.invoice.einvoice_error_detail, 'CABYS 123 no existe')
        mail = self._alert_mails()
        self.assertEqual(len(mail), 1)
        self.assertIn('rejected', mail.subject)
        self.assertIn('CABYS 123 no existe', mail.body_html)

    def test_rejection_from_the_button_carries_hacienda_detail(self):
        self.invoice.state_tributacion = 'procesando'
        answer = {'status': 200, 'ind-estado': 'rechazado', 'respuesta-xml': answer_xml('Receptor no existe')}
        with patch.object(api_facturae, 'consulta_clave', return_value=answer):
            api_facturae.consulta_documentos(self.invoice, self.invoice, 'api-stag', 'token', False, False)
        self.assertEqual(self.invoice.einvoice_error_detail, 'Receptor no existe')
        self.assertIn('Receptor no existe', self._alert_mails().body_html)

    @mute_logger('odoo.addons.cr_electronic_invoice.models.account_move')  # "Invoice not found ... error", on purpose
    def test_an_error_answer_is_checked_again_without_alerting(self):
        self.env.cr.execute("UPDATE account_move SET state = 'posted', state_tributacion = 'procesando' WHERE id = %s",
                            (self.invoice.id,))
        self.invoice.invalidate_recordset()
        with patch.object(api_facturae, 'get_token_hacienda', return_value='token'), \
                patch.object(api_facturae, 'consulta_clave', return_value={'status': 200, 'ind-estado': 'error'}):
            self.env['account.move']._check_hacienda_for_invoices_company(self.company)
        self.assertEqual(self.invoice.state_tributacion, 'procesando')
        self.assertFalse(self._alert_mails())
        self.invoice.error_count = MAX_SEND_ATTEMPTS
        with patch.object(api_facturae, 'get_token_hacienda', return_value='token'), \
                patch.object(api_facturae, 'consulta_clave', return_value={'status': 200, 'ind-estado': 'error'}):
            self.env['account.move']._check_hacienda_for_invoices_company(self.company)
        self.assertEqual(self.invoice.state_tributacion, 'error')
        self.assertEqual(len(self._alert_mails()), 1)

    @mute_logger('odoo.addons.cr_electronic_invoice.models.account_move')  # "could not alert the company", on purpose
    def test_a_failing_alert_keeps_the_state(self):
        with patch.object(type(self.invoice), '_cr_einvoice_alert', side_effect=ValueError('no access')):
            self.invoice._cr_einvoice_fail('CABYS missing')
        self.assertEqual(self.invoice.state_tributacion, 'error')
        self.assertEqual(self.invoice.einvoice_error_detail, 'CABYS missing')

    def test_fec_with_hacienda_down_asks_to_send_it_again(self):
        fec = self.env['account.move'].create({'move_type': 'in_invoice', 'partner_id': self.customer.id,
                                               'journal_id': self.purchases.id, 'tipo_documento': 'FEC'})
        fec._cr_einvoice_hacienda_unavailable('timeout')
        self.assertEqual(fec.state_tributacion, 'error', "no cron sends a FEC again")
        self.assertIn('Send FEC', fec.einvoice_error_detail)
        mail = self.env['mail.mail'].search([('email_to', '=', ISSUE_EMAIL), ('res_id', '=', fec.id)])
        self.assertIn('Send FEC', mail.body_html)

    def test_hacienda_down_while_checking_keeps_the_states(self):
        self.env.cr.execute("UPDATE account_move SET state = 'posted', state_tributacion = 'procesando' WHERE id = %s",
                            (self.invoice.id,))
        self.invoice.invalidate_recordset()
        with patch.object(api_facturae, 'get_token_hacienda',
                          side_effect=api_facturae.HaciendaUnavailable('timeout')):
            self.env['account.move']._check_hacienda_for_invoices_company(self.company)
        self.assertEqual(self.invoice.state_tributacion, 'procesando')
        self.assertFalse(self._alert_mails())

    # ------------------------------------------------------------------ Retry Sending

    def _retry(self, answer):
        sent = []
        with patch.object(api_facturae, 'get_token_hacienda', return_value='token'), \
                patch.object(api_facturae, 'consulta_clave', return_value=answer), \
                patch.object(type(self.invoice), 'generate_and_send_invoice', lambda move: sent.append(move)):
            self.invoice.action_cr_einvoice_retry()
        return sent

    def test_retry_builds_the_xml_again_when_hacienda_never_got_it(self):
        self.invoice._cr_einvoice_fail('CABYS missing')
        self.invoice.error_count = 11
        sent = self._retry({'status': 400, 'ind-estado': 'error'})
        self.assertEqual(sent, [self.invoice])
        self.assertFalse(self.invoice.xml_comprobante, "built again from the corrected data")
        self.assertEqual((self.invoice.error_count, self.invoice.einvoice_error_detail), (0, False))
        kept = self.invoice.message_ids.attachment_ids.mapped('name')
        self.assertIn('FE_' + CLAVE + '.xml', kept, "the XML that was not received stays in the chatter")

    def test_retry_takes_hacienda_answer_when_it_already_has_it(self):
        self.invoice._cr_einvoice_fail('timeout after sending')
        sent = self._retry({'status': 200, 'ind-estado': 'procesando'})
        self.assertEqual(sent, [])
        self.assertEqual(self.invoice.state_tributacion, 'procesando')
        self.assertTrue(self.invoice.xml_comprobante)

    def test_retry_with_hacienda_down_changes_nothing(self):
        self.invoice._cr_einvoice_fail('CABYS missing')
        with patch.object(api_facturae, 'get_token_hacienda',
                          side_effect=api_facturae.HaciendaUnavailable('down')), \
                self.assertRaises(UserError):
            self.invoice.action_cr_einvoice_retry()
        self.assertEqual(self.invoice.state_tributacion, 'error')

    # ------------------------------------------------------------------ Issue Replacement

    def test_replacement_of_a_rejected_document(self):
        self.invoice._cr_einvoice_fail('Receptor no existe', state='rechazado')
        sent = []
        with patch.object(type(self.invoice), 'get_invoice_sequence', lambda move: ('FE', '0000000009')), \
                patch.object(api_facturae, 'get_clave_hacienda',
                             return_value={'clave': NEW_CLAVE, 'consecutivo': NEW_CONSECUTIVO}), \
                patch.object(type(self.invoice), 'generate_and_send_invoice', lambda move: sent.append(move)):
            self.invoice.action_cr_einvoice_replace()
        invoice = self.invoice
        self.assertEqual(sent, [invoice])
        self.assertEqual((invoice.number_electronic, invoice.sequence, invoice.name),
                         (NEW_CLAVE, NEW_CONSECUTIVO, NEW_CONSECUTIVO))
        self.assertFalse(invoice.state_tributacion)
        self.assertEqual(invoice.reference_code_id.code, '16')
        self.assertEqual(invoice.reference_document_id.code, '01')
        self.assertEqual(invoice.not_loaded_invoice, CLAVE)
        self.assertEqual(str(invoice.not_loaded_invoice_date), '2026-11-26', "the rejected one's issue date")
        self.assertFalse(invoice.xml_comprobante)
        self.assertIn('FE_' + CLAVE + '.xml', invoice.message_ids.attachment_ids.mapped('name'))

    def test_a_second_replacement_refers_to_the_one_it_replaces(self):
        self.invoice._cr_einvoice_fail('Receptor no existe', state='rechazado')
        keys = iter([(NEW_CLAVE, NEW_CONSECUTIVO), (THIRD_CLAVE, THIRD_CONSECUTIVO)])

        def clave(*args):
            key, consecutivo = next(keys)
            return {'clave': key, 'consecutivo': consecutivo}

        with patch.object(type(self.invoice), 'get_invoice_sequence', lambda move: ('FE', '0000000009')), \
                patch.object(api_facturae, 'get_clave_hacienda', clave), \
                patch.object(type(self.invoice), 'generate_and_send_invoice', lambda move: None):
            self.invoice.action_cr_einvoice_replace()
            self.invoice.write({'state_tributacion': 'rechazado', 'date_issuance': '2026-11-27T09:00:00-06:00'})
            self.invoice.action_cr_einvoice_replace()
        self.assertEqual(self.invoice.number_electronic, THIRD_CLAVE)
        self.assertEqual(self.invoice.not_loaded_invoice, NEW_CLAVE)
        self.assertEqual(str(self.invoice.not_loaded_invoice_date), '2026-11-27')

    def test_replacement_of_an_export_invoice_refers_to_an_export_invoice(self):
        self.invoice.write({'tipo_documento': 'FEE', 'state_tributacion': 'rechazado'})
        with patch.object(type(self.invoice), 'get_invoice_sequence', lambda move: ('FEE', '0000000009')), \
                patch.object(api_facturae, 'get_clave_hacienda',
                             return_value={'clave': NEW_CLAVE, 'consecutivo': NEW_CONSECUTIVO}), \
                patch.object(type(self.invoice), 'generate_and_send_invoice', lambda move: None):
            self.invoice.action_cr_einvoice_replace()
        self.assertEqual(self.invoice.reference_document_id.code, '19')

    def test_replacement_of_a_credit_note_keeps_its_reference(self):
        note = self.env['account.move'].create({
            'move_type': 'out_refund', 'journal_id': self.journal.id, 'partner_id': self.customer.id,
            'tipo_documento': 'NC', 'number_electronic': NOTE_CLAVE, 'invoice_id': self.invoice.id,
            'reference_code_id': self.env.ref('cr_electronic_invoice.ReferenceCode_1').id,
        })
        note.state_tributacion = 'rechazado'
        with patch.object(type(note), 'get_invoice_sequence', lambda move: ('NC', '0000000009')), \
                patch.object(api_facturae, 'get_clave_hacienda',
                             return_value={'clave': NEW_CLAVE, 'consecutivo': NEW_CONSECUTIVO}), \
                patch.object(type(note), 'generate_and_send_invoice', lambda move: None):
            note.action_cr_einvoice_replace()
        self.assertEqual(note.number_electronic, NEW_CLAVE)
        self.assertEqual(note.reference_code_id, self.env.ref('cr_electronic_invoice.ReferenceCode_1'))
        self.assertFalse(note.not_loaded_invoice)

    def test_a_factura_for_a_customer_without_id_is_numbered_as_a_ticket(self):
        self.journal.TE_sequence_id = self.env['ir.sequence'].create({'name': 'TE prueba', 'padding': 10})
        self.customer.vat = False
        self.assertEqual(self.invoice.get_invoice_sequence(), ('TE', '0000000001'))
        self.assertEqual(self.invoice.tipo_documento, 'TE')
