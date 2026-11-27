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

## Domínio financeiro (decisões)

- **Mês de referência** é sempre uma `date` no dia 1. A API recebe `?mes=AAAA-MM`. Os utilitários ficam em `apps/financas/datas.py`. Vencimento no dia 31 em mês curto cai no último dia do mês.
- **Categoria:** no máximo 2 níveis, e a subcategoria tem o mesmo `tipo` da pai. Única por `(usuario, nome, categoria_pai)` com `nulls_distinct=False`. Por isso a receita padrão "Outros" se chama **"Outras receitas"** (já existe "Outros" de gasto). As categorias padrão são criadas pelo sinal `accounts.signals.usuario_registrado`, enviado pelo registro por convite; o `accounts` não importa o `financas`.
- **Conta:** com `pluggy_account_id` vazio (`""`) é manual. Os ids da Pluggy (`conexao_pluggy_id`, `pluggy_account_id`, `pluggy_transaction_id`) são texto (`CharField(max_length=64, blank=True, default="")`), porque o formato é de terceiros. `""` significa "sem Pluggy", e a unicidade é condicional (`condition=~Q(campo="")`). Não use `null` em `CharField`. Conta com transações não é apagada sozinha (`RESTRICT`, o mesmo de `Recorrencia.categoria`): desative. Use `RESTRICT` em vez de `PROTECT` em FKs de domínio, para não bloquear a exclusão do usuário inteiro.
- **Saldo:** nas contas manuais, `saldo_centavos` é ajustado pelos serviços de transação (criar, editar, apagar), inclusive para transações ignoradas. Em conta Pluggy o saldo vem do banco.
- **Transação:** `valor_centavos` é sempre positivo, e o sentido vai em `tipo`.
  - Saída com categoria de receita é inválida.
  - **Entrada com categoria de gasto é estorno:** abate o gasto da categoria, os orçamentos e as despesas, e não entra em receitas.
  - Categoria informada pelo usuário (na criação ou na edição) vira `categoria_definida_manualmente=True`, e as regras nunca sobrescrevem isso.
- **Divisão:** a original recebe `dividida=True` e sai das somas e da listagem padrão (`?incluir_divididas=true` mostra as originais). As partes são `Transacao` com `transacao_pai`, não mexem no saldo e só têm categoria, descrição e observação editáveis. A original fica com valor, conta, data, tipo e categoria travados até desfazer a divisão.
- **Regras:** comparam `descricao_original` e `descricao`, sem acentos e sem caixa (`services/texto.normalizar`). Vence a maior `prioridade`; no empate, a mais antiga. Ao corrigir a categoria, a resposta traz `sugestao_regra`, mas nada é criado.
- **Ocorrências:**
  - No banco o status é só `prevista` ou `paga`; "atrasada" é calculado na leitura.
  - `gerar_ocorrencias` é idempotente e roda **sempre** em `/ocorrencias/` e `/dashboard/resumo/`. `casar_ocorrencias` roda ao criar ou editar transação, ao marcar ou desmarcar, e quando o mês consultado ainda não tinha ocorrências.
  - Criar uma recorrência gera o mês atual. Editar atualiza as previstas do mês atual em diante. Desativar apaga as previstas que ainda não venceram; definir `fim` apaga as previstas depois do fim. **Pagas nunca mudam.**
  - `Ocorrencia.transacao` é OneToOne: uma transação quita no máximo uma ocorrência. Desmarcar desliga `casamento_automatico`, para não vincular de novo sozinho.
- **Dashboard:**
  - As somas usam transações não ignoradas e não divididas.
  - `saldo_atual` exclui cartão.
  - `fatura_cartao` é, por ora, a soma das saídas dos cartões no mês.
  - `saldo_previsto_fim_mes` é nulo para meses passados.
  - `proximas_contas` é relativo a hoje (7 dias).
  - `alertas` sinaliza um possível pagamento de fatura na corrente sem `ignorada`. Na fase 2 (Pluggy) isso vira automático.

## Convenções de código

- **Apps** ficam em `apps/<nome>/` com `name = "apps.<nome>"`. Cada app tem `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `services.py` (regras de negócio fora das views) e `tests/` (com `factories.py`).
- **Apps de domínio:** `financas` (todo o domínio: categorias, contas, transações, regras, recorrências, ocorrências e orçamentos), `dashboard` (leitura agregada, sem models) e `bancos` (integração Pluggy, fase 2, ainda não criado). As regras de negócio do `financas` ficam em `apps/financas/services/` (um módulo por assunto) em vez de um `services.py` único.
- **Views de domínio:** herde de `apps.core.api.DoUsuarioViewSet` (ou `DoUsuarioSomenteLeituraViewSet`) e defina `model`. A base filtra por `usuario=self.request.user`, grava `usuario` no `perform_create`, devolve 409 em `ProtectedError`/`RestrictedError` e trata o `swagger_fake_view`. Nunca use `Model.objects.all()` numa view.
- **Serializers:** liste os `fields` explicitamente (nada de `__all__`) e deixe `usuario` fora ou como `read_only`. Toda FK recebida no body usa `apps.core.api.CampoDoUsuario(Model)`, que só aceita objetos do usuário autenticado (id de outro usuário → 400). Unicidades que envolvem `usuario` são validadas no `validate()` do serializer, porque `usuario` não vem no body.
- **Escritas com efeito colateral passam pelos serviços:** transações por `services/transacoes.py`, que cuida do saldo, das regras e do casamento; recorrências por `sincronizar_recorrencia`. O admin também chama esses serviços.
- **Models de domínio:** herdam de `ModeloBase`, têm `usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name=...)` e um índice que começa por `usuario`.
- **Dinheiro:** campos `valor_centavos` / `*_centavos` (`BigIntegerField`). Conversão para reais só na apresentação (frontend).
- **Testes:** pytest + pytest-django + factory_boy. As fixtures `api_client`, `usuario`, `outro_usuario` e `cliente_autenticado` estão no `conftest.py` da raiz. Testes rodam contra Postgres de verdade (`make up`).
- **Lint:** ruff (`make lint` / `make format`), com linha de até 100 caracteres. O pre-commit roda ruff e checks básicos.
- **Migrations:** sempre commitadas junto com o model. O CI falha se faltar migration (`makemigrations --check`).
- **RLS (Supabase):** toda tabela do schema `public` tem `ENABLE ROW LEVEL SECURITY` sem policies, para bloquear a Data API (PostgREST/`anon`). Isso é aplicado pelo sinal `post_migrate` em `apps/core/rls.py` a cada `migrate` e cobre tabelas novas sozinho. **Não crie migration para isso, não crie policies e nunca use `FORCE ROW LEVEL SECURITY`**: o Django conecta como dono das tabelas, e o RLS sem FORCE não se aplica ao dono. O teste `apps/core/tests/test_rls.py` falha se alguma tabela ficar sem RLS. Em produção, confira com `manage.py verificar_rls`. A Data API deve ficar desligada no painel do Supabase.
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
| `manage.py criar_categorias_padrao <email>` | Categorias padrão para um usuário existente (idempotente) |
| `manage.py gerar_ocorrencias --mes AAAA-MM [--email]` | Gera as ocorrências do mês (idempotente) |
| `manage.py verificar_rls` | Lista dono e RLS das tabelas do `public`; falha se houver problema |
