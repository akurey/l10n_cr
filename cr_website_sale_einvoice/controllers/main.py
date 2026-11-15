import re
import time

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.website_sale.controllers.main import WebsiteSale

ERROR_KEY = 'cr_einvoice_error'
PENDING_KEY = 'cr_einvoice_pending'
LOOKUPS_KEY = 'cr_einvoice_lookups'
# Hacienda lookups per session and hour: enough for typos, not for scraping the registry through us.
MAX_LOOKUPS_PER_HOUR = 10
COSTA_RICA_PHONE_DIGITS = 8


def _lookup_allowed():
    now = time.time()
    recent = [stamp for stamp in request.session.get(LOOKUPS_KEY, []) if now - stamp < 3600]
    if len(recent) >= MAX_LOOKUPS_PER_HOUR:
        return False
    request.session[LOOKUPS_KEY] = recent + [now]
    return True


def save_einvoice_data(partner_sudo, id_code, number, activity_code=None):
    """Validate, look up in Hacienda and save the customer's electronic invoice data.

    Returns (verified, error). When Hacienda lists several activities and none was chosen yet, the
    answer is kept in the session and the form asks for one (error is None, verified is None).
    """
    try:
        number = partner_sudo._cr_check_own_identification(id_code, number)
    except UserError as error:
        return False, error.args[0]
    pending = request.session.get(PENDING_KEY) or {}
    if pending.get('number') == number and pending.get('id_code') == id_code:
        lookup = pending['lookup']
    elif _lookup_allowed():
        lookup = partner_sudo._cr_hacienda_lookup(number)
    else:
        return False, _("Too many identification lookups. Try again in an hour.")
    if lookup and lookup['id_code'] and lookup['id_code'] != id_code:
        return False, _("Hacienda registers this number with another identification type. Check the type.")
    activity_codes = [code for code, __, __ in (lookup or {}).get('activities', [])]
    if len(activity_codes) > 1 and activity_code not in activity_codes:
        request.session[PENDING_KEY] = {'number': number, 'id_code': id_code, 'lookup': lookup}
        return None, None
    request.session.pop(PENDING_KEY, None)
    partner_sudo._cr_set_einvoice_data(id_code, number, lookup=lookup, activity_code=activity_code)
    return bool(lookup), None


class EinvoiceWebsiteSale(WebsiteSale):

    @http.route('/shop/einvoice', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def shop_einvoice(self, requested=None, identification_type=None, vat=None, activity=None, **kw):
        """The checkout's electronic invoice section: request it (with the customer's data) or not."""
        order_sudo = request.cart
        if redirection := self._check_cart(order_sudo):
            return redirection
        if not requested:
            order_sudo.cr_einvoice_requested = False
            return request.redirect('/shop/checkout')
        partner_sudo = order_sudo.partner_invoice_id.commercial_partner_id
        if partner_sudo.is_company:
            # A company's data is kept by the sales team: the customer only chooses to get the FE.
            if not partner_sudo._cr_einvoice_ready():
                request.session[ERROR_KEY] = _("Your company's billing data is incomplete. Contact us to "
                                               "complete it.")
                return request.redirect('/shop/checkout#cr_einvoice')
            order_sudo.write({'cr_einvoice_requested': True, 'cr_einvoice_verified': True})
            return request.redirect('/shop/checkout')
        if not partner_sudo._can_be_edited_by_current_customer(order_sudo=order_sudo):
            raise request.not_found()
        verified, error = save_einvoice_data(partner_sudo, identification_type, vat, activity)
        if error:
            request.session[ERROR_KEY] = error
        if error or verified is None:
            return request.redirect('/shop/checkout#cr_einvoice')
        order_sudo.write({'cr_einvoice_requested': True, 'cr_einvoice_verified': verified})
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
            verified, error = save_einvoice_data(partner_sudo, identification_type, vat, activity)
            if error:
                request.session[ERROR_KEY] = error
            saved = not error and verified is not None
        return request.render('cr_website_sale_einvoice.portal_einvoice_page', {
            'einvoice_partner': partner_sudo, 'einvoice_saved': saved, 'page_name': 'einvoice',
        })
