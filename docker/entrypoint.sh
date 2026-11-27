#!/bin/sh
# Prepara o banco antes de subir a aplicação.
# Desligue com RODAR_MIGRATIONS=false (ex.: várias réplicas, migração feita à parte).
set -e

if [ "${RODAR_MIGRATIONS:-true}" = "true" ]; then
    echo "Aplicando migrations..."
    python manage.py migrate --noinput
    echo "Garantindo a tabela de cache (throttling)..."
    python manage.py createcachetable
fi

exec "$@"
