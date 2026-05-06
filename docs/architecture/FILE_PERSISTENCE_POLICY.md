# File Persistence Policy

Esta politica governa onde blobs documentais vivem, como sao referenciados e
como inconsistencias metadata/blob devem ser classificadas. Ela preserva leitura
de legado, mas torna novas escritas previsiveis.

## 1. Politica Estrutural

- Metadata nao prova existencia de blob; todo `fs:` precisa resolver para arquivo fisico antes de ser servido.
- Blob novo nao deve ser persistido em banco quando `storage_ref` aponta para filesystem.
- `db:bytea` e legado hibrido congelado: metadata e blob ficam no banco e continuam legiveis apenas quando a referencia e exatamente `db:bytea`; novas escritas ficam bloqueadas.
- `foto_base64` e snapshot residual de foto; leitura so existe como fallback isolado quando `foto_storage_ref` nao resolve blob servivel.
- Referencia remota documental (`s3://` ou `remote:`) e reconhecida como remota, mas nao e servida pela camada documental atual sem adapter dedicado.
- Path novo e sempre gerado por helper de dominio; fluxos nao montam caminho livremente.
- Nome fisico e opaco; nome original e metadata de exibicao.
- Exclusao fisica so ocorre em falha de nova escrita, troca/remocao de foto apos commit ou hard delete governado do dominio pai.
- Soft delete e substituicao mantem blob e metadata para rastreabilidade.

## 2. Mapa Real De Storage

| Fluxo | Storage atual | Referencia | Blob | Retencao |
| --- | --- | --- | --- | --- |
| Tripulante File | local filesystem para novas escritas | `fs:tripulantes/tripulante-{id}/documentos/{nome}` | arquivo em `MEDIA_STORAGE_ROOT` | ativo/substituido/removido retidos |
| Anexo de treinamento | local filesystem para novas escritas | `fs:treinamentos/treinamento-{id}/anexos/{nome}` | arquivo em `MEDIA_STORAGE_ROOT` | soft delete retido; delete do treinamento remove apos commit |
| Foto de tripulante | local filesystem para novas escritas | `fs:tripulantes/tripulante-{id}/fotos/{nome}` | arquivo em `MEDIA_STORAGE_ROOT` | foto anterior removida apos commit |
| Legado PDF | banco | `db:bytea` | coluna `arquivo_pdf` | retido por compatibilidade |
| Legado foto | banco/base64 | `foto_base64` sem `fs:` | coluna de tripulante | congelado para leitura |
| Remoto documental | nao ativo | `s3://`/`remote:` | nao lido pela camada documental | adapter futuro |
| Remoto backup | S3 operacional | configuracao `BACKUP_S3_*` | artefatos de backup | retencao de backup, fora da camada documental |

## 3. Politicas Por Dominio

- `tripulante_document`: path canonico `tripulantes/tripulante-{tripulante_id}/documentos/`; replace cria novo registro e marca o anterior como `substituido`.
- `training_attachment`: path canonico `treinamentos/treinamento-{treinamento_id}/anexos/`; anexos sao append-only e exclusao individual e soft delete.
- `tripulante_photo`: path canonico `tripulantes/tripulante-{tripulante_id}/fotos/`; troca substitui a foto corrente e remove o blob antigo apos commit.
- `remote_document`: referencia reconhecida, indisponivel para leitura ate existir adapter remoto documental.

## 4. Consistencia Metadata/Blob

- `consistent`: metadata aponta para blob local existente.
- `consistent_legacy`: metadata `db:bytea` possui blob no banco.
- `metadata_without_blob`: metadata existe, mas blob local/legado nao existe.
- `metadata_without_reference`: metadata nao tem referencia de storage.
- `remote_reference_unverified`: metadata aponta para remoto sem adapter documental ativo.
- `metadata_with_unsupported_reference`: referencia desconhecida.
- `orphan_blob`: blob local existe, mas nao aparece em metadata conhecida.

## 5. Compatibilidade

- `fs:` antigo continua legivel se estiver sob a raiz de storage e sem traversal.
- `db:bytea` continua legivel, mas novas escritas `fs:` nao duplicam blob em `arquivo_pdf`.
- Referencias remotas nao sao servidas por fallback local ou banco; isso evita metadata fingir disponibilidade.

## 6. Congelamento 18.FIX.4

| Residual | Owner canonico | Escrita nova | Leitura residual | Saida futura |
| --- | --- | --- | --- | --- |
| `tripulantes.foto_base64` | `tripulantes.foto_storage_ref` | bloqueada; writers vivos salvam em storage e limpam o legado | `application/tripulante_media.py::load_tripulante_photo_payload`, acionado apenas como fallback | migrar/limpar linhas com base64 residual e remover fallback/coluna em migracao dedicada |
| `tripulante_arquivos_pdf.arquivo_pdf` | `tripulante_arquivos_pdf.storage_ref` | bloqueada por `database_blob_for_persistence(..., allow_legacy_database_blob=False)` | `infra/document_blobs.py` apenas quando `storage_ref = 'db:bytea'` | migrar blobs restantes para `fs:` e remover fallback/coluna em migracao dedicada |
| `treinamento_anexos_pdf.arquivo_pdf` | `treinamento_anexos_pdf.storage_ref` | bloqueada por `database_blob_for_persistence(..., allow_legacy_database_blob=False)` | `infra/document_blobs.py` apenas quando `storage_ref = 'db:bytea'` | migrar anexos restantes para `fs:` e remover fallback/coluna em migracao dedicada |

Contratos devem expor `compat_residual`, `compat_source` e `blob_policy`/`photo_policy` quando o item toca legado. O campo legado nunca volta a ser tratado como fonte normal, URL publica ou owner de disponibilidade.
