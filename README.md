# financeiro_saas — API de controle financeiro pessoal

API em Django + Django REST Framework de um app de finanças pessoais. O frontend é um PWA separado (outro repositório). Cada usuário vê **somente os próprios dados**, e o cadastro é **apenas por convite**.

- **Stack:** Python 3.12, Django 5.2 LTS, DRF, JWT (simplejwt), PostgreSQL 17, uv, pytest, ruff.
- **Produção:** Easypanel (Dockerfile) + Postgres do Supabase (Session pooler).

---

## Rodando no WSL do zero

Pré-requisitos: Windows com WSL2 (Ubuntu) e Docker Desktop com a integração WSL ligada.

> Trabalhe sempre dentro do filesystem do Linux (`~/projetos/...`), nunca em `/mnt/c/...`. Em `/mnt/c` tudo fica muito mais lento e os file watchers não funcionam.

```bash
# 1. Ferramentas básicas
sudo apt update && sudo apt install -y git make curl

# 2. uv (gerenciador de Python e de dependências)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # ou abra um terminal novo

# 3. Código
mkdir -p ~/projetos && cd ~/projetos
git clone https://github.com/joaovictorSsouza/financeiro_saas.git
cd financeiro_saas

# 4. Tudo de uma vez: instala dependências (e o Python 3.12, via uv), cria o .env,
#    instala o pre-commit, sobe o Postgres, aplica migrations e cria a tabela de cache
make setup

# 5. Edite o .env e troque DJANGO_SECRET_KEY por uma chave aleatória:
uv run python -c "import secrets; print(secrets.token_urlsafe(50))"

# 6. Crie seu usuário admin e rode a API
make superuser
make run          # http://localhost:8000
```

Endereços úteis em desenvolvimento:

| URL | O que é |
|---|---|
| http://localhost:8000/api/health/ | Health check (testa a conexão com o banco) |
| http://localhost:8000/api/docs/ | Swagger UI (aberto em DEBUG; fora dele exige login) |
| http://localhost:8000/admin/ | Admin do Django (usuários e convites) |

### Comandos do Makefile

| Comando | O que faz |
|---|---|
| `make setup` | `uv sync`, cria o `.env`, instala o pre-commit, sobe o Postgres, roda `migrate` e `createcachetable` |
| `make up` / `make down` | Sobe e para o Postgres local |
| `make up-api` | Sobe Postgres + API usando a **imagem de produção** (gunicorn) em http://localhost:8000 |
| `make run` | `runserver` em http://localhost:8000 |
| `make test` | Roda o pytest |
| `make lint` / `make format` | Roda o ruff (verificar / corrigir) |
| `make migrate` / `make makemigrations` | Aplica / gera migrations |
| `make superuser` | Cria um superusuário |
| `make convite ARGS="..."` | Gera um convite (veja abaixo) |
| `make shell` | Abre o shell do Django |

No modo `make up-api` a imagem roda com os settings de produção. Como os cookies são `Secure`, o login no `/admin/` não funciona via `http://localhost`; a API com JWT funciona normalmente.

---

## Convites (cadastro)

O registro (`POST /api/v1/auth/registro/`) só funciona com um código de convite válido, não expirado e ainda não usado. Se o convite tiver e-mail, só esse e-mail pode usá-lo.

**Pelo terminal:**

```bash
make convite                                        # qualquer e-mail, válido por 7 dias
make convite ARGS="--email amigo@exemplo.com --dias 3 --criado-por voce@exemplo.com"
# ou: uv run python manage.py criar_convite --help
```

**Pelo admin:** em `/admin/` → Contas → Convites → Adicionar. O código é gerado automaticamente.

**Em produção (Easypanel):** abra o console do serviço e rode `python manage.py criar_convite --email ...`.

---

## API (v1)

Todas as rotas de negócio ficam em `/api/v1/`. Para autenticar, envie `Authorization: Bearer <access>`.

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/auth/registro/` | `{codigo, email, senha, nome?}` → `{usuario, access, refresh}` |
| POST | `/api/v1/auth/login/` | `{email, senha}` → `{access, refresh}` |
| POST | `/api/v1/auth/refresh/` | `{refresh}` → `{access, refresh}` (rotação: o refresh antigo deixa de valer) |
| POST | `/api/v1/auth/logout/` | `{refresh}` → 204 (refresh vai para a blacklist) |
| GET/PATCH | `/api/v1/me/` | Dados do usuário logado (só `nome` é editável) |
| GET | `/api/health/` | Status da API e do banco (sem autenticação) |

O login e o registro têm limite de requisições por IP (padrão: 5/min e 10/hora). Os contadores ficam no cache do banco (`DatabaseCache`), compartilhado entre os workers.

---

## Variáveis de ambiente

Veja o [`.env.example`](.env.example), que documenta todas. As principais:

| Variável | Obrigatória | Exemplo / padrão | Para quê |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | **sim** | chave aleatória longa | Assinatura de sessões e JWT |
| `DATABASE_URL` | **sim** | veja abaixo | Conexão com o Postgres |
| `DJANGO_SETTINGS_MODULE` | não | `config.settings.prod` (padrão na imagem Docker) | `dev`, `prod` ou `test` |
| `DJANGO_ALLOWED_HOSTS` | **sim em prod** | `api.seudominio.com.br` | Hosts aceitos |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | sim em prod | `https://api.seudominio.com.br` | Necessário para o login no `/admin/` |
| `CORS_ALLOWED_ORIGINS` | sim em prod | `https://app.seudominio.com.br` | Origem do PWA |
| `DB_CONN_MAX_AGE` | não | `60` | Reuso de conexões (segundos) |
| `DB_DISABLE_SERVER_SIDE_CURSORS` | não | `False` | `True` só no Transaction pooler |
| `JWT_ACCESS_MINUTOS` / `JWT_REFRESH_DIAS` | não | `15` / `7` | Validade dos tokens |
| `JWT_SIGNING_KEY` | não | padrão: `DJANGO_SECRET_KEY` | Chave própria para os JWT |
| `THROTTLE_LOGIN` / `THROTTLE_REGISTRO` | não | `5/min` / `10/hour` | Limites por IP |
| `DRF_NUM_PROXIES` | não | `1` em prod | Proxies na frente (para pegar o IP real) |
| `GUNICORN_WORKERS` | não | `3` | Número de workers |
| `RODAR_MIGRATIONS` | não | `true` | `migrate` + `createcachetable` ao subir |
| `DJANGO_SECURE_HSTS_SECONDS` | não | `2592000` (30 dias) | HSTS |
| `DJANGO_LOG_LEVEL` | não | `INFO` | Nível de log (JSON no stdout em prod) |

### `DATABASE_URL` do Supabase

Use o **Session pooler** (porta **5432**), sempre com `sslmode=require`. Ele fica em Supabase → seu projeto → **Connect** → *Session pooler*:

```
postgres://postgres.<ref-do-projeto>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require
```

Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`...), codifique-os em URL (ex.: `@` → `%40`).

> **Transaction pooler (porta 6543):** se um dia for usado, é obrigatório definir `DB_DISABLE_SERVER_SIDE_CURSORS=True` e `DB_CONN_MAX_AGE=0`.

Usamos o Supabase **apenas como Postgres**: nada de Supabase Auth, Storage ou supabase-py.

---

## Deploy no Easypanel

A imagem é construída a partir do `Dockerfile` (multi-stage, roda com usuário não root, faz `collectstatic` no build e escuta na porta 8000). Ao subir, o entrypoint roda `migrate` e `createcachetable`; para desligar, use `RODAR_MIGRATIONS=false`.

1. **Criar o serviço:** no projeto do Easypanel, *+ Service* → **App**.
2. **Fonte:** *Source* → **GitHub** → repositório `joaovictorSsouza/financeiro_saas`, branch `main`.
3. **Build:** *Build* → **Dockerfile**, com caminho `Dockerfile`.
4. **Variáveis:** em *Environment*, cole as variáveis (veja o checklist abaixo).
5. **Domínio:** em *Domains*, adicione `api.seudominio.com.br` com HTTPS ligado, apontando para a **porta 8000** do container.
6. **Deploy:** clique em *Deploy* e acompanhe os logs. Você deve ver `Aplicando migrations...` e depois o gunicorn em `Listening at: http://0.0.0.0:8000`.
7. **Teste:** abra `https://api.seudominio.com.br/api/health/`. A resposta esperada é `{"status": "ok", "banco": "ok"}`.
8. **Superusuário:** no *Console* do serviço, rode `python manage.py createsuperuser`.
9. **Primeiro convite:** no mesmo console, rode `python manage.py criar_convite --email voce@exemplo.com`.

Checklist de variáveis para o Easypanel:

```env
DJANGO_SECRET_KEY=<gere uma chave aleatória longa>
DATABASE_URL=postgres://postgres.<ref>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require
DJANGO_ALLOWED_HOSTS=api.seudominio.com.br
DJANGO_CSRF_TRUSTED_ORIGINS=https://api.seudominio.com.br
CORS_ALLOWED_ORIGINS=https://app.seudominio.com.br
GUNICORN_WORKERS=3
DB_CONN_MAX_AGE=60
```

O restante tem padrão seguro em `config/settings/prod.py`.

O Swagger em produção (`/api/docs/`) exige login: entre primeiro em `/admin/` e depois abra `/api/docs/`.

---

## Testes e qualidade

```bash
make test      # pytest (precisa do Postgres: make up)
make lint      # ruff check + ruff format --check
uv run pytest --cov   # com cobertura
```

O CI (GitHub Actions) roda em todo push e PR: ruff, pytest contra Postgres 17, checagem de migrations pendentes e o build da imagem Docker.

---

## Estrutura

```
apps/
  core/       ModeloBase (UUID + timestamps), health check, permissões
  accounts/   Usuario (login por e-mail), Convite, registro, JWT, /me
config/
  settings/   base.py, dev.py, prod.py, test.py
  api_v1.py   Rotas /api/v1/
  gunicorn.conf.py
docker/entrypoint.sh
```
