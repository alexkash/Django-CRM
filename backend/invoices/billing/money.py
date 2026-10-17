"""Exact UAH arithmetic shared by invoices and partial service acts."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999.99")
ZERO = Decimal(0)


def rounded(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def money_bound(value):
    if not value.is_finite() or not ZERO <= value <= MAX_MONEY:
        raise ValueError("Сума виходить за допустимі межі.")
    return value


@dataclass(frozen=True)
class LineInput:
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class LineTotals:
    net: Decimal
    vat: Decimal
    gross: Decimal


@dataclass(frozen=True)
class UATotals:
    lines: list[LineTotals]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True)
class SourceLineBudget:
    quantity: Decimal
    net: Decimal
    vat: Decimal


@dataclass(frozen=True)
class IssuedAllocation:
    quantity: Decimal = ZERO
    net: Decimal = ZERO
    vat: Decimal = ZERO


@dataclass(frozen=True)
class ActAllocation:
    quantity: Decimal
    net: Decimal
    vat: Decimal

    @property
    def total(self):
        return self.net + self.vat


def calculate_ua_totals(lines, vat_status, vat_rate):
    if (
        vat_status not in ("PAYER", "NON_PAYER")
        or not vat_rate.is_finite()
        or not ZERO <= vat_rate <= 100
    ):
        raise ValueError("Некоректна ставка ПДВ.")
    if vat_status == "NON_PAYER" and vat_rate != ZERO:
        raise ValueError("Неплатник ПДВ має нульову суму податку.")
    amounts = []
    try:
        for line in lines:
            if not line.quantity.is_finite() or line.quantity <= 0:
                raise ValueError("Кількість має бути додатною.")
            money_bound(line.unit_price)
            net = money_bound(rounded(line.quantity * line.unit_price))
            vat = money_bound(rounded(net * vat_rate / 100))
            amounts.append(LineTotals(net, vat, money_bound(net + vat)))
        net = money_bound(sum((line.net for line in amounts), ZERO))
        vat = money_bound(sum((line.vat for line in amounts), ZERO))
        return UATotals(amounts, net, vat, money_bound(net + vat))
    except InvalidOperation as exc:
        raise ValueError("Некоректна сума.") from exc


def allocate_act_line(source, requested_quantity, issued):
    q = requested_quantity
    if not q.is_finite() or q <= 0 or q.as_tuple().exponent < -8:
        raise ValueError("Кількість: додатне число до 8 десяткових знаків.")
    rq, rn, rv = (
        source.quantity - issued.quantity,
        source.net - issued.net,
        source.vat - issued.vat,
    )
    if rq <= 0 or q > rq or rn < 0 or rv < 0:
        raise ValueError("Недостатній залишок позиції.")
    net, vat = (rn, rv) if q == rq else (rounded(rn * q / rq), rounded(rv * q / rq))
    return ActAllocation(q, money_bound(net), money_bound(vat))
