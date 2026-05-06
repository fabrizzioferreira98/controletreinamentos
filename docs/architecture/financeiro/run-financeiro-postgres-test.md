# Runbook: teste PostgreSQL real do schema Financeiro

## Objetivo

Executar `tests/integration/test_financeiro_schema_bootstrap.py` contra um PostgreSQL descartavel/de teste para validar o DDL financeiro em banco real.

Este procedimento existe porque os testes de integracao so rodam quando `DATABASE_URL` esta definida e contem `test`. Esse guardrail evita uso acidental de `ct_local`, homologacao ou producao.

## Pre-requisitos

- PostgreSQL local acessivel.
- Usuario PostgreSQL com permissao para criar banco, ou banco de teste ja criado.
- Ambiente Python do projeto em `.venv`.
- Nome do banco contendo `test`, por exemplo `controle_treinamentos_test`.
- Nunca usar `ct_local`, `ct_hml`, `ct_prod` ou qualquer banco sem `test` no nome.

## Criar banco de teste

Use um banco descartavel com `test` no nome. Exemplo:

```powershell
$env:PGPASSWORD="<senha somente nesta sessao>"
& "C:\Program Files\PostgreSQL\15\bin\createdb.exe" `
  -h 127.0.0.1 `
  -p 5432 `
  -U <usuario> `
  --no-password `
  controle_treinamentos_test
```

Remova a senha temporaria da sessao quando terminar:

```powershell
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
```

Tambem e valido criar o banco manualmente por ferramenta administrativa, desde que o nome contenha `test`.

## Definir DATABASE_URL temporaria

Defina a variavel apenas na sessao PowerShell atual. Nao edite `.env`.

```powershell
$env:DATABASE_URL="postgresql://<usuario>:<senha>@127.0.0.1:5432/controle_treinamentos_test"
```

Conferencia segura:

```powershell
if ($env:DATABASE_URL -notmatch "test") { throw "DATABASE_URL precisa conter test." }
if ($env:DATABASE_URL -match "ct_local|ct_hml|ct_prod") { throw "DATABASE_URL proibida para este teste." }
```

## Rodar o teste manualmente

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_financeiro_schema_bootstrap.py -q
```

Resultado esperado com banco configurado:

- `4 passed`: DDL financeiro validado em PostgreSQL real.
- `4 skipped`: `DATABASE_URL` ausente ou sem `test`.
- falha de constraint/DDL: corrigir o DDL financeiro ou o teste conforme a causa real.

## Rodar com helper operacional

O helper valida a URL, mascara senha no log e executa apenas o pytest de bootstrap financeiro.

Com URL explicita:

```powershell
.\ops\windows\scripts\run_financeiro_schema_test.ps1 `
  -DatabaseUrl "postgresql://<usuario>:<senha>@127.0.0.1:5432/controle_treinamentos_test"
```

Para `-CreateDatabase` ou `-Cleanup`, informe senha por `PGPASSWORD` ou `.pgpass`; o helper nao grava nem imprime senha. Mesmo quando `DatabaseUrl` contem senha, os binarios `createdb.exe` e `dropdb.exe` sao chamados com `--no-password` para evitar prompt interativo.

Com parametros e senha via `PGPASSWORD`:

```powershell
$env:PGPASSWORD="<senha somente nesta sessao>"
.\ops\windows\scripts\run_financeiro_schema_test.ps1 `
  -HostName 127.0.0.1 `
  -Port 5432 `
  -Database controle_treinamentos_test `
  -User <usuario>
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
```

Para criar o banco antes do teste, se o usuario tiver permissao:

```powershell
$env:PGPASSWORD="<senha somente nesta sessao>"
.\ops\windows\scripts\run_financeiro_schema_test.ps1 `
  -HostName 127.0.0.1 `
  -Port 5432 `
  -Database controle_treinamentos_test `
  -User <usuario> `
  -CreateDatabase
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
```

## Limpeza segura

Nao ha drop por padrao. Para remover o banco descartavel, use confirmacao explicita:

```powershell
$env:PGPASSWORD="<senha somente nesta sessao>"
.\ops\windows\scripts\run_financeiro_schema_test.ps1 `
  -HostName 127.0.0.1 `
  -Port 5432 `
  -Database controle_treinamentos_test `
  -User <usuario> `
  -Cleanup `
  -ConfirmCleanup "drop:controle_treinamentos_test"
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
```

O helper recusa cleanup se o banco nao contiver `test`, se for `ct_local`, `ct_hml` ou `ct_prod`, ou se `-ConfirmCleanup` nao bater exatamente.

## Guardrails

- `DATABASE_URL` precisa conter `test`.
- `ct_local`, `ct_hml` e `ct_prod` sao recusados.
- O helper nao edita `.env`.
- Senhas nao devem ser commitadas nem registradas em arquivo.
- Cleanup nunca roda sem `-Cleanup` e `-ConfirmCleanup`.
- Repositories/use cases Financeiro so devem comecar depois de `tests/integration/test_financeiro_schema_bootstrap.py` passar em PostgreSQL real.

## Troubleshooting

### Senha ausente

Sintoma: `fe_sendauth: no password supplied` ou prompt interativo.

Solucao: configure `PGPASSWORD` apenas na sessao atual ou use `.pgpass`/gerenciador local de credenciais. Nao grave senha em arquivo versionado.

### Banco inexistente

Sintoma: `database "..._test" does not exist`.

Solucao: crie o banco com `createdb` ou rode o helper com `-CreateDatabase`.

### DATABASE_URL sem test

Sintoma: teste fica skipped ou helper recusa execucao.

Solucao: use um banco cujo nome contenha `test`, como `controle_treinamentos_test`.

### pg_isready OK mas conexao falha

Sintoma: `pg_isready` responde, mas `pytest` falha por autenticacao.

Solucao: `pg_isready` valida disponibilidade do servidor, nao credenciais. Confira usuario, senha e banco.

### Cluster artifact incompleto

Sintoma: `pg_ctl` informa falta de `global/pg_control`.

Solucao: nao use esse diretorio como banco real. Inicialize um cluster descartavel valido ou use o PostgreSQL local com um banco de teste criado explicitamente.
