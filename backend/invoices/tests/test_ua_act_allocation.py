from decimal import Decimal as D

import pytest

from invoices.billing.money import IssuedAllocation, SourceLineBudget, allocate_act_line


@pytest.mark.parametrize(
    "net,vat", [("12000.00", "2400.00"), (".07", ".01"), ("0", "0")]
)
def test_twelve_partial_allocations_exhaust_exact_budgets(net, vat):
    source = SourceLineBudget(D(1), D(net), D(vat))
    issued = IssuedAllocation()
    for i in range(12):
        q = D(".08333333") if i < 11 else source.quantity - issued.quantity
        part = allocate_act_line(source, q, issued)
        assert 0 <= part.net <= source.net - issued.net
        assert 0 <= part.vat <= source.vat - issued.vat
        issued = IssuedAllocation(
            issued.quantity + part.quantity,
            issued.net + part.net,
            issued.vat + part.vat,
        )
    assert (issued.quantity, issued.net, issued.vat) == (D(1), D(net), D(vat))


def test_cancelled_allocation_can_be_reissued_without_overrun():
    source = SourceLineBudget(D(1), D(".07"), D(".01"))
    first = allocate_act_line(source, D(".5"), IssuedAllocation())
    second = allocate_act_line(
        source, D(".5"), IssuedAllocation(first.quantity, first.net, first.vat)
    )
    replacement = allocate_act_line(
        source, D(".5"), IssuedAllocation(second.quantity, second.net, second.vat)
    )
    assert replacement.net + second.net == D(".07")
    assert replacement.vat + second.vat == D(".01")


@pytest.mark.parametrize("q", ["0", "-1", "1.1", "0.000000001", "NaN"])
def test_invalid_quantity_cannot_close_a_line(q):
    with pytest.raises(ValueError):
        allocate_act_line(SourceLineBudget(D(1), D(10), D(2)), D(q), IssuedAllocation())
