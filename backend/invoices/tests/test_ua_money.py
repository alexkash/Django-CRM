from decimal import Decimal as D

import pytest


def test_ua_tax_is_per_line_and_never_added_twice():
    from invoices.billing.money import LineInput, calculate_ua_totals

    result = calculate_ua_totals(
        [LineInput(D(1), D("0.03")), LineInput(D(1), D("0.03"))], "PAYER", D(20)
    )
    assert (result.subtotal, result.tax_amount, result.total_amount) == (
        D(".06"),
        D(".02"),
        D(".08"),
    )
    other = calculate_ua_totals([LineInput(D(1), D("10000"))], "NON_PAYER", D(0))
    assert (other.subtotal, other.tax_amount, other.total_amount) == (
        D(10000),
        D(0),
        D(10000),
    )


@pytest.mark.parametrize(
    "q,price",
    [
        ("0", "1"),
        ("-1", "1"),
        ("1", "-1"),
        ("1", "NaN"),
        ("1", "Infinity"),
        ("1", "9999999999.99"),
    ],
)
def test_invalid_or_overflowing_ua_amount_is_rejected(q, price):
    from invoices.billing.money import LineInput, calculate_ua_totals

    with pytest.raises(ValueError):
        calculate_ua_totals([LineInput(D(q), D(price))], "PAYER", D(20))


@pytest.mark.parametrize(
    "value,want",
    [
        ("0", "Нуль гривень 00 копійок"),
        ("1.01", "Одна гривня 01 копійка"),
        ("2.02", "Дві гривні 02 копійки"),
        ("5.05", "П'ять гривень 05 копійок"),
        ("11.11", "Одинадцять гривень 11 копійок"),
        ("21.21", "Двадцять одна гривня 21 копійка"),
        ("1001", "Одна тисяча одна гривня 00 копійок"),
        ("1011", "Одна тисяча одинадцять гривень 00 копійок"),
    ],
)
def test_ukrainian_money_words(value, want):
    from invoices.billing.formatting import amount_in_words_uk

    assert amount_in_words_uk(D(value)) == want
