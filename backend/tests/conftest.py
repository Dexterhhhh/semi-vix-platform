import base64
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/semi_vix_phase1_tests.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SECRET_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"a" * 32).decode())
os.environ.setdefault("SVIX_ADMIN_USERNAME", "admin")
os.environ.setdefault("SVIX_ADMIN_PASSWORD", "test-password")
os.environ.setdefault("COOKIE_SECURE", "false")
