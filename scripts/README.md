# Scripts de Compatibilidade

## Papel

`scripts/` existe apenas para compatibilidade controlada. Nao e trilha principal, nao e comando canonico e nao recebe novos fluxos.

## Caminho canonico

Os comandos oficiais ficam em `docs/operations/canonical-commands.md`. Quando existir caminho oficial, ele deve ser preferido a qualquer wrapper daqui.

## Wrappers mantidos

| wrapper de compatibilidade | trilha canonica |
| --- | --- |
| `scripts/backup/run_backups.py` | `backend/tools/maintenance/run_backups.py` |
| `scripts/database/run_db_consistency.py` | `backend/tools/maintenance/run_db_consistency.py` |
| `scripts/jobs/run_jobs_worker.py` | `backend/tools/maintenance/run_jobs_worker.py` |
| `scripts/jobs/run_notifications.py` | `backend/tools/maintenance/run_notifications.py` |
| `scripts/windows/Invoke-AppService.ps1` | `ops/windows/scripts/Invoke-AppService.ps1` |
| `scripts/windows/Invoke-OperationalPython.ps1` | `ops/windows/scripts/Invoke-OperationalPython.ps1` |

## Regra de uso

Cada wrapper deve permanecer fino, avisar que e compatibilidade e delegar para a trilha canonica.

## Politica para wrapper novo

Wrapper novo em `scripts/` so e permitido quando todos os criterios forem verdadeiros:

1. Existe consumidor real que ainda chama o caminho antigo.
2. O wrapper e fino: nao contem regra principal, apenas aviso e delegacao.
3. A trilha canonica esta declarada na tabela de wrappers mantidos.
4. A fila de remocao registra consumidor atual, pre-condicao de remocao e risco.
5. O arquivo tem cabecalho `COMPAT:` e avisa que nao e comando oficial.

Sem esses cinco itens, o wrapper deve nascer no caminho canonico correto ou ser recusado.

## Saida futura

A remocao segue `docs/governance/legacy-policy.md` quando consumidores historicos migrarem.

## Fila de remocao

| wrapper | substituto canonico | consumidor atual | pre-condicao de remocao | risco |
| --- | --- | --- | --- | --- |
| `scripts/backup/run_backups.py` | `backend/tools/maintenance/run_backups.py` | sem consumidor operacional conhecido; teste de shim protege o path | confirmar ausencia de job/atalho externo e atualizar ou remover `tests/unit/test_legacy_windows_compat.py` | backup antigo deixar de rodar em agendador externo |
| `scripts/database/run_db_consistency.py` | `backend/tools/maintenance/run_db_consistency.py` | sem consumidor operacional conhecido; teste de shim protege o path | confirmar ausencia de rotina manual/atalho externo e atualizar ou remover `tests/unit/test_legacy_windows_compat.py` | diagnostico ou reparo antigo falhar por path removido |
| `scripts/jobs/run_jobs_worker.py` | `backend/tools/maintenance/run_jobs_worker.py` | sem consumidor operacional conhecido; teste de shim protege o path | confirmar ausencia de agendador externo e atualizar ou remover `tests/unit/test_legacy_windows_compat.py` | worker antigo parar de processar jobs |
| `scripts/jobs/run_notifications.py` | `backend/tools/maintenance/run_notifications.py` | sem consumidor operacional conhecido; teste de shim protege o path | confirmar ausencia de chamada externa e atualizar ou remover `tests/unit/test_legacy_windows_compat.py` | notificacoes antigas deixarem de ser disparadas |
| `scripts/windows/Invoke-AppService.ps1` | `ops/windows/scripts/Invoke-AppService.ps1` | sem consumidor operacional conhecido no repo; teste de shim protege o path | auditar servicos, atalhos e Task Scheduler fora do repo; migrar para `ops/windows/scripts`; atualizar ou remover teste de shim | servico Windows antigo nao subir |
| `scripts/windows/Invoke-OperationalPython.ps1` | `ops/windows/scripts/Invoke-OperationalPython.ps1` | sem consumidor operacional conhecido no repo; teste de shim protege o path | auditar tarefas agendadas e atalhos fora do repo; migrar para `ops/windows/scripts`; atualizar ou remover teste de shim | rotina operacional antiga falhar |

## Classificacao de saida

- Remover em breve: nenhum wrapper de alto risco fica nesta classe sem prova objetiva de ausencia de consumidor externo.
- Remover depois de migracao: wrappers Windows, porque podem existir servicos ou tarefas locais fora do repo.
- Manter por enquanto: apenas enquanto o teste de shim ou consumidor externo confirmado ainda depender do path antigo.

## Ratificacao Frente 31

| bloco | wrapper | classificacao | decisao |
| --- | --- | --- | --- |
| `31.3.1` | `scripts/backup/run_backups.py` | `compat_residual_congelado` | consumidor interno operacional nao encontrado; ausencia externa nao provada; manter bloqueado |
| `31.3.1` | `scripts/jobs/run_jobs_worker.py` | `compat_residual_congelado` | consumidor interno operacional nao encontrado; ausencia externa nao provada; manter bloqueado |
| `31.3.1` | `scripts/windows/Invoke-AppService.ps1` | `compat_residual_congelado` | consumidor interno operacional nao encontrado; ausencia externa nao provada; manter bloqueado |
| `31.3.1` | `scripts/windows/Invoke-OperationalPython.ps1` | `compat_residual_congelado` | consumidor interno operacional nao encontrado; ausencia externa nao provada; manter bloqueado |
| `31.3.2` | `scripts/database/run_db_consistency.py` | `compat_residual_congelado` | manter ate confirmar ausencia de rotina manual/atalho externo e atualizar teste de shim |
| `31.3.2` | `scripts/jobs/run_notifications.py` | `compat_residual_congelado` | manter ate confirmar ausencia de chamada externa e atualizar teste de shim |

Regra final da Frente 31: nenhum wrapper em `scripts/` fica liberado para remocao sem prova objetiva de consumidor externo migrado ou ausente. A ausencia de consumidor operacional dentro do repo nao basta para remover.
