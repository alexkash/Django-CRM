"""Shared format checks for Ukrainian issuer and customer particulars."""

import re

from rest_framework.exceptions import ValidationError


def validate_registration_code(value):
    if value and not re.fullmatch(r"[0-9]{8}|[0-9]{10}", value):
        raise ValidationError("Вкажіть код із 8 або 10 цифр.")
    return value


def validate_ua_iban(value):
    if not value:
        return value
    value = value.replace(" ", "").upper()
    if not re.fullmatch(r"UA[0-9]{27}", value):
        raise ValidationError("IBAN має містити UA та 27 цифр.")
    if int(value[4:] + "3010" + value[2:4]) % 97 != 1:
        raise ValidationError("Некоректна контрольна сума IBAN.")
    return value


def validate_mfo(value):
    if value and not re.fullmatch(r"[0-9]{6}", value):
        raise ValidationError("МФО має містити 6 цифр.")
    return value


class BillingParticularsValidationMixin:
    """Keep blank legacy profiles valid and validate supplied particulars alike."""

    validate_registration_code = staticmethod(validate_registration_code)
    validate_iban = staticmethod(validate_ua_iban)
    validate_mfo = staticmethod(validate_mfo)
