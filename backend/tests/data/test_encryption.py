from datetime import datetime, timezone
from app.data.credentials import decrypt_credential, encrypt_credential
from app.data.models import OptionQuote, StockQuote
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository
from app.database.database import Base, SessionLocal, engine
from app.database.models import OptionSnapshot, ProviderCredential, StockSnapshot


def test_credentials_use_authenticated_encryption() -> None:
    encrypted = encrypt_credential("private-key")
    assert encrypted != "private-key"
    assert decrypt_credential(encrypted) == "private-key"


def test_normalized_quotes_persist_to_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        timestamp = datetime.now(timezone.utc)
        credential = ProviderCredential(provider="IBKR", api_key_encrypted=encrypt_credential("key"), enabled=True)
        database.add(credential)
        QuoteRepository(database).save(StockQuote("NVDA", timestamp, 100.0, 99.0, 101.0, 7))
        OptionRepository(database).save("IBKR", OptionQuote("nvda-c", "NVDA", timestamp, 100.0, "C", 3.0, 3.2, 3.1, 7, 9, 0.4))
        database.commit()
        assert database.query(ProviderCredential).one().api_key_encrypted != "key"
        assert database.query(StockSnapshot).count() == 1
        assert database.query(OptionSnapshot).one().implied_volatility == 0.4
    finally:
        database.close()
