import base64
import datetime
from unittest.mock import patch

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('not JSON')
        return self._payload


@tagged('post_install', '-at_install')
class TestTokenHacienda(TransactionCase):
    """Hacienda rejecting the token request (for instance a test user against the production
    realm) gives a readable error instead of an UnboundLocalError."""

    def setUp(self):
        super().setUp()
        # Module-level cache: start from no token for this company.
        api_facturae.last_tokens.pop(self.env.company.id, None)
        self.invoice = self.env['account.move'].new({'move_type': 'out_invoice'})

    def _token(self, response):
        with patch.object(api_facturae.requests, 'request', return_value=response):
            return api_facturae.get_token_hacienda(self.invoice, 'api-prod')

    def test_token_ok(self):
        token = self._token(FakeResponse(200, {'access_token': 'abc', 'expires_in': 300,
                                               'refresh_expires_in': 600}))
        self.assertEqual(token, 'abc')

    def test_rejected_credentials(self):
        with self.assertRaisesRegex(UserError, r'HTTP 401: Invalid user credentials.*ambiente Pruebas'):
            self._token(FakeResponse(401, {'error': 'invalid_grant',
                                           'error_description': 'Invalid user credentials'}))

    def test_rejected_with_a_non_json_answer(self):
        with self.assertRaisesRegex(UserError, r'HTTP 503: -'):
            self._token(FakeResponse(503, None))

    def test_button_logs_environment_and_expiration(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Llave de prueba')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
                .sign(key, hashes.SHA256()))
        company = self.env.company
        company.write({
            'frm_ws_ambiente': 'api-stag', 'frm_pin': '1234',
            'signature': base64.b64encode(pkcs12.serialize_key_and_certificates(
                b'prueba', key, cert, None, serialization.BestAvailableEncryption(b'1234'))),
        })
        api_facturae.last_tokens.pop(company.id, None)
        response = FakeResponse(200, {'access_token': 'abc', 'expires_in': 300, 'refresh_expires_in': 600})
        with patch.object(api_facturae.requests, 'request', return_value=response):
            company.test_get_token()
        body = company.message_ids[:1].body
        self.assertIn('Conexión correcta con Hacienda (Pruebas)', body)
        self.assertIn('La llave criptográfica vence el', body)

    def test_connection_error(self):
        with patch.object(api_facturae.requests, 'request', side_effect=requests.exceptions.ConnectionError('down')):
            with self.assertRaisesRegex(UserError, 'Error Obteniendo el Token'):
                api_facturae.get_token_hacienda(self.invoice, 'api-prod')
