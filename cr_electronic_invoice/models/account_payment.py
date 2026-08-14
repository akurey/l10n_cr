
from odoo import models, fields
from ..models import api_facturae, fe_enums

class PaymentMethods(models.Model):
    _name = "payment.methods"

    active = fields.Boolean(default=True)
    sequence = fields.Char()
    name = fields.Char()
    notes = fields.Text()


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    sale_conditions_id = fields.Many2one("sale.conditions")
    
class AccountPayment(models.Model):
    _inherit = "account.payment"

    xml_comprobante = fields.Binary(string="XML", copy=False, attachment=True)
    fname_xml_comprobante = fields.Char(string="File name XML", copy=False)
    xml_respuesta_tributacion = fields.Binary(string="XML Tributación Response", copy=False, attachment=True)
    fname_xml_respuesta_tributacion = fields.Char(string="XML File Name Tributación Response",copy=False)
    state_tributacion = fields.Selection([('aceptado', 'Aceptado'),
                                          ('rechazado', 'Rechazado'),
                                          ('recibido', 'Recibido'),
                                          ('firma_invalida', 'Firma Inválida'),
                                          ('error', 'Error'),
                                          ('procesando', 'Procesando'),
                                          ('na', 'No Aplica'),
                                          ('ne', 'No Encontrado')], 'Estado REP', copy=False)
    sequence = fields.Char(string="Consecutive")
    clave = fields.Char(string="self.clave")
    
    
    def consult_rep_document(self):
        if self.move_id.company_id.frm_ws_ambiente == 'disabled':
            return
        token_m_h = api_facturae.get_token_hacienda(self.move_id, self.move_id.company_id.frm_ws_ambiente)
        response_json_consulta_clave = api_facturae.consulta_clave(self.clave, token_m_h, self.move_id.company_id.frm_ws_ambiente)
                
        estado_m_h = response_json_consulta_clave.get('ind-estado')
        self.state_tributacion = estado_m_h
        
        self.fname_xml_respuesta_tributacion = f"AHC_{self.clave}.xml"
        self.env['ir.attachment'].create({'name': self.fname_xml_respuesta_tributacion,
                                'type': 'binary',
                                'datas': response_json_consulta_clave.get('respuesta-xml'),
                                'res_model': 'account.payment',
                                'res_id': self.id,
                                'res_field': 'xml_respuesta_tributacion',
                                'res_name': self.fname_xml_respuesta_tributacion,
                                'mimetype': 'text/xml'})
        