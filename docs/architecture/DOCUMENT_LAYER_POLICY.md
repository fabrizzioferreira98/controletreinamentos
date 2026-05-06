# Document Layer Policy

Fonte oficial da frente 20 para storage, arquivos e PDFs. Esta politica
consolida upload, persistencia, acesso, PDFs e riscos classicos em uma regra
unica de operacao documental.

## 1. Decisao estrutural

- Arquivo/documento e sempre composto por conteudo binario, metadata, referencia persistida, politica de acesso e ciclo de vida.
- Metadata nao prova existencia de blob; blob nao tem valor documental sem metadata confiavel.
- `storage_ref` e a referencia persistida oficial. `fs:` aponta para filesystem local e `db:bytea` e legado compativel.
- Referencia remota documental (`s3://` ou `remote:`) fica reconhecida, mas indisponivel para leitura ate existir adapter documental dedicado.
- Nome original e metadata de exibicao. Identidade estrutural usa id de dominio, hash, status, referencia e nome fisico opaco.
- PDFs e documentos de evidencia sao registros de dominio; nao sao apenas binarios.

## 2. Naming, paths e referencias

- Novas escritas locais usam helpers de dominio; fluxo nao monta path livremente.
- `tripulante_document`: `fs:tripulantes/tripulante-{tripulante_id}/documentos/{nome_fisico}`.
- `training_attachment`: `fs:treinamentos/treinamento-{treinamento_id}/anexos/{nome_fisico}`.
- `tripulante_photo`: `fs:tripulantes/tripulante-{tripulante_id}/fotos/{nome_fisico}`.
- Nome fisico deve ser opaco, seguro e sem dependencia do nome original.
- Referencia `fs:` nova precisa bater exatamente com a politica do dominio; traversal, separador Windows, byte nulo, nesting indevido e prefixo errado sao invalidos.
- Referencias `fs:` legadas continuam legiveis quando permanecem sob a raiz operacional e sem traversal.

## 3. Metadata, blob e consistencia

- Metadata minima de PDF persistido: `nome_original`, `nome_interno`, `mime_type`, `tamanho_bytes`, `arquivo_hash`, `storage_ref`, `status`, `enviado_por`, `enviado_em`.
- Novas escritas `fs:` nao duplicam bytes em `arquivo_pdf`.
- `arquivo_pdf` so e fonte de blob quando `storage_ref = 'db:bytea'`.
- Estados oficiais: `consistent`, `consistent_legacy`, `metadata_without_blob`, `metadata_without_reference`, `remote_reference_unverified`, `metadata_with_unsupported_reference`, `orphan_blob`.
- Metadata inconsistente deve aparecer em contrato, inventario ou monitoramento; nao deve ser mascarada por fallback binario.

## 4. Preview, download, autorizacao e cache

- Preview e download sao acoes distintas.
- Decisao atual: preview e download continuam com a mesma permissao por compatibilidade nos dominios existentes.
- Esta igualdade e decisao consciente, nao omissao. A politica ja declara permissoes separadas por acao.
- Condicao para divergir no futuro: conteudo sensivel exigir download mais restrito que visualizacao, link publico temporario, assinatura, ou auditoria regulatoria mais forte.
- Arquivos persistidos sensiveis usam `Cache-Control: private, no-store`.
- PDFs gerados usam `Cache-Control: no-store`.
- Resposta binaria usa `X-Content-Type-Options: nosniff`.
- Links atuais sao rotas autenticadas por sessao; expiracao acompanha a sessao. URLs assinadas ficam fora do escopo atual.

## 5. Retencao, versionamento e exclusao

- `tripulante_file`: replace cria novo registro ativo e marca o anterior como `substituido`; blob historico e retido.
- `training_attachment`: anexo e append-only; exclusao individual e soft delete; blob fica retido enquanto governado pelo registro.
- `tripulante_photo`: troca substitui foto corrente; blob anterior e removido apos commit.
- `pdf_export`: gerado sob demanda, nao persistido, versionamento `rendered_snapshot_at_request`, retencao `not_persisted`.
- Hard delete fisico so ocorre em falha de nova escrita, troca/remocao de foto apos commit, ou exclusao governada do dominio pai.

## 6. Rotina operacional de orfaos

- Inventariar metadata documental de `treinamento_anexos_pdf`, `tripulante_arquivos_pdf` e referencias de foto.
- Inventariar blobs locais sob `MEDIA_STORAGE_ROOT`.
- Classificar:
  - `metadata_without_blob`: investigar origem; reconciliar se houver blob recuperavel; manter metadata se houver valor historico; nao servir.
  - `blob_without_metadata`/`orphan_blob`: investigar se e sobra de falha, replace, delete ou migracao; manter por retencao quando houver duvida documental; remover apenas com decisao governada.
  - `metadata_without_reference`: corrigir metadata se houver fonte confiavel; caso contrario manter bloqueado e sinalizado.
  - `metadata_with_unsupported_reference`: bloquear leitura e corrigir referencia ou migrar.
  - `remote_reference_unverified`: manter indisponivel ate adapter remoto existir.
  - sobra de replace: manter se representar versao historica; remover apenas se comprovadamente falha de escrita sem metadata valida.
  - PDF/documento gerado sem governanca: nao persistir como evidencia; se precisar virar evidencia, reentrar por fluxo de documento persistido.
- Remocao governada exige inventario, classificacao, decisao registrada, dry-run quando aplicavel e execucao restrita ao escopo aprovado.
- Nao executar limpeza destrutiva ampla sem janela propria.

## 7. PDFs e governanca documental

- `pdf_export`: relatorios e exports gerados; nao sao evidencia persistida.
- `pdf_evidence`: PDF enviado ou armazenado que sustenta fato de dominio; exige hash, metadata/blob consistentes, retencao e acesso governados.
- `temporary_document`: documento gerado para consumo operacional, sem persistencia como evidencia.
- `signed_document`: capacidade reservada; nenhum fluxo atual deve inferir assinatura por nome, MIME ou extensao.
- PDF gerado deve ter `%PDF`, marcador `%%EOF`, contrato visual oficial, `application/pdf`, `no-store`, `nosniff` e headers `X-Document-*`.

## 8. Adapter remoto documental

- Decisao: nao implementar adapter remoto documental agora.
- Motivo: a camada atual serve documentos locais e legado `db:bytea`; nao existe requisito operacional aprovado para link publico, URL assinada ou leitura remota documental.
- Impacto atual: `s3://` e `remote:` sao metadata reconhecida e nao servida; isso evita fingir disponibilidade do blob.
- Backlog formal: implementar adapter remoto somente quando houver provedor definido, politica de credenciais, URL assinada/expiracao, auditoria de acesso, reconciliacao metadata/blob remota e testes de indisponibilidade.

## 9. Documento assinado reservado

- Documento assinado e arquivo cujo valor documental depende de identidade do assinante, integridade, timestamp e verificacao.
- Exige trilha mais forte quando usado como prova formal, aceite, autorizacao, termo, certificado ou evidencia regulatoria.
- Relacao com evidencia: todo documento assinado e evidencia, mas nem toda evidencia e documento assinado.
- Relacao com versionamento: nova assinatura ou alteracao de conteudo cria nova versao; versao assinada nao deve ser sobrescrita.
- Relacao com armazenamento/download: deve manter hash, dados de assinatura, signer, timestamp, politica de retencao e auditoria de preview/download.
- Estado atual: reservado para contrato futuro; nao ha fluxo ativo aceito como assinado.

## 10. Aderencia atual e divida controlada

- Aderente: upload de PDFs, fotos, storage local novo, preview/download autenticado, PDF exportado, metadata/blob classification e monitoramento de risco documental.
- Parcial: rotina de orfaos existe como regra e classificacao, mas limpeza governada ainda nao foi implementada como comando operacional.
- Backlog: adapter remoto documental, documento assinado, migracao de `db:bytea`, validacao PDF estrutural profunda, possivel separacao futura entre permissao de preview e download.
