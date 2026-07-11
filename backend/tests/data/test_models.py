from datetime import datetime, timezone
from app.data.models import OptionContract, OptionQuote, StockQuote


def test_normalized_models_retain_provider_independent_fields() -> None:
    timestamp = datetime.now(timezone.utc)
    contract = OptionContract("NVDA", timestamp, 120.0, "C", "contract-1")
    quote = OptionQuote("contract-1", "NVDA", timestamp, 120.0, "C", 2.0, 2.2, 2.1, 100, 50, 0.45)
    stock = StockQuote("NVDA", timestamp, 119.5, 119.4, 119.6, 2000)
    assert contract.option_type == quote.option_type == "C"
    assert quote.contract_id == contract.contract_id
    assert stock.price == 119.5
