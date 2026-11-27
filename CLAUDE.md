# CLAUDE.md

Memória do projeto entre sessões. Leia antes de qualquer mudança e mantenha atualizado quando uma decisão nova for tomada.

## Visão do produto

App de finanças pessoais. Este repositório é **só a API**; o frontend é um PWA no iPhone, em repositório separado.

- O usuário cadastra receitas e contas fixas do mês e lança gastos.
- Numa fase seguinte, as transações virão automaticamente do banco via **Meu Pluggy** (API da Pluggy, Open Finance Brasil).
- Dashboard: saldo atual, saldo previsto no fim do mês, receitas × despesas, gastos por categoria, próximas contas, orçamentos e evolução de 6 meses.
- No início há um único usuário (o dono). Depois entram amigos e familiares, cada um vendo **somente os próprios dados**. Cadastro **apenas por convite**.

## REGRAS PERMANENTES

1. **Todo dado financeiro pertence a um usuário.** Todo model de domínio tem `usuario` (FK para `settings.AUTH_USER_MODEL`), e toda queryset de API é filtrada pelo usuário autenticado (`request.user`). **Nunca confiar em `usuario` vindo do request body**: ele é sempre definido no servidor (`serializer.save(usuario=request.user)`) e não é campo gravável no serializer.
2. **Valores monetários são inteiros em centavos** (`BigIntegerField`). Nunca `float`, nem `DecimalField` para dinheiro.
3. **Segredos só por variável de ambiente.** Nada de chave, senha ou token no código, nos testes de integração ou nos commits. `.env` nunca é commitado.
4. **Toda funcionalidade nova vem com testes**, incluindo um teste que prova que um usuário **não acessa dados de outro** (listar, detalhar, editar e apagar recurso alheio → 404).
5. **Código, nomes de models e campos em português sem acentos** (ex.: `transacao`, `categoria`, `valor_centavos`). Mensagens de commit no padrão **Conventional Commits em português** (ex.: `feat(transacoes): adiciona lancamento manual`).

## Stack e decisões já tomadas

- **Python 3.12**, **Django 5.2 LTS**, **Django REST Framework**. Dependências com **uv** (`pyproject.toml` + `uv.lock`; `uv add <pacote>`, nunca pip).
- **Configuração** por variáveis de ambiente com `django-environ`. O `.env.example` documenta todas; toda variável nova entra nele e no README.
- **Settings** em `config/settings/`: `base.py`, `dev.py`, `prod.py` e `test.py`. O `manage.py` usa `dev` por padrão; a imagem Docker usa `prod`.
- **Banco:** Postgres 17. Em dev roda no docker-compose (`POSTGRES_VERSION`); em produção é o Postgres do Supabase, **só como Postgres** (sem Supabase Auth, Storage nem supabase-py). A conexão é pelo **Session pooler** (porta 5432, `sslmode=require`). Se um dia usarmos o Transaction pooler (6543): `DB_DISABLE_SERVER_SIDE_CURSORS=True` e `DB_CONN_MAX_AGE=0`. Driver: psycopg 3.
- **Usuário customizado** `accounts.Usuario`: login por e-mail, sem username, UUID como PK. O e-mail é normalizado para minúsculas.
- **PKs:** todos os models herdam de `apps.core.models.ModeloBase` (UUID, `criado_em`, `atualizado_em`).
- **Autenticação:** JWT com `djangorestframework-simplejwt`. O access é curto (15 min) e o refresh dura 7 dias, com **rotação e blacklist**. A emissão de tokens é centralizada em `apps.accounts.services.gerar_tokens`.
  - *Melhoria futura:* hoje o refresh vai no corpo da resposta. Avaliar movê-lo para um cookie `HttpOnly; Secure; SameSite` (o access continua no header).
  - *Passkeys/WebAuthn (fase futura):* criar o model `CredencialPasskey` (FK `usuario`, `credential_id`, `public_key`, `sign_count`, `transports`, `criado_em`, `ultimo_uso_em`) e endpoints `auth/passkey/registro/{opcoes,verificar}` e `auth/passkey/login/{opcoes,verificar}`. O login por passkey deve chamar `gerar_tokens` e não duplicar a lógica. O model `Usuario` não precisa mudar.
- **Cadastro por convite:** o model `Convite` tem `codigo` único gerado com `secrets`, `email` opcional, `criado_por`, `usado_por`, `expira_em` (padrão 7 dias) e `usado_em`. O registro consome o convite numa transação com `select_for_update`. Convites são gerados pelo admin ou com `manage.py criar_convite`.
- **Rotas:** tudo sob `/api/v1/` (registrado em `config/api_v1.py`), exceto `/api/health/`, `/api/schema/`, `/api/docs/` e `/admin/`.
- **OpenAPI** com `drf-spectacular`. O Swagger em `/api/docs/` fica aberto em DEBUG; fora dele exige login (sessão do admin ou Bearer). O schema precisa passar em `spectacular --validate --fail-on-warn` (há um teste para isso), então use `@extend_schema` em `APIView`.
- **Throttling:** `ScopedRateThrottle` nos escopos `login` e `registro`. O cache é `DatabaseCache` (tabela `django_cache`, criada por `createcachetable` no entrypoint e no `make setup`). Na fase da Pluggy, trocar por Redis.
- **CORS:** `django-cors-headers`, com origens via `CORS_ALLOWED_ORIGINS` e sem credenciais (o JWT vai no header).
- **Produção:** Easypanel na VPS, build pelo `Dockerfile` (multi-stage, não root, porta 8000) e gunicorn configurado em `config/gunicorn.conf.py` via env. O TLS fica no proxy (`SECURE_PROXY_SSL_HEADER`, `DRF_NUM_PROXIES=1`). Logs em JSON no stdout. O entrypoint roda `migrate` e `createcachetable` (desligável com `RODAR_MIGRATIONS=false`).
- **Fuso e idioma:** `TIME_ZONE="America/Sao_Paulo"`, `USE_TZ=True`, `LANGUAGE_CODE="pt-br"`. Datas são gravadas em UTC; para "mês corrente" use `timezone.localdate()`.

## Convenções de código

- **Apps** ficam em `apps/<nome>/` com `name = "apps.<nome>"`. Cada app tem `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `services.py` (regras de negócio fora das views) e `tests/` (com `factories.py`).
- **Apps de domínio previstos:** `contas` (contas bancárias), `categorias`, `transacoes`, `recorrencias` (receitas e contas fixas), `orcamentos`, `dashboard` e `integracoes` (Pluggy).
- **Views de domínio:** use `ViewSet`/`generics` com `get_queryset()` filtrando por `usuario=self.request.user` e `perform_create` com `serializer.save(usuario=self.request.user)`. Nunca use `Model.objects.all()` numa view.
- **Serializers:** listar os `fields` explicitamente (nada de `__all__`) e deixar `usuario` fora ou como `read_only`. Toda FK recebida no body (ex.: `categoria`) deve ser validada como pertencente ao mesmo usuário.
- **Models de domínio:** herdam de `ModeloBase`, têm `usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name=...)` e um índice que começa por `usuario`.
- **Dinheiro:** campos `valor_centavos` / `*_centavos` (`BigIntegerField`). Conversão para reais só na apresentação (frontend).
- **Testes:** pytest + pytest-django + factory_boy. As fixtures `api_client`, `usuario`, `outro_usuario` e `cliente_autenticado` estão no `conftest.py` da raiz. Testes rodam contra Postgres de verdade (`make up`).
- **Lint:** ruff (`make lint` / `make format`), com linha de até 100 caracteres. O pre-commit roda ruff e checks básicos.
- **Migrations:** sempre commitadas junto com o model. O CI falha se faltar migration (`makemigrations --check`).
- **Fluxo:** branch `feat/...` ou `fix/...` a partir da `main`, commits pequenos, PR com descrição e `make lint` + `make test` verdes.

## Comandos (Makefile)

| Comando | O que faz |
|---|---|
| `make setup` | `uv sync`, cria o `.env`, instala o pre-commit, sobe o Postgres, roda `migrate` e `createcachetable` |
| `make up` / `make down` | Sobe e para o Postgres local (docker-compose) |
| `make up-api` | Postgres + API com a imagem de produção em `:8000` |
| `make run` | `runserver 0.0.0.0:8000` |
| `make test` | pytest |
| `make lint` / `make format` | ruff check/format |
| `make migrate` / `make makemigrations` | migrations |
| `make superuser` | `createsuperuser` |
| `make convite ARGS="--email x@y.com --dias 7"` | `criar_convite` |
| `make shell` | shell do Django |
