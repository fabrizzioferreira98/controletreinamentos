# Backlog de remocao futura

## Objetivo

Registrar candidatos a limpeza fisica futura sem autorizar remocao imediata.

Um item neste backlog so pode ser removido quando a pre-condicao estiver atendida, o risco estiver aceito e a trilha canonica continuar funcionando.

## Politica incremental de limpeza - etapa 3.2.5

Esta politica transforma a higiene diagnosticada na frente 3.2 em fila objetiva. Nenhum item abaixo autoriza remocao por impulso: a acao indica o proximo tratamento semantico e a pre-condicao define quando a limpeza fisica e segura.

Categorias de acao:

- `remover ja`: artefato local/gerado sem consumidor real e sem valor historico.
- `isolar`: precisa existir temporariamente, mas nao pode parecer trilha principal.
- `congelar`: preservar para historico, auditoria ou contexto, sem novo uso vivo.
- `morrer depois`: manter enquanto houver consumidor, teste, compatibilidade ou legado vivo; remover apenas quando a condicao de saida for comprovada.

### Fila de limpeza incremental

| item | acao | motivo | pre-condicao |
| --- | --- | --- | --- |
| `.ruff_cache/` | remover ja | Cache de tooling; nao e arquitetura, fonte, build oficial ou evidencia. | Confirmar que e cache local e rodar hygiene depois da remocao. |
| `__pycache__/` e `*.pyc*` fora da `.venv/` | remover ja | Bytecode Python gerado em `backend/`, `ops/` e `tests`; polui source e validacao. | Confirmar ausencia de arquivo manualmente versionado por excecao, remover caches e rodar hygiene. |
| `archive/local-artifacts/.DS_Store` | remover ja | Artefato local macOS, ja classificado como fora do padrao. | Confirmar ausencia de referencia interna e atualizar `archive/MANIFEST.md` se a remocao exigir rastreio historico. |
| `.vscode/` | remover ja | Preferencia local de editor; deixou de ser excecao local oficial e nao deve reaparecer na trilha viva. | Confirmar ausencia de configuracao obrigatoria no repo, remover a pasta e manter hygiene verde. |
| `.venv/` | isolar | Ambiente local pesado dentro da raiz; util para desenvolvimento, mas nao topologia oficial. | Pode sair quando README/runbooks aceitarem ambiente externo ou variavel padronizada e checkout limpo for validado sem `.venv/`. |
| `frontend/dist/` | isolar | Build gerado do frontend; nao e fonte viva nem referencia arquitetural. | Remover do repo vivo quando o build canonico por `frontend/scripts/build_frontend.py` estiver validado e nenhuma rotina depender de arquivos pregerados no workspace. |
| `backend/tools/manual_unsafe/*` | isolar | Repair e cleanup destrutivos precisam existir fora da trilha normal. | So remover quando cada operacao virar migracao corretiva auditavel, rotina segura ou deixar de ter consumidor real. |
| `backend/tools/compat_residual/sync_tripulantes_snapshot.py` | isolar | Snapshot residual de dados; nao pode parecer job canonico. | Remover quando homologacao/restore nao dependerem mais de reidratacao por snapshot e houver evidencia de ausencia de consumidor. |
| `ops/scripts/database/sync_tripulantes_snapshot.py` | isolar | Implementacao residual com dados sensiveis; operacional apenas sob ack/controle. | Remover junto do wrapper residual quando snapshots nao forem mais necessarios para restore/homologacao. |
| `tripulantes.status` e `tripulantes.base` | morrer depois | Espelhos/snapshots residuais; owner canonico de status/base operacional e `pilotos.status` e `pilotos.base_id`. | Remover quando todos os tripulantes vivos tiverem piloto canonico, restore/homologacao nao dependerem do snapshot, scripts residuais forem aposentados e a varredura de codigo provar ausencia de leitor/escritor residual. |
| `treinamentos.aeronave_modelo` | morrer depois | Nome fisico legado que agora representa apenas `aeronave_modelo_snapshot`; a referencia canonica de programa e `horas_voo_aeronave(tipo_treinamento_id, aeronave_modelo)`. | Renomear/remover alias quando serializers, filtros, relatorios, imports e consumidores externos usarem apenas `aeronave_modelo_snapshot`/`aeronave_modelo_referencia`, constraints estruturais estiverem validadas e varredura provar ausencia de leitura/escrita pelo nome fisico como fonte principal. |
| `tripulantes.foto_base64` | morrer depois | Blob legado/base64 congelado; owner canonico e `tripulantes.foto_storage_ref` com arquivo em storage. | Remover quando todas as fotos residuais forem migradas/limpas, `load_tripulante_photo_payload` nao precisar mais do fallback e restore/homologacao provarem ausencia de dependencia do base64. |
| `tripulante_arquivos_pdf.arquivo_pdf` | morrer depois | Blob legado em banco; owner canonico e `tripulante_arquivos_pdf.storage_ref`. | Remover quando inventario `db:bytea` de documentos de tripulante estiver zerado, contratos nao exibirem compat residual e fallback de leitura for retirado com teste. |
| `treinamento_anexos_pdf.arquivo_pdf` | morrer depois | Blob legado em banco; owner canonico e `treinamento_anexos_pdf.storage_ref`. | Remover quando inventario `db:bytea` de anexos estiver zerado, restore validar apenas `fs:` e fallback de leitura for retirado com teste. |
| `db:bytea` | morrer depois | Sentinela de storage legado; sobrevive apenas para fallback isolado de PDF historico. | Remover quando nenhuma metadata viva usar `storage_ref = 'db:bytea'`, scripts de migracao historica forem aposentados e contratos deixarem de precisar de `compat_source=db:bytea`. |
| `sistema_controle` residual generico | morrer depois | Superficie generica congelada; apenas `notification_last_*` e `cache:*` permanecem permitidos. | Remover/particionar quando notificacoes tiverem owner especifico, cache persistido legado for aposentado e hygiene provar ausencia de novos usos genericos. |
| `idx_treinamentos_tripulante_vencimento` | morrer depois | Indice criado por migracao corretiva com mesmas colunas de `idx_treinamentos_tripulante_data_vencimento`. | Dropar apenas em migracao pequena apos medir `pg_stat_user_indexes`, validar planos e confirmar que o indice canonico cobre o workload. |
| `idx_treinamentos_vencimento` | morrer depois | Indice criado por migracao corretiva com mesmas colunas de `idx_treinamentos_data_vencimento`. | Dropar apenas em migracao pequena apos medir `pg_stat_user_indexes`, validar planos e confirmar que o indice canonico cobre o workload. |
| `idx_treinamentos_data_venc_tripulante` | morrer depois | Indice sobreposto em ordem reversa; pode ser util para filtros liderados por vencimento. | Manter sob medicao ate provar que filtros por vencimento nao dependem da ordem reversa; se inutil, remover em migracao dedicada. |
| `ops/scripts/database/cleanup_operational_data.py` | isolar | Implementacao destrutiva; deve continuar fora de rotina normal. | Remover quando cleanup segmentado e seguro substituir o script ou quando nao houver mais caso operacional documentado. |
| Docs vivas acusadas como `documentation_drift` pelo hygiene | isolar | O validator e o indice documental divergem; isso cria falso positivo e ambiguidade de fonte viva. | Registrar na allowlist/governanca ou consolidar/arquivar cada doc; hygiene deve ficar verde sem esconder doc concorrente. |
| `docs/archive/*` e `docs/archive/operations/*` | congelar | Documentos antigos e relatorios preservados; nao podem competir com docs vivas. | Remover apenas se nao houver referencia, valor de auditoria ou necessidade historica registrada. |
| `docs/migration/retired-platforms/*` | congelar | Plataformas retiradas como Render/Vercel/Gunicorn antigo; nao sao deploy atual. | Remover quando a decisao de aposentadoria estiver coberta por doc viva ou registro historico menor. |
| `archive/repo-snapshots/frontend-*` | congelar | Snapshots de builds/hotfixes de frontend; historico de migracao encerrada. | Remover quando nao houver auditoria, comparacao, bug hunt ou referencia documental pendente. |
| `archive/temp-backups/root-wrapper-docs-backup-20260408-1635/` | congelar | Backup de wrappers/docs antigos de raiz; nao executa operacao. | Remover quando docs vivas e wrappers canonicos forem suficientes e nenhuma referencia interna apontar para o backup. |
| `archive/temp-backups/src-app-backup-20260408-154654/` | congelar | Backup de arvore antiga de app; serve apenas para diff/auditoria residual. | Remover quando nao houver auditoria pendente e backend atual/testes cobrirem a funcao viva. |
| `archive/temp-backups/src-app-__init__-backup-20260408-1610.py` | congelar | Backup pontual de inicializacao antiga. | Remover quando nao houver investigacao pendente sobre inicializacao/compat antiga. |
| `archive/temp-backups/nested-repo-copy-20260415/` | congelar | Copia aninhada grande; historico classificado, nao raiz alternativa. | Remover quando automacoes externas nao apontarem para ela e nao houver valor de auditoria pendente. |
| `archive/old-wrappers/*.py` | congelar | Wrappers mortos preservados para entender aliases antigos. | Remover quando consumidores antigos estiverem migrados/inexistentes e `archive/MANIFEST.md` for atualizado. |
| `scripts/*` | morrer depois | Wrappers de compat vivos; finos, mas ainda podem ter consumidor externo. | Remover item a item quando consumidores externos forem auditados/migrados, teste de shim for removido/atualizado e docs oficiais apontarem so para trilha canonica. |
| `backend/src/controle_treinamentos/compat/http_entrypoints/*.py` | morrer depois | Entrypoints HTTP residuais de compat; nao sao runtime/scheduler oficial. | Remover quando nenhum provedor, deploy antigo ou consumidor HTTP depender desses caminhos. |
| `backend/src/controle_treinamentos/compat/python_reexports/*.py` | morrer depois | Reexports para imports antigos; nao devem receber codigo novo. | Remover quando busca/testes provarem ausencia de import legado e consumidores externos forem descartados. |
| `backend/src/controle_treinamentos/service_layers/domain_validation.py` | morrer depois | Superficie antiga de import ainda protegida por teste; producao nao deve depender dela. | Remover quando imports legados forem zerados e regras restantes tiverem owner canonico sem compat. |
| `backend/src/controle_treinamentos/ui/form_renderers.py` | morrer depois | Placeholder legado sem API exportada; existe para impedir reintroducao acidental. | Remover quando a ausencia da camada visual compartilhada estiver coberta por teste/governanca sem precisar do placeholder. |
| `legacy/` como container | morrer depois | Inventario de legado vivo real; nao e pasta decorativa enquanto houver consumidor. | Remover quando todos os itens de `legacy/LIVE_LEGACY.md` forem migrados, removidos ou arquivados, com testes/docs atualizados. |

### Regra incremental de execucao

1. Limpar primeiro somente `remover ja`, porque nao ha consumidor operacional esperado.
2. Em seguida, tratar `isolar` para impedir que artefato local, build gerado ou script perigoso pareca caminho principal.
3. Depois, manter `congelar` sem novos usos e reduzir o volume apenas quando o valor historico acabar.
4. Por ultimo, executar `morrer depois` item a item, sempre com pre-condicao comprovada, teste ou smoke relevante e atualizacao de docs.

## Backlog

| item | categoria | papel atual | pre-condicoes verificaveis | classificacao de saida |
| --- | --- | --- | --- | --- |
| `scripts/backup/run_backups.py` | compat temporaria | Wrapper fino para `backend/tools/maintenance/run_backups.py`. | Consumidor migrado ou ausencia comprovada em docs, runbooks, workflows, atalhos e rotinas externas; `scripts/README.md` e `docs/operations/canonical-commands.md` seguem apontando o caminho canonico; smoke/release de backup alinhados; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `scripts/database/run_db_consistency.py` | compat temporaria | Wrapper fino para `backend/tools/maintenance/run_db_consistency.py`. | Consumidor migrado ou ausencia comprovada; docs operacionais apontam somente para o caminho canonico; validacao de consistencia de banco segue verde; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `scripts/jobs/run_jobs_worker.py` | compat temporaria | Wrapper fino para `backend/tools/maintenance/run_jobs_worker.py`. | Task Scheduler, atalhos e rotinas externas migrados ou descartados com evidencia; docs de jobs apontam para o caminho canonico; worker validado na trilha oficial; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `scripts/jobs/run_notifications.py` | compat temporaria | Wrapper fino para `backend/tools/maintenance/run_notifications.py`. | Consumidor externo migrado ou ausencia comprovada; docs de jobs/notifications apontam para o caminho canonico; execucao de notifications validada na trilha oficial; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `scripts/windows/Invoke-AppService.ps1` | compat temporaria | Wrapper fino para `ops/windows/scripts/Invoke-AppService.ps1`. | Servicos, atalhos e Task Scheduler migrados para `ops/windows/scripts/`; docs Windows/self-hosted apontam para a trilha canonica; validacao Windows executada ou dispensa registrada; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `scripts/windows/Invoke-OperationalPython.ps1` | compat temporaria | Wrapper fino para `ops/windows/scripts/Invoke-OperationalPython.ps1`. | Tarefas externas migradas para `ops/windows/scripts/`; docs Windows/self-hosted e comandos oficiais nao apontam mais para `scripts/windows/`; compatibilidade validada em fluxo Windows ou dispensa registrada; teste de compat atualizado ou removido no mesmo change. | depende de migracao |
| `.venv/` | local tolerado, potencialmente dispensavel | Ambiente Python local ignorado pelo Git; comandos de onboarding ainda podem usa-lo. | README, comandos oficiais e runbooks aceitam interpretador externo ou variavel padronizada; onboarding validado em checkout limpo sem `.venv` dentro da raiz; hygiene nao depende da presenca da pasta. | depende de migracao |
| `.vscode/` | local removivel | Configuracao local de editor ignorada pelo Git, sem papel oficial na topologia ou nos comandos canonicos. | Preferencias obrigatorias movidas para configuracao pessoal ou recomendacao neutra; nenhuma doc viva depende da pasta; se reaparecer, hygiene deve voltar a bloquea-la. | pode sair cedo |
| `legacy/` como container | ainda necessario por enquanto | Area documenta legado vivo ainda acoplado ao produto. | Todos os itens de `legacy/LIVE_LEGACY.md` migrados, removidos ou arquivados; testes e smoke/release nao exercem mais fluxo legado; docs vivas atualizadas; governanca confirma ausencia de consumidor. | ainda nao pode sair |
| `archive/repo-snapshots/frontend-*` | historico removivel | Snapshots de build/frontend de transicoes encerradas. | Nenhuma doc/runbook referencia os snapshots; nao ha auditoria, comparacao ou bug hunt pendente; `archive/MANIFEST.md` registra a remocao ou descarte do grupo. | depende de validacao adicional |
| `archive/temp-backups/root-wrapper-docs-backup-20260408-1635/` | historico removivel | Backup temporario de wrappers/docs antigos de raiz. | Docs vivas e wrappers canonicos validados como suficientes; nenhuma referencia interna aponta para o backup; `archive/MANIFEST.md` atualizado na mesma limpeza. | depende de validacao adicional |
| `archive/temp-backups/src-app-backup-20260408-154654/` | historico removivel | Backup temporario de arvore antiga de app. | Nenhuma auditoria pendente sobre a arvore antiga; backend atual e testes cobrem a funcao viva; `archive/MANIFEST.md` atualizado na mesma limpeza. | depende de validacao adicional |
| `archive/temp-backups/src-app-__init__-backup-20260408-1610.py` | historico removivel | Backup de arquivo antigo de inicializacao. | Nenhuma investigacao pendente sobre inicializacao antiga; inicializacao atual validada por testes relevantes; `archive/MANIFEST.md` atualizado na mesma limpeza. | depende de validacao adicional |
| `archive/temp-backups/nested-repo-copy-20260415/` | historico removivel | Copia aninhada preservada como backup temporario. | Ausencia comprovada de automacao externa apontando para a copia; ausencia de valor de auditoria pendente; impacto de espaco aceito; `archive/MANIFEST.md` atualizado na mesma limpeza. | depende de validacao adicional |
| `archive/old-wrappers/*.py` | historico removivel | Wrappers antigos fora da trilha viva. | Consumidores antigos migrados ou inexistentes; docs e runbooks apontam para `ops/` ou `backend/tools/maintenance/`; `scripts/README.md` cobre apenas a compat viva; `archive/MANIFEST.md` atualizado na mesma limpeza. | depende de validacao adicional |
| `archive/local-artifacts/.DS_Store` | removido em `31.4.2` | Artefato local macOS sem papel arquitetural, ausente apos limpeza fisica. | Se reaparecer, remover como residuo local e manter hygiene verde. | fechado; reaparecimento vira violacao local |

## Dependencias e bloqueadores

| item | bloqueio | impacto |
| --- | --- | --- |
| Wrappers em `scripts/` | Pode existir consumidor fora do repo: Task Scheduler, atalhos locais, servicos Windows ou rotina manual da equipe. | Remocao sem migracao quebra operacao antiga apesar da trilha canonica existir. |
| `.venv/` | Onboarding e comandos locais ainda podem presumir ambiente dentro da raiz. | Remocao prematura pode quebrar comandos copiados de docs ou habito local. |
| `.vscode/` | Nenhum bloqueio oficial restante; no maximo pode haver conveniencia local residual de editor. | Baixo risco operacional; se reaparecer, tratar como residuo local e nao como excecao oficial. |
| `legacy/` | `legacy/LIVE_LEGACY.md` ainda registra fluxo legado vivo. | Remover o container antes da migracao apagaria a fronteira entre legado vivo e nucleo. |
| `archive/repo-snapshots/*` e `archive/temp-backups/*` | Pode haver valor residual de auditoria, comparacao ou investigacao. | Remocao prematura perde contexto historico ainda nao substituido por docs vivas. |
| `archive/old-wrappers/*.py` | Podem ser referencia de migracao para entender aliases antigos. | Remocao sem checagem pode dificultar auditoria de transicao. |
| `archive/local-artifacts/.DS_Store` | Nenhum bloqueio operacional conhecido. | Fechado em `31.4.2`; se reaparecer, tratar como residuo local. |

## Validacao antes de remover

- Buscar referencias internas em docs, runbooks, workflows, scripts e testes; referencias permitidas apenas no backlog, manifest ou registro historico.
- Confirmar consumidor migrado ou ausencia comprovada de consumidor.
- Atualizar docs vivas e `archive/MANIFEST.md` quando a remocao afetar conteudo arquivado.
- Rodar hygiene e testes/smoke/release relevantes para o tipo removido.
- Registrar risco aceito quando a verificacao depender de consumidor externo ao repo.

## Validacao de pre-condicoes - 2026-04-15

Escopo desta revisao: wrappers e aliases antigos em `scripts/` classificados para saida futura. Nenhum item fica liberado apenas por nao aparecer como consumidor interno; uso de equipe, atalhos locais, servicos Windows e Task Scheduler precisam ser verificados antes da remocao fisica.

| item | docs | uso de equipe | ops/release/smoke | testes/validacoes | status final |
| --- | --- | --- | --- | --- | --- |
| `scripts/backup/run_backups.py` | Docs vivas apontam para `backend/tools/maintenance/run_backups.py`; o path antigo aparece apenas em docs de compat/backlog/checks. | Sem consumidor operacional conhecido no repo; uso externo ainda nao auditado. | Windows/self-hosted usa `ops/windows/scripts/Invoke-OperationalPython.ps1` com target canonico; release/smoke nao chama o path antigo. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | ainda nao pode remover |
| `scripts/database/run_db_consistency.py` | Docs vivas apontam para `backend/tools/maintenance/run_db_consistency.py`; o path antigo aparece apenas em compat/backlog/checks. | Sem consumidor operacional conhecido no repo; rotina manual externa ainda nao auditada. | Runbook e release gate apontam para trilhas canonicas; path antigo nao aparece como comando operacional vivo. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | depende de verificacao adicional |
| `scripts/jobs/run_jobs_worker.py` | Docs vivas apontam para `backend/tools/maintenance/run_jobs_worker.py`; o path antigo aparece apenas em compat/backlog/checks. | Sem consumidor operacional conhecido no repo; Task Scheduler/atalhos externos ainda nao auditados. | Windows/self-hosted usa target canonico para worker; release/smoke nao chama o path antigo. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | ainda nao pode remover |
| `scripts/jobs/run_notifications.py` | Docs vivas apontam para `backend/tools/maintenance/run_notifications.py`; o path antigo aparece apenas em compat/backlog/checks. | Sem consumidor operacional conhecido no repo; chamada externa ainda nao auditada. | `ops/` mantem implementacao despriorizada e backend/tools como entrada canonica; path antigo nao aparece como fluxo vivo. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | depende de verificacao adicional |
| `scripts/windows/Invoke-AppService.ps1` | Docs vivas apontam para `ops/windows/scripts/Invoke-AppService.ps1`; o path antigo aparece apenas em compat/backlog/checks. | Sem consumidor operacional conhecido no repo; servicos Windows/atalhos/Task Scheduler fora do repo ainda nao auditados. | Comando oficial de subida e docs Windows/self-hosted usam `ops/windows/scripts/Invoke-AppService.ps1`. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | ainda nao pode remover |
| `scripts/windows/Invoke-OperationalPython.ps1` | Docs vivas apontam para `ops/windows/scripts/Invoke-OperationalPython.ps1`; o path antigo aparece apenas em compat/backlog/checks. | Sem consumidor operacional conhecido no repo; tarefas agendadas fora do repo ainda nao auditadas. | Docs Windows/self-hosted usam `ops/windows/scripts/Invoke-OperationalPython.ps1` com targets canonicos em `backend/tools/maintenance/`. | `tests/unit/test_legacy_windows_compat.py` ainda exige o wrapper; suite relevante verde. | ainda nao pode remover |

### Alias fora da liberacao

`ops/scripts/backup/run_backups.py`, `ops/scripts/database/run_db_consistency.py`, `ops/scripts/jobs/run_jobs_worker.py` e `ops/scripts/jobs/run_notifications.py` nao estao liberados como aliases removiveis nesta revisao: `backend/tools/maintenance/*` ainda importa esses modulos como implementacao atual. Eles podem ser despriorizados como entrada direta, mas nao sao residuos mortos enquanto forem a implementacao chamada pela trilha canonica.

## Remocao fisica - 2026-04-15

Nenhum wrapper ou alias foi removido nesta etapa. A validacao de pre-condicoes nao liberou itens de `scripts/` para exclusao fisica: as docs vivas ja apontam para a trilha canonica, mas o uso externo de equipe/Task Scheduler/servicos Windows ainda nao foi auditado e `tests/unit/test_legacy_windows_compat.py` ainda protege a existencia dos shims.

| item | decisao | motivo |
| --- | --- | --- |
| `scripts/backup/run_backups.py` | manter bloqueado | Risco de job/atalho de backup externo e teste de compat ainda ativo. |
| `scripts/database/run_db_consistency.py` | manter bloqueado como `compat_residual_congelado` | Ausencia de consumidor externo/manual ainda nao comprovada e teste de compat ainda ativo. |
| `scripts/jobs/run_jobs_worker.py` | manter bloqueado | Possivel Task Scheduler/rotina externa e teste de compat ainda ativo. |
| `scripts/jobs/run_notifications.py` | manter bloqueado como `compat_residual_congelado` | Chamada externa/manual ainda nao auditada e teste de compat ainda ativo. |
| `scripts/windows/Invoke-AppService.ps1` | manter bloqueado | Possivel servico Windows/atalho externo e teste de compat ainda ativo. |
| `scripts/windows/Invoke-OperationalPython.ps1` | manter bloqueado | Possivel tarefa agendada externa e teste de compat ainda ativo. |

## Ordem sugerida de remocao

| prioridade | item | faixa de risco | razao da prioridade |
| --- | --- | --- | --- |
| 1 | `archive/local-artifacts/.DS_Store` | fechado | Removido fisicamente em `31.4.2`; nao permanece como pendencia ativa. |
| 2 | `.vscode/` | baixo | Configuracao local; pode sair depois de confirmar que preferencias obrigatorias estao fora da topologia viva. |
| 3 | `archive/temp-backups/src-app-__init__-backup-20260408-1610.py` | baixo | Backup pontual sem funcao operacional; exige apenas confirmar ausencia de investigacao de inicializacao. |
| 4 | `archive/temp-backups/root-wrapper-docs-backup-20260408-1635/` | baixo | Backup historico de docs/wrappers; nao executa produto e pode sair apos confirmar que docs vivas bastam. |
| 5 | `archive/old-wrappers/*.py` | medio | Nao esta na trilha viva, mas pode ajudar auditoria de migracao de aliases antigos. |
| 6 | `archive/repo-snapshots/frontend-*` | medio | Snapshots historicos sem operacao viva, mas ainda podem servir a comparacao ou auditoria. |
| 7 | `archive/temp-backups/src-app-backup-20260408-154654/` | medio | Backup de arvore antiga; sem operacao viva, mas com valor potencial de diff/auditoria. |
| 8 | `archive/temp-backups/nested-repo-copy-20260415/` | alto | Copia aninhada grande; precisa checar automacao externa e valor de auditoria antes de remover. |
| 9 | `.venv/` | medio | Local, mas ainda pode sustentar onboarding e comandos copiados de docs. |
| 10 | `scripts/database/run_db_consistency.py` | medio | Compat de diagnostico/manutencao; sai apenas depois de consumidor migrado ou ausencia comprovada. |
| 11 | `scripts/jobs/run_notifications.py` | medio | Compat de job auxiliar; risco controlado, mas ainda depende de confirmar chamadas externas. |
| 12 | `scripts/backup/run_backups.py` | alto | Compat de backup; nao deve sair antes de smoke/release de backup e migracao de consumidores. |
| 13 | `scripts/jobs/run_jobs_worker.py` | alto | Compat de worker; pode ter agendador externo e impacto operacional direto. |
| 14 | `scripts/windows/Invoke-OperationalPython.ps1` | alto | Compat Windows/self-hosted; pode estar em Task Scheduler ou servico fora do repo. |
| 15 | `scripts/windows/Invoke-AppService.ps1` | alto | Compat Windows/self-hosted de app service; remocao prematura pode quebrar operacao local/servico. |
| 16 | `legacy/` como container | alto | So pode sair quando todo legado vivo registrado for migrado, removido ou arquivado. |

## Faixas de risco

| item | faixa | justificativa |
| --- | --- | --- |
| `.vscode/`, backups pontuais sem consumidor e artefatos locais equivalentes | baixo | Nao participam da operacao oficial; a checagem principal e ausencia de referencia ou dependencia local obrigatoria. `.DS_Store` conhecido foi removido em `31.4.2`. |
| Snapshots, backups de arvore, `archive/old-wrappers/*.py`, `.venv/`, wrappers auxiliares de diagnostico/jobs | medio | Nao devem sair por estetica; exigem validacao documental, confirmacao de consumidor e, quando aplicavel, smoke/teste relevante. |
| Wrappers de backup, worker, Windows/self-hosted, copia aninhada e `legacy/` | alto | Podem ter consumidor externo, agendamento, valor de auditoria ou fluxo legado vivo; ficam no fim da fila. |

## Fora do backlog

| item | motivo |
| --- | --- |
| `backend/tools/maintenance/*` | Entradas canonicas de manutencao; nao sao compat temporaria. |
| `ops/scripts/*` | Camada operacional viva; remover exigiria decisao operacional especifica, nao limpeza geral. |
| `docs/operations/*` | Docs vivas e templates operacionais; seguem governanca documental, nao backlog fisico generico. |
| `legacy/domains/*` e `legacy/data-compat/*` | Ainda documentam legado vivo real; so entram em remocao quando `legacy/LIVE_LEGACY.md` for esvaziado por migracao real. |
| `archive/MANIFEST.md` e READMEs de `archive/` | Governam o conteudo arquivado; nao devem sair enquanto existir archive. |

## Hotspots

| item | impacto | severidade |
| --- | --- | --- |
| Wrappers em `scripts/` | Podem parecer caminho alternativo oficial se a compatibilidade ficar indefinida. | Alta |
| `.venv/` visivel | Polui leitura local da raiz e pesa no hygiene local, mas ainda sustenta onboarding. | Media |
| `.vscode/` visivel | Nao e mais excecao oficial; se reaparecer, volta a ser ruido estrutural e deve ser removido. | Baixa |
| `legacy/` sem codigo executavel movido | Pode parecer pasta estetica se os legados vivos forem resolvidos e o container permanecer. | Media |
| `archive/temp-backups/nested-repo-copy-20260415/` | Grande e contem arvore inteira; pode consumir espaco e confundir buscas manuais. | Alta |
| `archive/local-artifacts/.DS_Store` | Fechado em `31.4.2`; se reaparecer, tratar como residuo local. | Baixa |

## Atualizacao Frente 31

Esta atualizacao registra apenas status derivados de blocos ja executados da Frente 31. Ela nao autoriza remocao, nao cria bloco novo e nao muda a ordem de execucao definida em `docs/migration/31.2.0-matriz-blocos-executaveis-frente-31.md`.

### Refino de status 31.7.1

Este refino nao muda prioridade, nao antecipa remocao e nao transforma item P2 em P0 por redacao. `admin/routes.py:748>725` permanece baseline arquitetural conhecido fora do backlog fisico; `legacy/` permanece legado vivo enquanto houver itens ratificados em `legacy/LIVE_LEGACY.md`; artefatos locais tratados em `31.4.2` so voltam ao backlog se reaparecerem como violacao local.

| bloco | efeito no backlog | decisao |
| --- | --- | --- |
| `31.2.1-baseline-gates-estruturais` | artefatos locais gerados ficaram confirmados como baseline local vermelho de hygiene, sem limpeza naquele bloco. | pendencia rebaixada em `31.4.2-artefatos-locais-baixo-risco`; se reaparecer, tratar como violacao local. |
| `31.2.1-baseline-gates-estruturais` | `admin/routes.py:748>725` fica registrado como falha arquitetural conhecida, fora do backlog fisico. | nao tratar como remocao; corrigir apenas em bloco proprio de arquitetura/baseline, sem reabrir Frente 30. |
| `31.A-auditoria-contrato-fechamento` | `run_release_strict.py` fica reclassificado como gate de release operacional, nao como criterio geral de aceite da Frente 31. | manter registros anteriores como auditoria historica; fechamento da 31 passa a usar regua de governanca/compat/topologia. |
| `31.3.1-wrappers-alto-risco` | wrappers de backup, worker e Windows ficam como `compat_residual_congelado`; busca interna nao encontrou consumidor operacional vivo, mas consumidor externo nao foi auditado e ausencia objetiva nao foi comprovada. | manter bloqueado; remover apenas com prova de migracao/ausencia externa e teste de shim atualizado. |
| `31.3.2-wrappers-auxiliares` | wrappers de consistencia de banco e notificacoes ficam como `compat_residual_congelado`, porque consumidor externo/manual nao foi auditado e ausencia objetiva nao foi comprovada. | manter bloqueado; remover apenas com prova de migracao/ausencia externa/manual e teste de shim atualizado. |
| `31.4.1-archive-snapshots-risco-medio-alto` | snapshots, backups historicos, copia aninhada e old wrappers ficam historico legitimo congelado; `archive/temp-backups/nested-repo-copy-20260415/` nao e segunda raiz viva. | nao remover sem perda objetiva de valor de auditoria, ausencia de referencia, ausencia de consumidor externo quando aplicavel e atualizacao de `archive/MANIFEST.md`. |
| `31.4.2-artefatos-locais-baixo-risco` | residuos locais de baixo risco foram classificados como removiveis; `__pycache__` e bytecode fora de `.venv/`, `archive/` e `frontend/dist/` foram zerados; `.tmp`, `.vscode`, caches de tooling e `.DS_Store` local estavam ausentes nesta medicao. | hygiene verde apos limpeza; se reaparecer, tratar como violacao local. |
| `31.5.1-local-build-gerado` | `.venv/` e `frontend/dist/` ficam ratificados como excecoes locais geradas, nao fonte viva. | manter permitidos nos caminhos canonicos; nao entram como topologia oficial nem criterio arquitetural. |
| `31.6.1-legacy-vivo` | `legacy/` como container permanece necessario enquanto houver itens ratificados em `legacy/LIVE_LEGACY.md`. | nao remover; condicoes de saida por item foram ratificadas e feature nova em legacy ficou bloqueada. |
| `31.6.1-legacy-vivo` | `legacy/domains/*` e `legacy/data-compat/*` seguem fora do backlog fisico generico. | manter como legado vivo ate migracao real, evidencia material e teste da camada afetada. |

## Regra de uso

- Backlog nao e autorizacao de remocao.
- Remocao exige pre-condicao atendida, risco aceito e validacao do hygiene/testes relevantes.
- Item com consumidor operacional confirmado deve sair do backlog de remocao e voltar para compat, legacy ou operacao viva.
