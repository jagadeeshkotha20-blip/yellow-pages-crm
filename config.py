import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

_DEV_SECRET_FALLBACK = "yellow-pages-crm-dev-secret-CHANGE-ME-IN-PRODUCTION"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_FALLBACK)
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "crm.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB max upload
    ALLOWED_EXCEL_EXTENSIONS = {"xlsx", "xls"}

    LEADS_PER_PAGE = 25
    EMPLOYEES_PER_PAGE = 25

    # --- Session / cookie security -----------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only force HTTPS-only cookies when explicitly running behind TLS —
    # set FORCE_HTTPS=1 in production (.env) once you have a real certificate.
    SESSION_COOKIE_SECURE = os.environ.get("FORCE_HTTPS", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # --- Login brute-force protection ----------------------------------
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCKOUT_MINUTES = 15

    # --- CSRF ------------------------------------------------------------
    WTF_CSRF_TIME_LIMIT = None  # tokens don't expire mid-session


class ProductionConfig(Config):
    FLASK_ENV = "production"


def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return ProductionConfig if env == "production" else Config


def assert_production_ready(config_obj):
    """Called from the app factory — fails fast instead of running insecurely."""
    if getattr(config_obj, "FLASK_ENV", "development") == "production":
        if config_obj.SECRET_KEY == _DEV_SECRET_FALLBACK:
            raise RuntimeError(
                "Refusing to start in production with the default SECRET_KEY. "
                "Set SECRET_KEY in your environment/.env file."
            )
