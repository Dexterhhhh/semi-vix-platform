from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.api.health import router as health_router
from app.api.provider import router as provider_router
from app.auth.password import hash_password
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.database.database import SessionLocal
from app.database.models import AdminAccount, AdminSecurity


def ensure_initial_admin() -> None:
    """Create the sole administrator only when the database is empty."""
    settings = get_settings()
    database: Session = SessionLocal()
    try:
        if database.query(AdminAccount).first() is None:
            admin = AdminAccount(id=1, username=settings.svix_admin_username, password_hash=hash_password(settings.svix_admin_password.get_secret_value()))
            database.add(admin)
            database.flush()
            database.add(AdminSecurity(admin_id=admin.id))
            database.commit()
    finally:
        database.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_initial_admin()
    yield


app = FastAPI(title="Semi-VIX Platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().allowed_origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(provider_router)
