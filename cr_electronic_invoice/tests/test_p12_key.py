import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import api_facturae


@tagged('post_install', '-at_install')
class TestP12Key(TransactionCase):
    """A PIN that does not open the company's .p12 gives a readable error, not a traceback."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Llave de prueba')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cls.not_after = now + datetime.timedelta(days=365)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now).not_valid_after(cls.not_after)
                .sign(key, hashes.SHA256()))
        cls.p12 = base64.b64encode(pkcs12.serialize_key_and_certificates(
            b'prueba', key, cert, None, serialization.BestAvailableEncryption(b'1234')))

    def test_right_pin(self):
        expiration = api_facturae.p12_expiration_date(self.p12, '1234')
        self.assertEqual(expiration.date(), self.not_after.date())

    def test_wrong_pin_is_a_user_error(self):
        for pin in ('9999', ''):
            with self.assertRaisesRegex(UserError, 'el PIN no corresponde'):
                api_facturae.p12_expiration_date(self.p12, pin)

    def test_not_a_key_file_is_a_user_error(self):
        with self.assertRaisesRegex(UserError, 'el PIN no corresponde'):
            api_facturae.p12_expiration_date(base64.b64encode(b'no es una llave'), '1234')

    def test_signing_with_a_wrong_pin_is_a_user_error(self):
        with self.assertRaisesRegex(UserError, 'el PIN no corresponde'):
            api_facturae.sign_xml(self.p12, '9999', '<FacturaElectronica/>')
