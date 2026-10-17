"""Address formatting and Ukrainian money wording for built-in invoice forms."""

from decimal import Decimal


def format_document_address(source, prefix=""):
    """Keep every available address component, including the ISO country code."""
    parts = (
        str(getattr(source, f"{prefix}{field}", "") or "").strip()
        for field in ("address_line", "city", "state", "postcode", "country")
    )
    return ", ".join(part for part in parts if part)


_ONES = (
    "",
    "один",
    "два",
    "три",
    "чотири",
    "п’ять",
    "шість",
    "сім",
    "вісім",
    "дев’ять",
    "десять",
    "одинадцять",
    "дванадцять",
    "тринадцять",
    "чотирнадцять",
    "п’ятнадцять",
    "шістнадцять",
    "сімнадцять",
    "вісімнадцять",
    "дев’ятнадцять",
)
_TENS = (
    "",
    "",
    "двадцять",
    "тридцять",
    "сорок",
    "п’ятдесят",
    "шістдесят",
    "сімдесят",
    "вісімдесят",
    "дев’яносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двісті",
    "триста",
    "чотириста",
    "п’ятсот",
    "шістсот",
    "сімсот",
    "вісімсот",
    "дев’ятсот",
)


def _plural(number, forms):
    if 11 <= number % 100 <= 14:
        return forms[2]
    if number % 10 == 1:
        return forms[0]
    if 2 <= number % 10 <= 4:
        return forms[1]
    return forms[2]


def _triplet(number, feminine=False):
    words = [_HUNDREDS[number // 100]] if number >= 100 else []
    remainder = number % 100
    if remainder >= 20:
        words.append(_TENS[remainder // 10])
        remainder %= 10
    if remainder:
        word = _ONES[remainder]
        if feminine and remainder in (1, 2):
            word = "одна" if remainder == 1 else "дві"
        words.append(word)
    return words


def amount_in_words_uk(amount):
    """Spell a model-sized UAH amount, with two numeric kopeck digits."""
    amount = Decimal(amount).quantize(Decimal("0.01"))
    negative = amount < 0
    amount = abs(amount)
    hryvnias = int(amount)
    kopecks = int((amount - hryvnias) * 100)
    words = []
    remainder = hryvnias
    for divisor, forms, feminine in (
        (1_000_000_000, ("мільярд", "мільярди", "мільярдів"), False),
        (1_000_000, ("мільйон", "мільйони", "мільйонів"), False),
        (1_000, ("тисяча", "тисячі", "тисяч"), True),
    ):
        group, remainder = divmod(remainder, divisor)
        if group:
            words.extend(_triplet(group, feminine))
            words.append(_plural(group, forms))
    words.extend(_triplet(remainder, feminine=True))
    if not hryvnias:
        words.append("нуль")
    words.extend(
        (
            _plural(hryvnias, ("гривня", "гривні", "гривень")),
            f"{kopecks:02d}",
            _plural(kopecks, ("копійка", "копійки", "копійок")),
        )
    )
    if negative:
        words.insert(0, "мінус")
    return " ".join(words).capitalize()
