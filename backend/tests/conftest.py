import base64
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:////tmp/semi_vix_phase1_tests.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SECRET_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"a" * 32).decode()
os.environ["SVIX_ADMIN_USERNAME"] = "admin"
os.environ["SVIX_ADMIN_PASSWORD"] = "test-password"
os.environ["COOKIE_SECURE"] = "false"
