import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.cr_electronic_invoice.models import api_facturae
from odoo.addons.cr_electronic_invoice.models.identification import LEGAL_ID_CODE, clean_identification, is_legal_id

_logger = logging.getLogger(__name__)

# A customer waits on the checkout page while Hacienda answers.
HACIENDA_TIMEOUT = 5
# A customer asks for an electronic invoice in their own name: cédula física, DIMEX or NITE. Invoices to a
# company (cédula jurídica) are set up by the sales team, who link the customer to that company.
OWN_NAME_ID_TYPES = ('01', '03', '04')
# An invoice in a third party's name (another person or a company) may also go to a cédula jurídica.
THIRD_PARTY_ID_TYPES = ('01', LEGAL_ID_CODE, '03', '04')
# As cr_electronic_invoice checks them when posting the invoice.
ID_LENGTHS = {'01': (9,), '03': (11, 12), '04': (10,)}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    cr_einvoice_requested_by_id = fields.Many2one(
        'res.partner', string="Electronic Invoice Requested By", copy=False, index='btree_not_null',
        help="The website customer who asked for electronic invoices in this partner's name (a third party).")
    cr_einvoice_checked = fields.Boolean(
        string="Billing Data Checked with Hacienda", copy=False,
        help="Set when the customer saved their electronic invoice data on the website and Hacienda's registry "
             "confirmed it; cleared when Hacienda could not be reached.")

    def _cr_einvoice_ready(self):
        """Whether an electronic invoice (FE) can be issued to this partner: ID type and number set."""
        self.ensure_one()
        commercial = self.commercial_partner_id
        return bool(commercial.vat and commercial.identification_id)

    def _cr_check_own_identification(self, id_code, number, third_party=False):
        """Validate an identification typed by a customer and return it cleaned."""
        if id_code not in (THIRD_PARTY_ID_TYPES if third_party else OWN_NAME_ID_TYPES):
            raise UserError(_("Choose a personal identification type: cédula física, DIMEX or NITE."))
        number = clean_identification(number, id_code)
        if id_code == LEGAL_ID_CODE:
            if not is_legal_id(number):
                raise UserError(_("A cédula jurídica has 10 characters without dashes, for example 3101123456."))
            return number
        if not number.isdigit() or number.startswith('0') or len(number) not in ID_LENGTHS[id_code]:
            lengths = _(" or ").join(str(length) for length in ID_LENGTHS[id_code])
            raise UserError(_("The identification number must have %(lengths)s digits, with no leading zero, "
                              "dashes or spaces.", lengths=lengths))
        return number

    def _cr_hacienda_lookup(self, number):
        """Look an identification up in Hacienda's public taxpayer registry.

        Returns a dict with `name`, `id_code`, `activities` (Hacienda's active ones) and `choices`
        ([code, description]), JSON-friendly so it can wait in the session; or None when Hacienda does
        not answer or does not know the number.
        """
        answer = api_facturae.get_economic_activities(self, vat=number, timeout=HACIENDA_TIMEOUT)
        if answer.get('status') != 200:
            _logger.info("Hacienda taxpayer lookup unavailable: %s", answer.get('text'))
            return None
        activities = [activity for activity in answer.get('activities') or []
                      if activity.get('estado') == 'A' and activity.get('codigo')]
        return {
            'name': (answer.get('name') or '').strip(),
            'id_code': answer.get('id_type'),
            'activities': activities,
            'choices': [[activity['codigo'], activity.get('descripcion') or activity['codigo']]
                        for activity in activities],
        }

    def _cr_set_einvoice_data(self, id_code, number, lookup=None, activity_code=None):
        """Save the customer's electronic invoice data on this (commercial) partner.

        With a Hacienda answer, the name and the economic activities come from Hacienda; without one
        (Hacienda down or number not registered), the partner keeps its name and has no activity.
        """
        self.ensure_one()
        # sudo: identification types and economic activities are restricted to accounting; the type's
        # record is only read, and the activities come from Hacienda's answer.
        id_type = self.env['identification.type'].sudo().search([('code', '=', id_code)], limit=1)
        vals = {'identification_id': id_type.id, 'vat': number, 'cr_einvoice_checked': bool(lookup)}
        if lookup:
            activities = self.env['economic.activity'].sudo()._from_hacienda(lookup['activities'])
            chosen = activities.filtered(lambda activity: activity.code == activity_code)[:1]
            vals.update(economic_activities_ids=[(6, 0, activities.ids)],
                        activity_id=(chosen or activities[:1]).id)
            if lookup['name']:
                vals['name'] = lookup['name']
        self.write(vals)

    def _cr_third_party_receptor(self, id_code, number, email, lookup=None, activity_code=None, lang=None):
        """The partner an electronic invoice is issued to on behalf of this customer: the one this customer
        already registered with that identification, or a new one. Existing partners of other customers are
        never reused or changed from the website.

        `lang` is the language the customer is buying in: the invoice e-mails go out in it."""
        self.ensure_one()
        receptor = self.search([('cr_einvoice_requested_by_id', '=', self.id), ('vat', '=', number)], limit=1)
        if not receptor:
            receptor = self.create({
                'name': (lookup or {}).get('name') or number,
                'is_company': id_code == LEGAL_ID_CODE,
                'cr_einvoice_requested_by_id': self.id,
                'country_id': self.env.ref('base.cr').id,
            })
        receptor.email = email
        if lang:
            receptor.lang = lang
        receptor._cr_set_einvoice_data(id_code, number, lookup=lookup, activity_code=activity_code)
        return receptor
