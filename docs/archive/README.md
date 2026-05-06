# Arquivo de Documentacao

## Papel

Esta area guarda documentos historicos, auditorias encerradas, registros de transicao ja concluidos e artefatos documentais que nao sao fonte viva.

## Regra

- Nao usar como runbook, arquitetura vigente, comando oficial ou manual vivo.
- Nao apontar README, CI, release ou operacao para esta area como fonte de verdade.
- Mudancas aqui devem se limitar a preservacao historica, aviso de arquivo ou link para a doc viva correta.
- Esta area nao e retencao infinita: documento sem valor historico, auditoria ou referencia util pode ser removido em limpeza futura.

## Permanencia

- Fica quando explica decisao, migracao, auditoria encerrada ou contexto historico que ainda ajuda manutencao.
- Pode sair quando estiver duplicado, sem referencia viva e sem valor historico pratico.
- Nunca volta a ser doc viva por copia direta; conteudo util deve ser reconsolidado na area viva correta.

## Fonte viva

- Arquitetura: `docs/architecture/`
- Operacao: `docs/operations/`
- Governanca: `docs/governance/`
- Produto: `docs/product/`

## Conteudo atual

- Auditoria tecnica datada.
- Manuais unificados antigos.
- HTML consolidado gerado.
- Registros de fases da separacao frontend/backend.
- Modelo antigo de release gate consolidado em `docs/operations/RELEASE_GATES.md`.
- Checklist preenchido da release `release_20260330_233758`; a fonte viva e `docs/operations/REGRESSION_AUDIT_CHECKLIST.md`.
- PDF antigo de produto; a fonte viva e `docs/product/manual_usuario_operacional.md`.
- Relatorio historico da reorganizacao estrutural; as fontes vivas ficam em `docs/governance/`, `docs/operations/`, `docs/architecture/` e `docs/product/`.
