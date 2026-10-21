
from odoo import models, fields

# Nota 9: "Pago a comprobante electrónico" is only valid on the Recibo Electrónico de Pago,
# which is generated automatically, so it is never picked by hand on an invoice or a note.
REP_PAYMENT_CODE = '17'
MANUAL_REFERENCE_CODE_DOMAIN = [('code', '!=', REP_PAYMENT_CODE)]

# Nota 9, replacement documents: the new document that replaces an annulled one takes
# code 15 when the annulment used 13 (error material), and code 07 when it used 01.
# Not suggested automatically for now: whoever invoices picks it by hand.


class ReferenceCode(models.Model):
    _name = "reference.code"

    active = fields.Boolean(default=True)
    code = fields.Char()
    name = fields.Char()
