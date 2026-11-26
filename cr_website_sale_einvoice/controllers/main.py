import re
import time
from collections import defaultdict

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import single_email_re

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.main import WebsiteSale

ERROR_KEY = 'cr_einvoice_error'
PENDING_KEY = 'cr_einvoice_pending'
LOOKUPS_KEY = 'cr_einvoice_lookups'
# Hacienda lookups per hour: enough for typos, not for scraping the registry through the store. Counted per
# session and, since a new session is one cookie away, per IP address too (per server process).
MAX_LOOKUPS_PER_HOUR = 10
MAX_LOOKUPS_PER_IP_HOUR = 30
COSTA_RICA_PHONE_DIGITS = 8
_lookups_by_ip = defaultdict(list)


def _recent(stamps, now):
    return [stamp for stamp in stamps if now - stamp < 3600]


def _lookup_allowed():
    now = time.time()
    by_session = _recent(request.session.get(LOOKUPS_KEY, []), now)
    ip = request.httprequest.remote_addr
    by_ip = _lookups_by_ip[ip] = _recent(_lookups_by_ip[ip], now)
    if len(by_session) >= MAX_LOOKUPS_PER_HOUR or len(by_ip) >= MAX_LOOKUPS_PER_IP_HOUR:
        return False
    request.session[LOOKUPS_KEY] = by_session + [now]
    by_ip.append(now)
    return True


def _lookup(partner_sudo, id_code, number, third_party):
    """Hacienda's answer for a number: the pending one (same number, waiting for an activity) or a new
    lookup. Returns (lookup, error)."""
    pending = request.session.get(PENDING_KEY) or {}
    if (pending.get('number'), pending.get('id_code'), bool(pending.get('third_party'))) == \
            (number, id_code, third_party):
        lookup = pending['lookup']
    elif _lookup_allowed():
        lookup = partner_sudo._cr_hacienda_lookup(number)
    else:
        return None, _("Too many identification lookups. Try again in an hour.")
    if lookup and lookup['id_code'] and lookup['id_code'] != id_code:
        return None, _("Hacienda registers this number with another identification type. Check the type.")
    return lookup, None


def save_einvoice_data(partner_sudo, id_code, number, activity_code=None, third_party=False, email=None):
    """Validate, look up in Hacienda and save electronic invoice data: the customer's own, or a third
    party's (another person or a company) for whom a receptor partner is created.

    Returns (verified, error, receptor). When Hacienda lists several activities and none was chosen yet,
    the answer waits in the session and the form asks for one (verified and error are None).
    """
    try:
        number = partner_sudo._cr_check_own_identification(id_code, number, third_party=third_party)
    except UserError as error:
        return False, error.args[0], None
    if third_party and not single_email_re.match(email or ''):
        return False, _("Write the e-mail address where the third party receives the invoice."), None
    lookup, error = _lookup(partner_sudo, id_code, number, third_party)
    if error:
        return False, error, None
    activity_codes = [code for code, __ in (lookup or {}).get('choices', [])]
    if len(activity_codes) > 1 and activity_code not in activity_codes:
        request.session[PENDING_KEY] = {'number': number, 'id_code': id_code, 'lookup': lookup,
                                        'third_party': third_party, 'email': email}
        return None, None, None
    request.session.pop(PENDING_KEY, None)
    if third_party:
        receptor = partner_sudo._cr_third_party_receptor(id_code, number, email, lookup=lookup,
                                                         activity_code=activity_code)
    else:
        receptor = partner_sudo
        partner_sudo._cr_set_einvoice_data(id_code, number, lookup=lookup, activity_code=activity_code)
    return bool(lookup), None, receptor


class EinvoiceWebsiteSale(WebsiteSale):

    @http.route('/shop/einvoice', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def shop_einvoice(self, requested=None, identification_type=None, vat=None, activity=None, **kw):
        """The checkout's electronic invoice section: request it (with the customer's data) or not."""
        order_sudo = request.cart
        if redirection := self._check_cart(order_sudo):
            return redirection
        if not requested:
            request.session.pop(PENDING_KEY, None)
            order_sudo.write({'cr_einvoice_requested': False, 'cr_einvoice_choice_made': True})
            return request.redirect('/shop/checkout')
        partner_sudo = order_sudo.partner_invoice_id.commercial_partner_id
        if partner_sudo.is_company and not kw.get('third_party'):
            # A company's data is kept by the sales team: the customer only chooses to get the FE.
            if not partner_sudo._cr_einvoice_ready():
                request.session[ERROR_KEY] = _("Your company's billing data is incomplete. Contact us to "
                                               "complete it.")
                return request.redirect('/shop/checkout#cr_einvoice')
            order_sudo.write({'cr_einvoice_requested': True, 'cr_einvoice_choice_made': True,
                              'cr_einvoice_partner_id': False})
            return request.redirect('/shop/checkout')
        if not partner_sudo._can_be_edited_by_current_customer(order_sudo=order_sudo):
            raise request.not_found()
        third_party = bool(kw.get('third_party'))
        if third_party:
            verified, error, receptor = save_einvoice_data(
                partner_sudo, kw.get('third_type'), kw.get('third_vat'), activity, third_party=True,
                email=(kw.get('third_email') or '').strip())
        else:
            verified, error, receptor = save_einvoice_data(partner_sudo, identification_type, vat, activity)
        if error:
            request.session[ERROR_KEY] = error
        if error or verified is None:
            return request.redirect('/shop/checkout#cr_einvoice')
        order_sudo.write({'cr_einvoice_requested': True, 'cr_einvoice_choice_made': True,
                          'cr_einvoice_partner_id': receptor.id if third_party else False})
        return request.redirect('/shop/checkout')

    def _validate_address_values(self, address_values, partner_sudo, address_type, *args, **kwargs):
        """Costa Rica phone numbers have 8 digits: the delivery depends on reaching the customer."""
        invalid_fields, missing_fields, error_messages = super()._validate_address_values(
            address_values, partner_sudo, address_type, *args, **kwargs)
        country = request.env['res.country'].browse(address_values.get('country_id')).exists()
        phone = address_values.get('phone')
        if phone and country.code == 'CR':
            digits = re.sub(r'\D', '', phone)
            if digits.startswith('506') and len(digits) == COSTA_RICA_PHONE_DIGITS + 3:
                digits = digits[3:]
            if len(digits) != COSTA_RICA_PHONE_DIGITS:
                invalid_fields.add('phone')
                error_messages.append(_("The phone number must have 8 digits."))
        return invalid_fields, missing_fields, error_messages


class EinvoicePortal(CustomerPortal):

    @http.route('/my/einvoice', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_einvoice(self, identification_type=None, vat=None, activity=None, **kw):
        """The customer's electronic invoice data, in their account."""
        partner_sudo = request.env.user.partner_id.commercial_partner_id.sudo()
        saved = False
        if request.httprequest.method == 'POST' and not partner_sudo.is_company:
            verified, error, __ = save_einvoice_data(partner_sudo, identification_type, vat, activity)
            if error:
                request.session[ERROR_KEY] = error
            saved = not error and verified is not None
        return request.render('cr_website_sale_einvoice.portal_einvoice_page', {
            'einvoice_partner': partner_sudo, 'einvoice_saved': saved, 'page_name': 'einvoice',
        })
