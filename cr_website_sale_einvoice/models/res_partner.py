import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

from odoo.addons.cr_electronic_invoice.models.identification import clean_identification

_logger = logging.getLogger(__name__)

HACIENDA_LOOKUP_URL = 'https://api.hacienda.go.cr/fe/ae'
HACIENDA_TIMEOUT = 8
# A customer asks for an electronic invoice in their own name: cédula física, DIMEX or NITE. Invoices to a
# company (cédula jurídica) are set up by the sales team, who link the customer to that company.
OWN_NAME_ID_TYPES = ('01', '03', '04')
ID_LENGTHS = {'01': (9,), '03': (11, 12), '04': (10,)}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _cr_einvoice_ready(self):
        """Whether an electronic invoice (FE) can be issued to this partner: ID type and number set."""
        self.ensure_one()
        commercial = self.commercial_partner_id
        return bool(commercial.vat and commercial.identification_id)

    def _cr_check_own_identification(self, id_code, number):
        """Validate an identification typed by a customer and return it cleaned (digits only)."""
        if id_code not in OWN_NAME_ID_TYPES:
            raise UserError(_("Choose a personal identification type: cédula física, DIMEX or NITE."))
        number = clean_identification(number, id_code)
        if not number.isdigit() or number.startswith('0') or len(number) not in ID_LENGTHS[id_code]:
            lengths = _(" or ").join(str(length) for length in ID_LENGTHS[id_code])
            raise UserError(_("The identification number must have %(lengths)s digits, with no leading zero, "
                              "dashes or spaces.", lengths=lengths))
        return number

    def _cr_hacienda_lookup(self, number):
        """Look an identification up in Hacienda's public taxpayer registry.

        Returns a dict with `name`, `id_code` and `activities` ([(code, description, sale type)], active
        ones), or None when Hacienda does not answer or does not know the number.
        """
        try:
            response = requests.get(HACIENDA_LOOKUP_URL, params={'identificacion': number},
                                    timeout=HACIENDA_TIMEOUT)
        except requests.exceptions.RequestException as error:
            _logger.warning("Hacienda taxpayer lookup failed: %s", error)
            return None
        if response.status_code != 200:
            _logger.info("Hacienda taxpayer lookup: HTTP %s", response.status_code)
            return None
        try:
            data = response.json()
        except ValueError:
            _logger.warning("Hacienda taxpayer lookup: unreadable answer")
            return None
        activities = [
            (activity['codigo'], activity.get('descripcion') or activity['codigo'],
             'services' if activity.get('tipo') == 'S' else 'goods')
            for activity in data.get('actividades') or []
            if activity.get('estado') == 'A' and activity.get('codigo')
        ]
        return {'name': (data.get('nombre') or '').strip(), 'id_code': data.get('tipoIdentificacion'),
                'activities': activities}

    def _cr_economic_activities(self, activities):
        """`economic.activity` records for Hacienda activities, created when missing."""
        # sudo: customers can't read or create economic activities; they come from Hacienda's answer.
        activity_model = self.env['economic.activity'].sudo().with_context(active_test=False)
        records = activity_model.search([('code', 'in', [code for code, __, __ in activities])])
        missing = [(code, name, sale_type) for code, name, sale_type in activities
                   if code not in records.mapped('code')]
        if missing:
            records |= activity_model.create([
                {'code': code, 'name': name, 'description': name, 'sale_type': sale_type}
                for code, name, sale_type in missing
            ])
        records.filtered(lambda activity: not activity.active).active = True
        return records

    def _cr_set_einvoice_data(self, id_code, number, lookup=None, activity_code=None):
        """Save the customer's electronic invoice data on this (commercial) partner.

        With a Hacienda answer, the name and the economic activities come from Hacienda; without one
        (Hacienda down or number not registered), the partner keeps its name and has no activity.
        """
        self.ensure_one()
        # sudo: identification types are restricted to accounting; only the type's record is read.
        id_type = self.env['identification.type'].sudo().search([('code', '=', id_code)], limit=1)
        vals = {'identification_id': id_type.id, 'vat': number}
        if lookup:
            activities = self._cr_economic_activities(lookup['activities'])
            chosen = activities.filtered(lambda activity: activity.code == activity_code)
            if not chosen and len(activities) == 1:
                chosen = activities
            vals.update(economic_activities_ids=[(6, 0, activities.ids)], activity_id=chosen.id)
            if lookup['name']:
                vals['name'] = lookup['name']
        self.write(vals)
