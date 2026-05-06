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

- app factory: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\__init__.py](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\__init__.py)
- blueprints HTTP: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\blueprints](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\blueprints)
- contratos e parsing HTTP: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\core](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\core)
- aplicacao/regras de negocio: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\application](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\application)
- acesso a dados: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\repositories](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\repositories)
- jobs/backup/mailer/storage: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\infra](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\infra)

### Frontend

- frontend oficial: [C:\apps\controle-treinamentos\frontend](C:\apps\controle-treinamentos\frontend)
- shell e rotas hash: [C:\apps\controle-treinamentos\frontend\src\app.js](C:\apps\controle-treinamentos\frontend\src\app.js)
- paginas principais:
  - [C:\apps\controle-treinamentos\frontend\src\pages-dashboard-tripulantes.js](C:\apps\controle-treinamentos\frontend\src\pages-dashboard-tripulantes.js)
  - [C:\apps\controle-treinamentos\frontend\src\pages-treinamentos-relatorios.js](C:\apps\controle-treinamentos\frontend\src\pages-treinamentos-relatorios.js)

### Banco e schema

- schema e colunas obrigatorias: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\db\schema.py](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\db\schema.py)
- migrations idempotentes: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\db\migrations.py](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\db\migrations.py)
- consistencia operacional: [C:\apps\controle-treinamentos\backend\tools\maintenance\run_db_consistency.py](C:\apps\controle-treinamentos\backend\tools\maintenance\run_db_consistency.py)

### Storage

- storage local de midia/anexos: [C:\apps\controle-treinamentos\backend\src\controle_treinamentos\infra\media_storage.py](C:\apps\controle-treinamentos\backend\src\controle_treinamentos\infra\media_storage.py)
- raiz operacional:
  - runtime externo: `D:\srv-data\controle-treinamentos\<env>\runtime`
  - operacoes versionadas: [C:\apps\controle-treinamentos\ops](C:\apps\controle-treinamentos\ops)

## Ambientes e hospedagem

### Self-hosted Windows

Ambiente oficial:

- homologacao local em `8102`
- producao local em `8101`
- servicos Windows `CT-App-Hml`, `CT-App-Prod`, `CT-Caddy`
- Caddy publicando frontend + proxy do backend

Referencias:

- guia operacional: [C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md](C:\apps\controle-treinamentos\docs\operations\WINDOWS_SELF_HOSTED_SERVER.md)
- env de producao: [C:\apps\controle-treinamentos\ops\windows\env\prod.env.example](C:\apps\controle-treinamentos\ops\windows\env\prod.env.example)
- env de homologacao: [C:\apps\controle-treinamentos\ops\windows\env\hml.env.example](C:\apps\controle-treinamentos\ops\windows\env\hml.env.example)
- Caddy exemplo: [C:\apps\controle-treinamentos\ops\windows\caddy\Caddyfile.example](C:\apps\controle-treinamentos\ops\windows\caddy\Caddyfile.example)

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
