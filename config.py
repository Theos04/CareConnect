import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-careconnect-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Connection pool (applies to PostgreSQL / MySQL via SQLAlchemy) ──────
    # pool_size:    persistent connections kept open
    # max_overflow: extra connections allowed above pool_size under load
    # pool_timeout: seconds to wait for a connection before raising
    # pool_recycle: recycle connections after N seconds (avoids stale TCP)
    # pool_pre_ping: issue a lightweight SELECT 1 before each checkout
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size':     int(os.environ.get('DB_POOL_SIZE',    '10')),
        'max_overflow':  int(os.environ.get('DB_MAX_OVERFLOW', '20')),
        'pool_timeout':  int(os.environ.get('DB_POOL_TIMEOUT', '30')),
        'pool_recycle':  int(os.environ.get('DB_POOL_RECYCLE', '1800')),
        'pool_pre_ping': True,
    }

    # ── Read replica ─────────────────────────────────────────────────────────
    # Set REPLICA_DATABASE_URL in env to route SELECT queries to a read replica.
    # Consumed by app.py's _get_replica_session() helper.
    REPLICA_DATABASE_URL = os.environ.get('REPLICA_DATABASE_URL')

    # ── Session & Cookie Security ────────────────────────────────────────────
    SESSION_COOKIE_SECURE   = False   # True in production (HTTPS only)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # ── OAuth ────────────────────────────────────────────────────────────────
    GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_DISCOVERY_URL = 'https://accounts.google.com/.well-known/openid-configuration'


class DevelopmentConfig(Config):
    DEBUG = True
    # SQLite for local dev — pool options are silently ignored by SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    # Smaller pool for dev to avoid resource waste
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'pool_size':    2,
        'max_overflow': 5,
    }


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    # Require an explicit DATABASE_URL in production (fail fast if missing)
    _db_url = os.environ.get('DATABASE_URL', '')
    # Heroku / Render ship postgres:// — SQLAlchemy 1.4+ needs postgresql://
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url or None


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}   # no pooling for in-memory


config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
    'default':     DevelopmentConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development').lower()
    return config_map.get(env, config_map['default'])
