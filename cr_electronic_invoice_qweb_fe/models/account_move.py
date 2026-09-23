from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_name_invoice_report(self):
        # Odoo's hook for localisations to print their own invoice (see l10n_ar / l10n_cl).
        # Limited to Costa Rican companies: the document is the Hacienda (DGT) layout.
        self.ensure_one()
        if self.company_id.country_code == 'CR':
            return 'cr_electronic_invoice_qweb_fe.report_invoice_document'
        return super()._get_name_invoice_report()
