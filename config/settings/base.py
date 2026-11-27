"""Settings comuns a todos os ambientes.

Toda configuração sensível ou que varia por ambiente vem de variáveis de ambiente
(django-environ). Em desenvolvimento, um arquivo `.env` na raiz é lido se existir.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
]
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Banco de dados -------------------------------------------------------------
# DATABASE_URL, ex.: postgres://usuario:senha@host:5432/banco?sslmode=require
#
# Supabase (Session pooler, porta 5432): funciona com conexões persistentes
# (CONN_MAX_AGE > 0) e server-side cursors normalmente.
#
# ATENÇÃO: se um dia usarmos o Transaction pooler (porta 6543), é obrigatório:
#   DB_DISABLE_SERVER_SIDE_CURSORS=True  e  DB_CONN_MAX_AGE=0
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env.bool(
    "DB_DISABLE_SERVER_SIDE_CURSORS", default=False
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.Usuario"

# --- Cache ----------------------------------------------------------------------
# DatabaseCache: compartilhado entre todos os workers do gunicorn (usado pelo
# throttling do DRF). A tabela é criada com `manage.py createcachetable`
# (entrypoint e `make setup`). Será trocado por Redis na fase da Pluggy.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# --- Django REST Framework -----------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Throttling por escopo (ScopedRateThrottle) nas views de login e registro.
    # O contador fica no cache "default" (DatabaseCache), compartilhado entre workers.
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", default="5/min"),
        "registro": env("THROTTLE_REGISTRO", default="10/hour"),
    },
    # Quantos proxies confiáveis existem na frente (para ler o IP real em X-Forwarded-For).
    # 0 = usa REMOTE_ADDR. Em produção (Easypanel/Traefik) o padrão é 1.
    "NUM_PROXIES": env.int("DRF_NUM_PROXIES", default=0),
}

# --- OpenAPI (drf-spectacular) --------------------------------------------------
# Swagger UI em /api/docs/: liberado em DEBUG ou para usuário logado (sessão do admin
# ou Bearer). Sem login, redireciona para /admin/login/.
SPECTACULAR_SETTINGS = {
    "TITLE": "Financeiro API",
    "DESCRIPTION": "API do app de controle financeiro pessoal.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "SERVE_PERMISSIONS": ["apps.core.permissions.AutenticadoOuDebug"],
}

# --- CORS -----------------------------------------------------------------------
# Origens do PWA, ex.: https://app.seudominio.com.br (lista separada por vírgulas).
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_CREDENTIALS = False  # JWT vai no header Authorization, não em cookie.

# --- JWT (simplejwt) ------------------------------------------------------------
# Access curto; refresh com rotação e blacklist (cada refresh só pode ser usado uma vez).
# Nesta fase o refresh vai no corpo da resposta (melhoria futura: cookie HttpOnly).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTOS", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DIAS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- Senhas ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internacionalização --------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Estáticos (admin) ----------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Logging --------------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simples": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simples"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
