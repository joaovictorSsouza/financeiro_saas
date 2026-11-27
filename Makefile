.DEFAULT_GOAL := help
MANAGE := uv run python manage.py

.PHONY: help setup up up-api down run test lint format migrate makemigrations superuser convite shell

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Instala dependências, cria .env, sobe o Postgres, migra e cria a tabela de cache
	uv sync
	@test -f .env || (cp .env.example .env && echo ".env criado a partir do .env.example")
	uv run pre-commit install
	docker compose up -d --wait postgres
	$(MANAGE) migrate
	$(MANAGE) createcachetable

up: ## Sobe o Postgres local
	docker compose up -d --wait postgres

up-api: ## Sobe Postgres + a API com a imagem de produção (Docker) em http://localhost:8000
	docker compose --profile api up -d --build --wait

down: ## Para os containers
	docker compose --profile api down

run: ## Roda a API em modo desenvolvimento (http://localhost:8000)
	$(MANAGE) runserver 0.0.0.0:8000

test: ## Roda os testes
	uv run pytest

lint: ## Verifica lint e formatação
	uv run ruff check .
	uv run ruff format --check .

format: ## Corrige lint e formata o código
	uv run ruff check --fix .
	uv run ruff format .

migrate: ## Aplica as migrations
	$(MANAGE) migrate

makemigrations: ## Gera novas migrations
	$(MANAGE) makemigrations

superuser: ## Cria um superusuário
	$(MANAGE) createsuperuser

convite: ## Gera um convite (ex.: make convite ARGS="--email fulano@x.com --dias 7")
	$(MANAGE) criar_convite $(ARGS)

shell: ## Abre o shell do Django
	$(MANAGE) shell
