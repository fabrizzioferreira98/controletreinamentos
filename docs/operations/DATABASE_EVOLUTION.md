# Evolucao de Banco

## Objetivo

Separar a trilha de evolucao do banco em caminhos previsiveis. Bootstrap estrutural, migracao corretiva, compat historica, seed/import e sync operacional nao sao a mesma coisa.

## Classificacao dos artefatos

| grupo | artefatos | papel | roda por default |
| --- | --- | --- | --- |
| bootstrap estrutural | `backend/src/controle_treinamentos/db/schema.py`, `schema_bootstrap.py`, `backend/tools/maintenance/bootstrap_db_schema.py` | Sobe tabelas, colunas, indices e checks declarados no schema canonico. | Sim, via `bootstrap_db_schema.py`. |
| migracao corretiva | `backend/src/controle_treinamentos/db/migrations.py`, `backend/tools/manual_unsafe/run_db_repair.py` | Corrige bancos historicos e aplica ajustes legados quando o repair manual for acionado. | Nao. |
| seed minima runtime | `backend/src/controle_treinamentos/db/seeder.py`, `backend/tools/maintenance/bootstrap_seed_data.py` | Aplica bases/defaults operacionais minimos depois do schema. | Sim, mas separado do schema. |
| seed/import historico | `backend/src/controle_treinamentos/db/training_program_seed.py`, `backend/tools/data/import_tripulantes_csv.py`, `ops/scripts/database/import_tripulantes_csv.py` | Carga herdada ou importacao pontual de massa historica. | Nao; fica congelado e exige ack para escrita. |
| sync operacional | `ops/scripts/database/sync_training_master_types.py` | Reconciliacao pontual de catalogo entre ambientes. | Nao. |
| compat historica | `backend/tools/compat_residual/sync_tripulantes_snapshot.py`, `ops/scripts/database/sync_tripulantes_snapshot.py`, `migrate_tripulante_media_to_storage.py`, `reconcile_tripulante_photos.py` | Reconciliacao ou migracao residual de legado vivo/historico. | Nao; usa dry-run/apply ack quando aplicavel. |
| validacao | `backend/tools/maintenance/run_db_consistency.py`, `ops/scripts/database/run_db_consistency.py` | Valida schema e dados; repair fica redirecionado para manual unsafe. | Sim, sem repair. |
| manual unsafe | `backend/tools/manual_unsafe/cleanup_operational_data.py` | Cleanup destrutivo e isolado. | Nao. |

A classificacao executavel fica em `backend/src/controle_treinamentos/db/evolution_paths.py`.

## Trilha principal

1. Sobe schema: `backend/tools/maintenance/bootstrap_db_schema.py`.
2. Aplica seed minima: `backend/tools/maintenance/bootstrap_seed_data.py`.
3. Valida sem repair: `backend/tools/maintenance/run_db_consistency.py`.

Essa trilha nao chama seed historico, import historico, sync entre ambientes, snapshot residual, cleanup destrutivo ou repair manual.

## Correcoes e legado

| necessidade | caminho |
| --- | --- |
| Corrigir banco historico | `backend/tools/manual_unsafe/run_db_repair.py`, que chama `execute_corrective_migrations`. |
| Reconcilia legado/snapshot | `backend/tools/compat_residual/sync_tripulantes_snapshot.py` ou scripts de compat em `ops/scripts/database/`, sempre fora da trilha principal. |
| Importar massa historica | `backend/tools/data/import_tripulantes_csv.py` com dry-run primeiro e ack explicito para aplicar. |
| Sincronizar catalogo entre ambientes | `ops/scripts/database/sync_training_master_types.py`, dry-run por padrao e `--apply` apenas por decisao operacional. |

## Itens congelados

- `training_program_seed.py`: leitura permitida para analise/testes; escrita exige `seed-training-program-reference-historico`.
- `import_tripulantes_csv.py`: dry-run e permitido; escrita exige `import-tripulantes-csv-historico`.
- `sync_tripulantes_snapshot.py`: compat residual com `--apply-ack`.
- Migracoes de media/foto legadas: continuam fora da trilha principal e so devem rodar como reconciliacao historica controlada.

## Regra de mudanca

- Regra estrutural nova entra em `schema.py` e `schema_bootstrap.py`.
- Correcao de banco historico entra em `migrations.py` como corretiva, sem seed/import/sync.
- Dados minimos de runtime entram em `seeder.py`.
- Carga herdada, snapshot ou sync entre ambientes nao entram na trilha principal.
