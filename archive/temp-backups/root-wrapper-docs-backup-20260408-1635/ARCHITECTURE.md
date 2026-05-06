# Arquitetura do Sistema

## Visao geral

O sistema opera hoje como monolito Flask self-hosted em servidor local Windows com frontend oficial desacoplado, banco PostgreSQL local, storage em filesystem e operacao conduzida por servicos Windows.

Arquitetura vigente:

- backend: Flask + Waitress
- frontend oficial: app estatica servida pelo Caddy
- proxy e TLS: Caddy
- banco: PostgreSQL nativo no host local
- storage: filesystem local (`fs:`)
- jobs: fila persistida em banco + workers locais
- backup: dump local + espelhamento opcional

Nao ha mais modelo oficial de deploy em Vercel, Render ou Supabase.

## Componentes principais

### Backend

- app factory: [C:\apps\controle-treinamentos\src\app\__init__.py](C:\apps\controle-treinamentos\src\app\__init__.py)
- blueprints HTTP: [C:\apps\controle-treinamentos\src\app\blueprints](C:\apps\controle-treinamentos\src\app\blueprints)
- contratos e parsing HTTP: [C:\apps\controle-treinamentos\src\app\core](C:\apps\controle-treinamentos\src\app\core)
- aplicacao/regras de negocio: [C:\apps\controle-treinamentos\src\app\application](C:\apps\controle-treinamentos\src\app\application)
- acesso a dados: [C:\apps\controle-treinamentos\src\app\repositories](C:\apps\controle-treinamentos\src\app\repositories)
- jobs/backup/mailer/storage: [C:\apps\controle-treinamentos\src\app\infra](C:\apps\controle-treinamentos\src\app\infra)

### Frontend

- frontend oficial: [C:\apps\controle-treinamentos\frontend-app](C:\apps\controle-treinamentos\frontend-app)
- shell e rotas hash: [C:\apps\controle-treinamentos\frontend-app\src\app.js](C:\apps\controle-treinamentos\frontend-app\src\app.js)
- paginas principais:
  - [C:\apps\controle-treinamentos\frontend-app\src\pages-dashboard-tripulantes.js](C:\apps\controle-treinamentos\frontend-app\src\pages-dashboard-tripulantes.js)
  - [C:\apps\controle-treinamentos\frontend-app\src\pages-treinamentos-relatorios.js](C:\apps\controle-treinamentos\frontend-app\src\pages-treinamentos-relatorios.js)

### Banco e schema

- schema e colunas obrigatorias: [C:\apps\controle-treinamentos\src\app\db\schema.py](C:\apps\controle-treinamentos\src\app\db\schema.py)
- migrations idempotentes: [C:\apps\controle-treinamentos\src\app\db\migrations.py](C:\apps\controle-treinamentos\src\app\db\migrations.py)
- consistencia operacional: [C:\apps\controle-treinamentos\scripts\database\run_db_consistency.py](C:\apps\controle-treinamentos\scripts\database\run_db_consistency.py)

### Storage

- storage local de midia/anexos: [C:\apps\controle-treinamentos\src\app\infra\media_storage.py](C:\apps\controle-treinamentos\src\app\infra\media_storage.py)
- raiz operacional:
  - runtime: [C:\apps\controle-treinamentos\runtime](C:\apps\controle-treinamentos\runtime)
  - operacoes: [C:\apps\controle-treinamentos\ops](C:\apps\controle-treinamentos\ops)

## Ambientes e hospedagem

### Self-hosted Windows

Ambiente oficial:

- homologacao local em `8102`
- producao local em `8101`
- servicos Windows `CT-App-Hml`, `CT-App-Prod`, `CT-Caddy`
- Caddy publicando frontend + proxy do backend

Referencias:

- guia operacional: [C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md](C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md)
- env de producao: [C:\apps\controle-treinamentos\service\windows\env\prod.env.example](C:\apps\controle-treinamentos\service\windows\env\prod.env.example)
- env de homologacao: [C:\apps\controle-treinamentos\service\windows\env\hml.env.example](C:\apps\controle-treinamentos\service\windows\env\hml.env.example)
- Caddy exemplo: [C:\apps\controle-treinamentos\service\windows\Caddyfile.example](C:\apps\controle-treinamentos\service\windows\Caddyfile.example)

## Fluxo de operacao

1. Caddy recebe requisicoes LAN ou dominio publico.
2. O frontend oficial e servido a partir de `C:\srv\controle-treinamentos\frontend\{prod|hml}`.
3. APIs e rotas protegidas seguem para Waitress em `127.0.0.1:8101/8102`.
4. O backend usa PostgreSQL local e storage local.
5. Jobs, notificacoes e backups rodam no host local.

## Seguranca e sessao

- sessao por cookie assinado
- CSRF obrigatorio
- trusted proxy headers configurados no Waitress
- origins oficiais e locais controlados por:
  - `FRONTEND_PUBLIC_ORIGIN`
  - `FRONTEND_LOCAL_ORIGIN`
  - `FRONTEND_ALLOWED_ORIGINS`

## Observacoes arquiteturais

- o repositorio ainda preserva alguns artefatos historicos e de auditoria da migracao, mas o modelo operacional atual e local
- qualquer resquicio documental ou compatibilidade de stack antigo deve ser tratado como legado, nao como rota oficial
- a prova final de migracao completa depende de config real alinhada, runtime recarregado e banco, storage e jobs operando sem qualquer dependencia antiga
