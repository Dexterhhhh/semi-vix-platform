"""Loopback-only IBKR/Futu SDK bridge; Go owns orchestration and migrations."""

import asyncio
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from app.api.provider_bridge import router
from app.database.database import SessionLocal
from app.database.models import ProviderCredential
from app.data.vendor_factory import create_vendor_provider
from app.services.market_collector import collect_option_snapshot

app = FastAPI(title="Internal vendor SDK bridge", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return await call_next(request)


app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


class CollectionRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100)


@app.post("/internal/providers/collect")
def collect(request: CollectionRequest):
    database = SessionLocal()
    try:
        credential = database.query(ProviderCredential).filter_by(enabled=True).first()
        if credential is None or credential.provider not in {"IBKR", "FUTU"}:
            raise HTTPException(409, "An active IBKR or FUTU configuration is required")
        provider = create_vendor_provider(credential.provider, host=credential.host,
                                          port=credential.port, client_id=credential.client_id)
        return asyncio.run(collect_option_snapshot(request.symbols, database, provider=provider))
    finally:
        database.close()
