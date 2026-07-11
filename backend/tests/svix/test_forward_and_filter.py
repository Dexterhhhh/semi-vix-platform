from datetime import timedelta

import pytest

from app.svix.exceptions import InsufficientOptionData
from app.svix.forward import calculate_forward, select_k0
from app.svix.option_filter import filter_otm_options
from tests.svix.conftest import VALUATION_TIME, make_chain


def test_put_call_parity_forward_and_k0_selection() -> None:
    chain = make_chain("NVDA", VALUATION_TIME + timedelta(days=30))
    forward = calculate_forward(chain, 30 / 365)
    assert forward.reference_strike == 100.0
    assert forward.forward_price == pytest.approx(102.0)
    k0 = select_k0((quote.strike for quote in chain), forward.forward_price)
    assert k0.strike == 100.0
    assert k0.used_nearest_fallback is False


def test_otm_filter_uses_puts_calls_and_k0_average() -> None:
    expiry = VALUATION_TIME + timedelta(days=30)
    chain = make_chain("NVDA", expiry)
    forward = calculate_forward(chain, 30 / 365)
    filtered = filter_otm_options("NVDA", expiry, chain, select_k0((quote.strike for quote in chain), forward.forward_price), forward)
    assert [option.option_type for option in filtered.options] == ["P", "K0", "C"]
    assert [option.delta_k for option in filtered.options] == [10.0, 10.0, 10.0]


def test_filter_rejects_missing_k0_pair() -> None:
    chain = [quote for quote in make_chain("NVDA", VALUATION_TIME + timedelta(days=30)) if not (quote.strike == 100 and quote.option_type == "P")]
    forward = calculate_forward(chain, 30 / 365)
    with pytest.raises(InsufficientOptionData):
        filter_otm_options("NVDA", VALUATION_TIME + timedelta(days=30), chain, select_k0((quote.strike for quote in chain), forward.forward_price), forward)
