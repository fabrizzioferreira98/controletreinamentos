# Checklist de Auditoria de Regressao

## Papel

Template vivo para auditoria de regressao por release. O gate oficial le este arquivo quando indicado por `docs/operations/canonical-commands.md`.

Preencha uma copia por release no diretorio externo de evidencias (`C:/srv-data/controle-treinamentos/<env>/evidence/<release_id>/`). Nao transforme este template em evidencia historica preenchida dentro de `docs/operations/`.

## Metadados
- Release ID: `<release_id>`
- Commit SHA: `<git_sha>`
- Ambiente: `<homolog|production>`
- Responsavel tecnico: `<nome ou automacao>`
- Data/hora: `<YYYY-MM-DD HH:MM:SS>`

## Checklist obrigatorio
- [ ] Paridade minima local/homolog/producao revisada contra `docs/operations/ENVIRONMENT_PARITY.md`.
- [ ] Contrato HTTP (401/403/500/CSRF) validado em navegacao e chamadas programaticas.
- [ ] Autenticacao e autorizacao (login, logout, permissao) validadas.
- [ ] Auth/cookies/origens do frontend validados no modo real do ambiente-alvo.
- [ ] CRUDs criticos validados ponta a ponta.
- [ ] Jobs (enqueue, worker, retry, dead-letter) validados.
- [ ] Worker ativo consumindo fila real e scheduler/cron equivalente validado ou explicitamente fora do escopo.
- [ ] Storage, uploads/downloads e PDFs validados em raiz real do ambiente.
- [ ] Notificacoes e integracoes externas validadas ponta a ponta ou explicitamente excluidas da evidencia.
- [ ] Massa minima canonica declarada e coerente com o ambiente-alvo.
- [ ] Backup/restore drill validado.
- [ ] Rollback drill validado (ida e volta).
- [ ] Carga autenticada validada dentro do SLO.
- [ ] Alertas externos validados ponta a ponta.
- [ ] Checklist de release preenchido no pacote externo do release.
- [ ] Checklist de rollback preenchido antes do deploy.
- [ ] Smoke pos-deploy validado.
- [ ] Gate final strict executado e anexado.
- [ ] Gate de release com evidencias operacionais em PASS.

## Evidencias anexadas
- Paridade minima entre ambientes: `<path externo>`
- Gate final strict: `<path externo>`
- Checklist de release: `<path externo>`
- Checklist de rollback: `<path externo>`
- E2E: `<path externo>`
- Carga autenticada: `<path externo>`
- Jobs concorrentes: `<path externo>`
- Scheduler/cron ou declaracao de escopo: `<path externo>`
- Storage/PDF/upload-download: `<path externo>`
- Alertas externos: `<path externo>`
- Backup/restore: `<path externo>`
- Rollback: `<path externo>`
- Smoke: `<path externo>`
- Smoke pos-release: `<path externo>`
- Manifest de evidencias: `<path externo>`

## Decisao
- Resultado: `<GO|GO CONDICIONAL|NO-GO>`
- Justificativa: `<resumo>`
- Riscos residuais: `<resumo ou nenhum>`
