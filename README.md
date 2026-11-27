# financeiro_saas — API de controle financeiro pessoal

[![CI](https://github.com/joaovictorSsouza/financeiro_saas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/joaovictorSsouza/financeiro_saas/actions/workflows/ci.yml)

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
| http://localhost:8000/admin/ | Admin do Django (usuários, convites e todos os dados financeiros) |

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

No modo `make up-api` a imagem roda com os settings de produção, mas o serviço `api` do `docker-compose.yml` define `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE` e `DJANGO_CSRF_COOKIE_SECURE` como `False`. Assim tudo funciona em `http://localhost:8000`, inclusive o login no `/admin/`. Em produção essas três variáveis **não** devem ser definidas: o padrão é `True`.

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

### Domínio financeiro

**Todos os valores são inteiros em centavos** (`valor_centavos`, `saldo_centavos`...). Cada usuário só enxerga e só referencia os próprios dados: recurso de outro usuário dá 404, e uma FK de outro usuário no body dá 400. As listas são paginadas (`?page=`, `?page_size=` até 200) e respondem `{count, next, previous, results}`.

| Rota | Descrição |
|---|---|
| `/api/v1/categorias/` | CRUD. Até 2 níveis (pai > subcategoria). Filtros: `tipo`, `ativa`, `categoria_pai`, `raiz` |
| `/api/v1/contas/` | CRUD de contas (corrente, poupança, cartão, carteira, outro). Filtros: `tipo`, `ativa` |
| `/api/v1/transacoes/` | CRUD. Filtros: `mes=AAAA-MM`, `conta`, `categoria` (inclui subcategorias), `sem_categoria`, `tipo`, `ignorada`, `busca` (descrição ou valor: `45,90`) |
| `POST/DELETE /api/v1/transacoes/{id}/dividir/` | Divide em partes `{"itens": [{categoria, valor_centavos, descricao?}]}` (soma = valor) / desfaz |
| `/api/v1/regras/` | CRUD de regras de categoria (`contem`, `comeca_com`, `igual`; sem acentos e sem caixa) |
| `POST /api/v1/regras/aplicar/` | Reaplica as regras nas transações sem categoria manual |
| `/api/v1/recorrencias/` | CRUD de contas e receitas fixas (e parcelados com `total_parcelas`) |
| `GET /api/v1/ocorrencias/?mes=AAAA-MM` | Contas e receitas do mês (gera as que faltam). Filtros: `status` (`prevista`, `paga`, `atrasada`), `tipo` |
| `POST /api/v1/ocorrencias/{id}/marcar-paga/` | `{transacao?, paga_em?}` |
| `POST /api/v1/ocorrencias/{id}/desmarcar/` | Volta para prevista (e não casa mais sozinha) |
| `/api/v1/orcamentos/` | CRUD de limites por categoria e mês. Filtros: `mes`, `categoria` |
| `GET /api/v1/dashboard/resumo/?mes=AAAA-MM` | Resumo do mês (saldo, receitas × despesas, contas a pagar, saldo previsto, gastos por categoria, orçamentos, alertas...) |
| `GET /api/v1/dashboard/evolucao/?meses=6` | Receitas e despesas por mês (`ate=AAAA-MM` opcional) |

Regras que valem para o app inteiro:

- **Saldo:** nas contas manuais (sem Pluggy), criar, editar ou apagar transações ajusta o saldo da conta automaticamente.
- **Ignorada:** a transação fica fora de receitas e despesas, mas continua mexendo no saldo. Use para transferências entre contas próprias e para o **pagamento da fatura do cartão na conta corrente**: os gastos já contam no cartão, então sem `ignorada` a despesa conta duas vezes. O dashboard devolve um alerta (`alertas`) quando acha uma saída na corrente com "fatura" ou "cartão" na descrição e sem `ignorada`.
- **Estorno:** uma entrada com categoria de gasto (ex.: compra devolvida) abate o gasto da categoria, os orçamentos e as despesas do mês. Ela não conta como receita.
- **Ocorrências:** são geradas a partir das recorrências sempre que um mês é consultado, e também ao criar uma recorrência. Elas são casadas sozinhas com transações de valor ±10% e data até 5 dias antes ou depois do vencimento. "Atrasada" é calculado: prevista com vencimento antes de hoje.
- **Categorias padrão:** são criadas no registro. Para um usuário que já existia, rode `python manage.py criar_categorias_padrao <email>`.

Comandos de gestão:

```bash
uv run python manage.py criar_categorias_padrao voce@exemplo.com   # idempotente
uv run python manage.py gerar_ocorrencias --mes 2026-12 [--email voce@exemplo.com]
uv run python manage.py verificar_rls                              # confere o RLS (abaixo)
```

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
| `DJANGO_SECURE_SSL_REDIRECT` | não | `True` | Redireciona HTTP → HTTPS (`False` só localmente) |
| `DJANGO_SESSION_COOKIE_SECURE` / `DJANGO_CSRF_COOKIE_SECURE` | não | `True` / `True` | Cookies só via HTTPS (`False` só localmente) |
| `DJANGO_SECURE_HSTS_SECONDS` | não | `2592000` (30 dias) | HSTS |
| `DJANGO_LOG_LEVEL` | não | `INFO` | Nível de log (JSON no stdout em prod) |
| `GIT_SHA` | não (automático) | hash do commit | Exposto no `/api/health/` como `versao`. O Easypanel passa como build arg; não defina à mão |

### `DATABASE_URL` do Supabase

Use o **Session pooler** (porta **5432**), sempre com `sslmode=require`. Ele fica em Supabase → seu projeto → **Connect** → *Session pooler*:

```
postgres://postgres.<ref-do-projeto>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres?sslmode=require
```

Se a senha tiver caracteres especiais (`@`, `:`, `/`, `#`...), codifique-os em URL (ex.: `@` → `%40`).

> **Transaction pooler (porta 6543):** se um dia for usado, é obrigatório definir `DB_DISABLE_SERVER_SIDE_CURSORS=True` e `DB_CONN_MAX_AGE=0`.

Usamos o Supabase **apenas como Postgres**: nada de Supabase Auth, Storage ou supabase-py.

### Data API do Supabase bloqueada (RLS)

O Supabase publica automaticamente as tabelas do schema `public` numa API REST (PostgREST) acessível com a chave `anon`. Para que ninguém leia nada por ali, **toda tabela do `public` tem Row Level Security ligado e nenhuma policy**. Isso vale para as tabelas do projeto, do Django (auth, admin, sessions, contenttypes, `django_migrations`), do simplejwt (`token_blacklist_*`) e do cache (`django_cache`).

- **Como:** um sinal `post_migrate` (`apps/core/rls.py`) roda a cada `migrate`. Ele garante a tabela de cache e liga o RLS nas tabelas que ainda não têm. Tabelas novas ficam cobertas sozinhas no próximo deploy.
- **Por que o Django continua funcionando:** ele conecta com o dono das tabelas (o papel `postgres` do Session pooler, o mesmo que rodou o `migrate`), e o RLS **não se aplica ao dono** enquanto não houver `FORCE ROW LEVEL SECURITY`. **Nunca use FORCE.**
- **Conferir:** `python manage.py verificar_rls` mostra o usuário do banco e, por tabela, o dono e o RLS. O comando falha se alguma tabela estiver sem RLS, com FORCE ou com outro dono. Um teste no CI também falha se alguma tabela ficar sem RLS.
- **Recomendado:** mantenha a **Data API desligada** no painel do Supabase (*Project Settings → Data API*). O RLS é a segunda camada, caso ela seja ligada por engano.

---

## Deploy no Easypanel

A imagem é construída a partir do `Dockerfile` (multi-stage, roda com usuário não root, faz `collectstatic` no build e escuta na porta 8000). Ao subir, o entrypoint roda `migrate` e `createcachetable`; para desligar, use `RODAR_MIGRATIONS=false`.

1. **Criar o serviço:** no projeto do Easypanel, *+ Service* → **App**.
2. **Fonte:** *Source* → **GitHub** → repositório `joaovictorSsouza/financeiro_saas`, branch `main`.
3. **Build:** *Build* → **Dockerfile**, com caminho `Dockerfile`.
4. **Variáveis:** em *Environment*, cole as variáveis (veja o checklist abaixo).
5. **Domínio:** em *Domains*, adicione `api.seudominio.com.br` com HTTPS ligado, apontando para a **porta 8000** do container.
6. **Primeiro deploy:** clique em *Deploy* e acompanhe os logs (os seguintes saem do CI; veja [Deploy contínuo](#deploy-contínuo)). Você deve ver `Aplicando migrations...` e depois o gunicorn em `Listening at: http://0.0.0.0:8000`.
7. **Teste:** abra `https://api.seudominio.com.br/api/health/`. A resposta esperada é `{"status": "ok", "banco": "ok", "versao": "<sha do commit>"}`.
8. **Superusuário:** no *Console* do serviço, rode `python manage.py createsuperuser`.
9. **Primeiro convite:** no mesmo console, rode `python manage.py criar_convite --email voce@exemplo.com`.
10. **Categorias padrão** para usuários criados fora do registro (ex.: o superusuário): `python manage.py criar_categorias_padrao voce@exemplo.com`.
11. **RLS:** `python manage.py verificar_rls` deve terminar com "Todas as tabelas do public têm RLS.".

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

### Deploy contínuo

O deploy em produção é automático e **só acontece pela main com o CI verde**:

```
PR → CI (lint, test, docker) → merge na main → CI de novo na main → job deploy
   → webhook do Easypanel → build do Dockerfile → espera o /api/health/ responder com o SHA novo
```

- O job `deploy` fica no mesmo workflow (`.github/workflows/ci.yml`), com `needs: [lint, test, docker]` e `if` restrito a `push` na `main`. Em PR e em outras branches ele não roda.
- Usa o environment `production` e `concurrency: deploy-production` (um deploy por vez; um push novo espera o atual terminar, sem cancelar).
- Chama o *Deployment Trigger* do Easypanel (segredo `EASYPANEL_DEPLOY_WEBHOOK`) com `curl --fail`, timeout e retry. A URL nunca é impressa.
- **Verificação:** o Easypanel passa `GIT_SHA` como build arg nos builds por Dockerfile; o `Dockerfile` grava esse valor em `ENV GIT_SHA`, e o `/api/health/` o devolve em `versao`. O job consulta `HEALTHCHECK_URL` (variável do repositório) a cada 15 s por até 10 minutos e só passa quando `status` é `ok` e `versao` é o SHA do commit que disparou o deploy. Se nesse meio tempo a main andou e já está no ar um commit mais novo que contém este, o job também passa.
- O **Auto Deploy do Easypanel fica desligado**: quem dispara o deploy é o CI. Deploy manual pelo painel continua possível em emergência, mas o caminho normal é o merge na main.

---

## Testes e qualidade

```bash
make test      # pytest (precisa do Postgres: make up)
make lint      # ruff check + ruff format --check
uv run pytest --cov   # com cobertura
```

O CI (GitHub Actions) roda em todo push e PR: ruff, pytest contra Postgres 17, checagem de migrations pendentes e o build da imagem Docker. Em push na `main`, com tudo verde, roda também o deploy (veja [Deploy contínuo](#deploy-contínuo)).

---

## Estrutura

```
apps/
  core/       ModeloBase (UUID + timestamps), health check, permissões, bases de API, RLS
  accounts/   Usuario (login por e-mail), Convite, registro, JWT, /me
  financas/   Categorias, contas, transações, regras, recorrências, ocorrências, orçamentos
    services/   Regras de negócio (transacoes, regras, ocorrencias, casamento, categorias)
  dashboard/  Leitura agregada (resumo e evolução), sem models
  (bancos/)   Reservado para a integração Pluggy (fase 2)
config/
  settings/   base.py, dev.py, prod.py, test.py
  api_v1.py   Rotas /api/v1/
  gunicorn.conf.py
docker/entrypoint.sh
```
