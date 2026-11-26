from unittest.mock import patch

import requests

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.cr_website_sale_einvoice.controllers.main import (
    ERROR_KEY,
    MAX_LOOKUPS_PER_HOUR,
    PENDING_KEY,
    EinvoicePortal,
    EinvoiceWebsiteSale,
)
from odoo.addons.website_sale.tests.common import MockRequest

API = 'odoo.addons.cr_electronic_invoice.models.api_facturae'
LOOKUP = f'{API}.requests.get'


class FakeResponse:

    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self.reason = 'Not Found'
        self._data = data or {}

    def json(self):
        return self._data


def hacienda(name='JUANA PEREZ MORA', id_code='01', activities=()):
    return FakeResponse(data={
        'nombre': name, 'tipoIdentificacion': id_code,
        'actividades': [{'estado': 'A', 'tipo': 'B', 'codigo': code, 'descripcion': f'Actividad {code}'}
                        for code in activities] + [{'estado': 'I', 'codigo': '999999', 'descripcion': 'Inactiva'}],
    })


@tagged('post_install', '-at_install')
class TestCheckoutEinvoice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        cls.user = cls.env['res.users'].create({
            'name': 'Juana', 'login': 'fe_juana', 'email': 'juana@example.com',
            'group_ids': [(6, 0, cls.env.ref('base.group_portal').ids)],
        })
        cls.customer = cls.user.partner_id
        cls.product = cls.env['product.product'].create({'name': 'Producto FE', 'list_price': 1000})

    def setUp(self):
        super().setUp()
        self.cart = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'website_id': self.website.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})],
        })

    def _submit(self, session=None, **form):
        # The cart belongs to the signed-in customer: Odoo ignores another customer's cart.
        with MockRequest(self.env(user=self.user), website=self.website.with_user(self.user),
                         sale_order_id=self.cart.id) as request:
            request.session.update(session or {})
            EinvoiceWebsiteSale().shop_einvoice(**form)
            return dict(request.session)

    def test_without_einvoice_the_order_gets_a_ticket(self):
        self.assertFalse(self.cart.cr_einvoice_requested)
        self.assertEqual(self.cart._prepare_invoice()['tipo_documento'], 'TE')

    def test_einvoice_with_one_activity_is_saved_from_hacienda(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])) as lookup:
            self._submit(requested='1', identification_type='01', vat='1-1234-0567')
        lookup.assert_called_once()
        self.assertEqual(self.customer.vat, '112340567', "stored the way Hacienda expects it")
        self.assertEqual(self.customer.identification_id.code, '01')
        self.assertEqual(self.customer.name, 'JUANA PEREZ MORA', "the name comes from Hacienda")
        self.assertEqual(self.customer.activity_id.code, '523101')
        self.assertNotIn('999999', self.customer.economic_activities_ids.mapped('code'), "inactive left out")
        self.assertTrue(self.cart.cr_einvoice_requested and self.cart.cr_einvoice_verified)
        self.assertEqual(self.cart._prepare_invoice()['tipo_documento'], 'FE')

    def test_several_activities_ask_which_one(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101', '552001'])) as lookup:
            session = self._submit(requested='1', identification_type='01', vat='112340567')
            self.assertFalse(self.customer.vat, "nothing saved until an activity is chosen")
            self.assertEqual(session[PENDING_KEY]['number'], '112340567')
            session = self._submit(session=session, requested='1', identification_type='01', vat='112340567',
                                   activity='552001')
        self.assertEqual(lookup.call_count, 1, "the second step reuses Hacienda's answer")
        self.assertEqual(self.customer.activity_id.code, '552001')
        self.assertNotIn(PENDING_KEY, session)
        self.assertTrue(self.cart.cr_einvoice_requested)

    @mute_logger(API)  # Hacienda failing is the point of this test.
    def test_hacienda_down_saves_unverified(self):
        with patch(LOOKUP, side_effect=requests.exceptions.Timeout()):
            self._submit(requested='1', identification_type='01', vat='112340567')
        self.assertEqual(self.customer.vat, '112340567')
        self.assertEqual(self.customer.name, 'Juana', "keeps the account name")
        self.assertTrue(self.cart.cr_einvoice_requested)
        self.assertFalse(self.cart.cr_einvoice_verified, "the sales team sees it needs checking")

    def test_company_ids_and_bad_numbers_are_refused(self):
        for id_code, number in (('02', '3101123456'), ('01', '12345'), ('01', '012345678'), ('03', '123'),
                                ('04', '123456789')):
            with self.subTest(id_code=id_code, number=number), patch(LOOKUP) as lookup:
                session = self._submit(requested='1', identification_type=id_code, vat=number)
                self.assertTrue(session.get(ERROR_KEY))
                lookup.assert_not_called()
        self.assertFalse(self.customer.vat)
        self.assertFalse(self.cart.cr_einvoice_requested)

    def test_type_must_match_hacienda(self):
        with patch(LOOKUP, return_value=hacienda(id_code='03')):
            session = self._submit(requested='1', identification_type='01', vat='112340567')
        self.assertIn('another identification type', session[ERROR_KEY])
        self.assertFalse(self.customer.vat)

    @mute_logger(API)  # Hacienda failing is the point of this test.
    def test_lookups_are_limited(self):
        with patch(LOOKUP, return_value=FakeResponse(404)) as lookup:
            session = {}
            for __ in range(MAX_LOOKUPS_PER_HOUR + 1):
                session = self._submit(session=session, requested='1', identification_type='01', vat='112340567')
        self.assertEqual(lookup.call_count, MAX_LOOKUPS_PER_HOUR)
        self.assertIn('Too many', session[ERROR_KEY])

    def test_customer_can_switch_back_to_a_ticket(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])):
            self._submit(requested='1', identification_type='01', vat='112340567')
        self._submit()
        self.assertFalse(self.cart.cr_einvoice_requested)
        self.assertEqual(self.cart._prepare_invoice()['tipo_documento'], 'TE')
        next_cart = self.cart.copy()
        self.assertTrue(next_cart.cr_einvoice_requested, "the next order offers the FE again by default")

    def test_company_data_is_kept_by_the_sales_team(self):
        company = self.env['res.partner'].create({
            'name': 'Restaurante S.A.', 'is_company': True, 'vat': '3101123456',
            'identification_id': self.env['identification.type'].search([('code', '=', '02')]).id,
        })
        self.customer.parent_id = company
        self.cart.partner_invoice_id = self.customer
        with patch(LOOKUP) as lookup:
            self._submit(requested='1', identification_type='01', vat='112340567')
        lookup.assert_not_called()
        self.assertEqual(company.vat, '3101123456', "the customer can't change the company's data")
        self.assertTrue(self.cart.cr_einvoice_requested)
        self.assertEqual(self.cart._prepare_invoice()['tipo_documento'], 'FE')

    def test_invoice_in_a_third_partys_name(self):
        with patch(LOOKUP, return_value=hacienda(name='EMPRESA TERCERA S.A.', id_code='02', activities=['5610.0'])):
            self._submit(requested='1', third_party='1', third_type='02', third_vat='3-101-123456',
                         third_email='facturas@tercera.example')
        receptor = self.cart.cr_einvoice_partner_id
        self.assertEqual((receptor.name, receptor.vat, receptor.is_company),
                         ('EMPRESA TERCERA S.A.', '3101123456', True))
        self.assertEqual(receptor.email, 'facturas@tercera.example')
        self.assertEqual(receptor.cr_einvoice_requested_by_id, self.customer)
        self.assertFalse(self.customer.vat, "the customer's own data is untouched")
        invoice_vals = self.cart._prepare_invoice()
        self.assertEqual((invoice_vals['tipo_documento'], invoice_vals['partner_id']), ('FE', receptor.id))

    def test_third_party_needs_an_email_and_is_reused(self):
        with patch(LOOKUP) as lookup:
            session = self._submit(requested='1', third_party='1', third_type='02', third_vat='3101123456')
        self.assertIn('e-mail', session[ERROR_KEY])
        lookup.assert_not_called()
        with patch(LOOKUP, return_value=hacienda(name='TERCERA', id_code='02', activities=['5610.0'])):
            self._submit(requested='1', third_party='1', third_type='02', third_vat='3101123456', third_email='a@b.cr')
            first = self.cart.cr_einvoice_partner_id
            self._submit(requested='1', third_party='1', third_type='02', third_vat='3101123456', third_email='c@d.cr')
        self.assertEqual(self.cart.cr_einvoice_partner_id, first, "the same third party is not duplicated")
        self.assertEqual(first.email, 'c@d.cr')

    def test_taxpayers_get_the_einvoice_by_default(self):
        with patch(LOOKUP, return_value=hacienda(activities=[])):
            self._submit(requested='1', identification_type='01', vat='112340567')
        self.assertFalse(self.cart.copy().cr_einvoice_requested, "without an activity: ticket by default")
        self.customer.activity_id = self.env['economic.activity'].sudo().create({'code': '4773.0', 'name': 'Venta'})
        self.assertTrue(self.cart.copy().cr_einvoice_requested, "a taxpayer gets the FE by default")

    def test_backend_orders_keep_the_module_choice_and_export_is_fee(self):
        backend = self.cart.copy({'website_id': False})
        self.assertNotIn('tipo_documento', backend._prepare_invoice())
        self.customer.export = True
        self.assertEqual(self.cart._prepare_invoice()['tipo_documento'], 'FEE')

    def test_nite_has_ten_digits(self):
        with patch(LOOKUP, return_value=hacienda(id_code='04', activities=['523101'])):
            session = self._submit(requested='1', identification_type='04', vat='1234567890')
        self.assertFalse(session.get(ERROR_KEY))
        self.assertEqual(self.customer.vat, '1234567890')

    def test_switching_off_forgets_a_pending_activity_choice(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101', '552001'])):
            session = self._submit(requested='1', identification_type='01', vat='112340567')
        self.assertIn(PENDING_KEY, session)
        session = self._submit(session=session)
        self.assertNotIn(PENDING_KEY, session)
        self.assertFalse(self.cart.cr_einvoice_requested)

    def test_a_new_billing_address_keeps_the_choice(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])):
            self._submit(requested='1', identification_type='01', vat='112340567')
        self._submit()
        other = self.env['res.partner'].create({'name': 'Oficina', 'type': 'invoice', 'parent_id': self.customer.id})
        self.cart.partner_invoice_id = other
        self.assertFalse(self.cart.cr_einvoice_requested, "the customer said no electronic invoice")

    def test_einvoice_goes_to_the_customer_not_to_an_invoice_address(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])):
            self._submit(requested='1', identification_type='01', vat='112340567')
        address = self.env['res.partner'].create({'name': 'Oficina', 'type': 'invoice', 'parent_id': self.customer.id})
        self.cart.partner_invoice_id = address
        self.assertFalse(address.identification_id, "an address shares the number but not the type")
        invoice_vals = self.cart._prepare_invoice()
        self.assertEqual(invoice_vals['tipo_documento'], 'FE')
        self.assertEqual(invoice_vals['partner_id'], self.customer.id)

    def test_checked_data_is_remembered_for_the_next_order(self):
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])):
            self._submit(requested='1', identification_type='01', vat='112340567')
        next_cart = self.cart.copy()
        self.assertTrue(next_cart.cr_einvoice_requested and next_cart.cr_einvoice_verified)
        self.assertEqual(next_cart._prepare_invoice()['tipo_documento'], 'FE')


@tagged('post_install', '-at_install')
class TestPortalEinvoice(TransactionCase):

    def test_customer_updates_their_data_in_their_account(self):
        user = self.env['res.users'].create({
            'name': 'Cliente Portal', 'login': 'fe_portal', 'email': 'fe@example.com',
            'group_ids': [(6, 0, self.env.ref('base.group_portal').ids)],
        })
        website = self.env['website'].search([], limit=1)
        env = self.env(user=user)
        with patch(LOOKUP, return_value=hacienda(activities=['523101'])), \
                MockRequest(env, website=website.with_user(user)) as request:
            request.httprequest.method = 'POST'
            EinvoicePortal().portal_einvoice(identification_type='01', vat='112340567')
        self.assertEqual(user.partner_id.vat, '112340567')

    def test_address_forms_have_no_tax_id_input(self):
        """The ID is given with its type in the electronic invoice section; checked in /my/account's form and in the
        checkout's (/shop/address), a primary copy that sets its own condition on the same node."""
        for xmlid in ('portal.address_form_fields', 'website_sale.address_form_fields'):
            nodes = self.env.ref(xmlid)._get_combined_arch().xpath("//t[@name='b2b_fields']")
            self.assertEqual([node.get('t-if') for node in nodes], ['False'], xmlid)


@tagged('post_install', '-at_install')
class TestCostaRicaPhone(TransactionCase):

    def test_phone_needs_eight_digits(self):
        costa_rica = self.env.ref('base.cr')
        website = self.env['website'].search([], limit=1)
        controller = EinvoiceWebsiteSale()
        with MockRequest(self.env, website=website):
            for phone, valid in (('8780-6690', True), ('+506 8780 6690', True), ('8780669', False),
                                 ('506878066901', False)):
                with self.subTest(phone=phone):
                    invalid, __, __ = controller._validate_address_values(
                        {'phone': phone, 'country_id': costa_rica.id}, self.env['res.partner'], 'delivery',
                        False, '')
                    self.assertEqual('phone' not in invalid, valid)
