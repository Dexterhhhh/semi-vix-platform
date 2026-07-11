from datetime import datetime, timedelta, timezone

import pytest
from cryptography.exceptions import InvalidTag

from app.data import credentials
from app.data.credentials import decrypt_credential, encrypt_credential
from app.data.models import OptionQuote, StockQuote
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository
from app.database.database import Base, SessionLocal, engine
from app.database.models import OptionSnapshot, ProviderCredential, StockSnapshot


def test_credentials_use_authenticated_non_deterministic_encryption() -> None:
    first = encrypt_credential("private-key")
    second = encrypt_credential("private-key")
    assert first != "private-key"
    assert first != second
    assert decrypt_credential(first) == "private-key"


def test_tampered_or_wrong_key_credentials_fail_to_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    encrypted = encrypt_credential("private-key")
    tampered = encrypted[:-2] + ("AA" if encrypted[-2:] != "AA" else "BB")
    with pytest.raises((InvalidTag, ValueError)):
        decrypt_credential(tampered)
    monkeypatch.setattr(credentials, "_key", lambda: b"z" * 32)
    with pytest.raises(InvalidTag):
        decrypt_credential(encrypted)


def test_normalized_quotes_persist_and_can_be_retrieved() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        timestamp = datetime.now(timezone.utc)
        credential = ProviderCredential(provider="IBKR", api_key_encrypted=encrypt_credential("key"), enabled=True)
        database.add(credential)
        quote_repository = QuoteRepository(database)
        option_repository = OptionRepository(database)
        stock = StockQuote(symbol="NVDA", timestamp=timestamp, price=100.0, bid=99.0, ask=101.0, volume=7, provider="IBKR")
        option = OptionQuote(contract_id="IBKR:nvda-c", symbol="NVDA", expiry=timestamp, strike=100.0, option_type="C", timestamp=timestamp, bid=3.0, ask=3.2, last=3.1, volume=7, open_interest=9, implied_volatility=0.4, provider="IBKR")
        quote_repository.save(stock)
        option_repository.save_many([option])
        database.commit()
        assert database.query(ProviderCredential).one().api_key_encrypted != "key"
        assert quote_repository.latest("NVDA", "IBKR").price == 100.0
        assert option_repository.latest_chain("NVDA", "IBKR")[0].contract_id == "IBKR:nvda-c"
        assert option_repository.available_expirations("NVDA", "IBKR") == [timestamp]
        assert database.query(StockSnapshot).count() == 1
        assert database.query(OptionSnapshot).one().implied_volatility == 0.4
    finally:
        database.close()


def test_snapshot_rollback_and_provider_separation() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        timestamp = datetime.now(timezone.utc)
        QuoteRepository(database).save(StockQuote(symbol="NVDA", timestamp=timestamp, price=1.0, provider="IBKR"))
        database.rollback()
        assert database.query(StockSnapshot).count() == 0
        QuoteRepository(database).save_many([
            StockQuote(symbol="NVDA", timestamp=timestamp, price=1.0, provider="IBKR"),
            StockQuote(symbol="NVDA", timestamp=timestamp + timedelta(seconds=1), price=2.0, provider="FUTU"),
        ])
        database.commit()
        assert QuoteRepository(database).latest("NVDA", "IBKR").provider == "IBKR"
        assert QuoteRepository(database).latest("NVDA", "FUTU").provider == "FUTU"
    finally:
        database.close()
