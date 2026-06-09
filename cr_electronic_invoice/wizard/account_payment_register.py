
from odoo import models, fields
import re
from datetime import datetime
import base64
from ..models import api_facturae, fe_enums

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'
    
    def _create_payments(self):
        payments = super()._create_payments()

        active_invoices = self.env["account.move"].browse(self.env.context.get("active_ids", []))

        for payment in payments:
            if payment.payment_type != 'inbound':
                continue

            # Match this payment to the invoices it was reconciled against
            invoice = payment.reconciled_invoice_ids & active_invoices
            if not invoice:
                continue
            invoice = invoice[0]

            sucursal_id = payment.move_id.journal_id.sucursal or self.env.user.company_id.sucursal_MR
            terminal_id = payment.move_id.journal_id.terminal or self.env.user.company_id.terminal_MR
            sequence = self.env['ir.sequence'].next_by_code('sequence.REP')
            payment.sequence = f"{sucursal_id}{terminal_id}{fe_enums.TipoDocumento['REP']}{sequence}"

            response_json = api_facturae.get_clave_hacienda(payment, 'REP', sequence, sucursal_id, terminal_id)
            if response_json:
                payment.clave = response_json.get('clave')
                payment.sequence = response_json.get('consecutivo')

            if invoice.rep_string:
                updated_rep_string_date = re.sub(r"<FechaEmision[^>]*>(.*?)</FechaEmision>", r"<FechaEmision>" + api_facturae.get_time_hacienda() + r"</FechaEmision>", invoice.rep_string)
                updated_rep_string_clave = re.sub(r"<Clave[^>]*>(.*?)</Clave>", r"<Clave>" + payment.clave + r"</Clave>", updated_rep_string_date)
                updated_rep_string_sequence = re.sub(r"<NumeroConsecutivo[^>]*>(.*?)</NumeroConsecutivo>", r"<NumeroConsecutivo>" + payment.sequence + r"</NumeroConsecutivo>", updated_rep_string_clave)

                xml_to_sign = str(updated_rep_string_sequence)
                xml_firmado = api_facturae.sign_xml(invoice.company_id.signature, invoice.company_id.frm_pin, xml_to_sign)
                payment.fname_xml_comprobante = f"REP_{response_json.get('clave')}.xml"
                self.env['ir.attachment'].sudo().create({
                    'name': payment.fname_xml_comprobante,
                    'type': 'binary',
                    'datas': base64.b64encode(xml_firmado),
                    'res_model': 'account.payment',
                    'res_id': payment.id,
                    'res_field': 'xml_comprobante',
                    'res_name': payment.fname_xml_comprobante,
                    'mimetype': 'text/xml',
                })

                token_m_h = api_facturae.get_token_hacienda(invoice, invoice.company_id.frm_ws_ambiente)
                api_facturae.send_xml_rep(invoice, payment.clave, token_m_h, api_facturae.get_time_hacienda(), xml_firmado, invoice.company_id.frm_ws_ambiente)
                response_json_consulta_clave = api_facturae.consulta_clave(payment.clave, token_m_h, invoice.company_id.frm_ws_ambiente)
                estado_m_h = response_json_consulta_clave.get('ind-estado')
                payment.state_tributacion = estado_m_h

                if estado_m_h != 'procesando':
                    payment.fname_xml_respuesta_tributacion = f"AHC_{payment.clave}.xml"
                    self.env['ir.attachment'].create({
                        'name': payment.fname_xml_respuesta_tributacion,
                        'type': 'binary',
                        'datas': response_json_consulta_clave.get('respuesta-xml'),
                        'res_model': 'account.payment',
                        'res_id': payment.id,
                        'res_field': 'xml_respuesta_tributacion',
                        'res_name': payment.fname_xml_respuesta_tributacion,
                        'mimetype': 'text/xml',
                    })

        return payments