"""Configuração do gunicorn, lida de variáveis de ambiente."""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 4)))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = 100

# Logs no stdout/stderr (o Easypanel coleta).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# O proxy do Easypanel (Traefik) fica na frente; confiar no X-Forwarded-*.
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "*")

# Socket de controle do gunicorn (>= 25) não é usado e o $HOME do container não é
# gravável pelo usuário não root.
control_socket_disable = True
