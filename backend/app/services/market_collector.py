"""Bounded, provider-injected collection of normalized market snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session

from app.data.factory import create_provider
from app.data.credentials import decrypt_credential
from app.data.provider import MarketDataProvider
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository
from app.data.universe import DEFAULT_SYMBOLS as DEFAULT_UNIVERSE
from app.database.models import ProviderCredential

logger = logging.getLogger(__name__)
DEFAULT_SYMBOLS = DEFAULT_UNIVERSE


@dataclass(frozen=True)
class CollectionError:
    symbol: str
    code: str
    message: str


@dataclass
class CollectionSummary:
    provider: str
    started_at: datetime
    symbols_requested: int
    finished_at: datetime | None = None
    symbols_succeeded: int = 0
    symbols_failed: int = 0
    stock_quotes_saved: int = 0
    option_quotes_saved: int = 0
    errors: list[CollectionError] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


async def _bounded(call, timeout_seconds: float):
    return await asyncio.wait_for(call, timeout=timeout_seconds)


async def collect_option_snapshot(symbols: Iterable[str], database: Session, provider: MarketDataProvider | None = None, request_timeout_seconds: float = 15.0, max_contracts_per_symbol: int = 120) -> dict[str, object]:
    """Collect sequentially (bounded concurrency of one) and commit successes.

    Provider SDKs are commonly stateful, so serial collection avoids exceeding
    broker request/subscription quotas.  Each symbol is isolated in a database
    savepoint: an unavailable SKHY chain cannot discard NVDA data already
    normalized and staged for commit.
    """

    requested = list(symbols)
    configured = database.query(ProviderCredential).filter_by(enabled=True).first()
    market_provider = provider or create_provider(
        configured.provider if configured else None,
        host=configured.host if configured else None,
        port=configured.port if configured else None,
        client_id=configured.client_id if configured else None,
        api_key=decrypt_credential(configured.api_key_encrypted) if configured and configured.api_key_encrypted else None,
        secret=decrypt_credential(configured.secret_encrypted) if configured and configured.secret_encrypted else None,
        data_feed=configured.data_feed if configured else None,
    )
    summary = CollectionSummary(provider=market_provider.provider_name, started_at=datetime.now(timezone.utc), symbols_requested=len(requested))
    stock_repository = QuoteRepository(database)
    option_repository = OptionRepository(database)
    try:
        await _bounded(market_provider.connect(), request_timeout_seconds)
        for symbol in requested:
            try:
                with database.begin_nested():
                    stock_quote = await _bounded(market_provider.get_stock_quote(symbol), request_timeout_seconds)
                    stock_repository.save(stock_quote)
                    summary.stock_quotes_saved += 1

                    contracts = await _bounded(market_provider.get_option_chain(symbol), request_timeout_seconds)
                    if not contracts:
                        summary.errors.append(CollectionError(symbol=symbol.upper(), code="OPTION_CHAIN_UNAVAILABLE", message="No eligible contracts returned"))
                        summary.symbols_failed += 1
                        continue

                    quotes = []
                    for contract in contracts[:max_contracts_per_symbol]:
                        try:
                            quotes.append(await _bounded(market_provider.get_option_quote(contract), request_timeout_seconds))
                        except asyncio.TimeoutError:
                            summary.errors.append(CollectionError(symbol=symbol.upper(), code="QUOTE_TIMEOUT", message="Option quote request timed out"))
                        except Exception as exc:
                            logger.warning("Option quote unavailable for %s: %s", symbol.upper(), exc)
                            summary.errors.append(CollectionError(symbol=symbol.upper(), code="OPTION_QUOTE_UNAVAILABLE", message="Option quote unavailable"))
                    option_repository.save_many(quotes)
                    summary.option_quotes_saved += len(quotes)
                    summary.symbols_succeeded += 1
            except asyncio.TimeoutError:
                summary.symbols_failed += 1
                summary.errors.append(CollectionError(symbol=symbol.upper(), code="REQUEST_TIMEOUT", message="Market-data request timed out"))
            except Exception as exc:
                summary.symbols_failed += 1
                logger.warning("Market-data collection unavailable for %s: %s", symbol.upper(), exc)
                summary.errors.append(CollectionError(symbol=symbol.upper(), code="COLLECTION_UNAVAILABLE", message="Market data unavailable"))
        database.commit()
    except Exception:
        database.rollback()
        logger.exception("Market-data collection setup failed")
        raise
    finally:
        summary.finished_at = datetime.now(timezone.utc)
        try:
            await _bounded(market_provider.disconnect(), request_timeout_seconds)
        except Exception:
            logger.warning("Market-data provider disconnect failed")
    return summary.to_dict()
