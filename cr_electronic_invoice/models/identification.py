"""Costa Rica identification numbers in electronic documents.

Registro Nacional, "Cambio de formato de la cédula jurídica": once the six-digit consecutive
reaches 999999, new cédulas jurídicas get an alphanumeric consecutive of the same length
(3-101-A00001); existing numeric ones do not change. Hacienda accepts them since the Anexos y
Estructuras v4.4 update of 22/04/2026, and the clave becomes alphanumeric too
([a-zA-Z0-9]{50} in the XSD), since it embeds the issuer's identification.
"""
import re

LEGAL_ID_CODE = '02'
# 10 characters: the first 4 stay digits, the 6-character consecutive may hold letters.
_LEGAL_ID = re.compile(r'\d{4}[A-Z0-9]{6}')


def clean_identification(number, id_code=False):
    """The identification as Hacienda expects it: no dashes, dots or spaces.

    A cédula jurídica keeps its letters, upper case. When the type is unknown, letters are
    kept only if the number has the cédula jurídica shape (so a foreign tax ID such as
    ESB12345678 is still reduced to its digits, as before). Every other type keeps only
    its digits, as before.
    """
    if not number:
        return ''
    alphanumeric = re.sub(r'[^0-9A-Za-z]', '', number).upper()
    if id_code == LEGAL_ID_CODE or (not id_code and is_legal_id(alphanumeric)):
        return alphanumeric
    return re.sub(r'[^0-9]', '', number)


def is_legal_id(number):
    return bool(_LEGAL_ID.fullmatch(number or ''))


def clean_clave(clave):
    return re.sub(r'[^0-9A-Za-z]', '', clave or '')
