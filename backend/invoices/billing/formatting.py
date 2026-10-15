"""Ukrainian UAH words and document formatting, independent of host locale."""

from decimal import Decimal

from .money import money_bound, rounded

ONES = ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
FEMININE = ["", "одна", "дві"] + ONES[3:]
TEENS = [
    "десять",
    "одинадцять",
    "дванадцять",
    "тринадцять",
    "чотирнадцять",
    "п'ятнадцять",
    "шістнадцять",
    "сімнадцять",
    "вісімнадцять",
    "дев'ятнадцять",
]
TENS = [
    "",
    "",
    "двадцять",
    "тридцять",
    "сорок",
    "п'ятдесят",
    "шістдесят",
    "сімдесят",
    "вісімдесят",
    "дев'яносто",
]
HUNDREDS = [
    "",
    "сто",
    "двісті",
    "триста",
    "чотириста",
    "п'ятсот",
    "шістсот",
    "сімсот",
    "вісімсот",
    "дев'ятсот",
]


def ending(n, forms):
    if 11 <= n % 100 <= 14:
        return forms[2]
    return forms[0] if n % 10 == 1 else forms[1] if 2 <= n % 10 <= 4 else forms[2]


def triplet(n, feminine=False):
    words = [HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(TEENS[rest - 10])
    else:
        words.extend([TENS[rest // 10], (FEMININE if feminine else ONES)[rest % 10]])
    return " ".join(word for word in words if word)


def amount_in_words_uk(amount: Decimal) -> str:
    amount = rounded(money_bound(amount))
    whole = int(amount)
    coins = int((amount - whole) * 100)
    groups = [
        (1_000_000_000, ("мільярд", "мільярди", "мільярдів"), False),
        (1_000_000, ("мільйон", "мільйони", "мільйонів"), False),
        (1000, ("тисяча", "тисячі", "тисяч"), True),
    ]
    rest = whole
    words = []
    for scale, forms, female in groups:
        count, rest = divmod(rest, scale)
        if count:
            words.extend([triplet(count, female), ending(count, forms)])
    if rest:
        words.append(triplet(rest, True))
    if not words:
        words.append("нуль")
    words.extend(
        [
            ending(whole, ("гривня", "гривні", "гривень")),
            f"{coins:02d}",
            ending(coins, ("копійка", "копійки", "копійок")),
        ]
    )
    return " ".join(words).capitalize()
