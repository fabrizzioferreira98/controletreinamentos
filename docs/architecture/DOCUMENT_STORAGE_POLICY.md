# Document Storage Policy

Esta politica governa a separacao entre metadata, blob binario e referencia
interna para documentos e PDFs. Ela preserva leitura de legado `db:bytea`, mas
define `fs:` como caminho canonico para novas escritas.

## 1. Mapa Real

- Tripulante File -> metadata em `tripulante_arquivos_pdf` -> blob novo em filesystem, blob legado em `arquivo_pdf` -> reference em `storage_ref`.
- Anexo de treinamento -> metadata em `treinamento_anexos_pdf` -> blob novo em filesystem, blob legado em `arquivo_pdf` -> reference em `storage_ref`.
- Foto de tripulante -> metadata no cadastro do tripulante -> blob novo em filesystem, base64 legado em `foto_base64` -> reference em `foto_storage_ref`.
- Download/preview -> busca metadata autorizada, resolve `storage_ref`, e so usa `arquivo_pdf` quando a reference e `db:bytea`.

## 2. Problemas Estruturais

- `arquivo_pdf` ainda recebia bytes em novas escritas `fs:` -> evidência: inserts de documentos e anexos gravavam `payload["arquivo_pdf"]` -> severidade alta.
- Blob ausente podia ser mascarado por fallback binario -> evidência: leitura aceitava fallback junto com `storage_ref` -> severidade alta.
- Anexo de treinamento era hard deleted apesar de possuir `status` -> evidência: `DELETE FROM treinamento_anexos_pdf` no delete individual -> severidade alta.
- Exclusao do treinamento pai removia metadata por cascade sem limpar blobs em um fluxo -> evidência: `delete_treinamento` nao coletava anexos antes do delete -> severidade media.

## 3. Modelo Normalizado

- Banco -> guarda metadata documental: dono, nome exibido, nome fisico, mime, tamanho, hash, status, usuario, timestamps e `storage_ref`.
- Storage/filesystem -> guarda o conteudo binario novo dos documentos e PDFs.
- `arquivo_pdf` -> coluna legada, usada apenas quando `storage_ref = 'db:bytea'`.
- Ligacao -> `storage_ref` e a referencia persistida; `fs:` aponta para blob em storage e `db:bytea` aponta para blob legado no banco.
- Disponibilidade -> metadata exposta pode carregar `blob_storage`, `blob_available` e `blob_status`.
- Contrato -> metadata exposta tambem carrega `blob_policy` para deixar claro que `arquivo_pdf`/`db:bytea` sao compat residual, nao owner normal.

## 4. Replace / Delete / Soft Delete / Versionamento

- Upload novo -> escreve blob primeiro, grava metadata depois; falha de metadata remove o blob recem-criado.
- Replace de Tripulante File -> cria nova metadata e novo blob; registro anterior vira `substituido`; blob anterior fica preservado como versao historica.
- Delete de Tripulante File -> soft delete; metadata fica `removido`, blob fica retido e download e bloqueado.
- Delete de anexo de treinamento -> soft delete; metadata fica `removido`, blob fica vinculado e download/lista ativa bloqueiam o item.
- Delete do treinamento pai -> hard delete do dominio pai; blobs de anexos sao coletados antes e removidos depois do commit.

## 5. Mudancas Aplicadas

- `core/document_storage.py` define tipo de referencia, persistencia de blob e estado documental.
- `infra/document_blobs.py` centraliza leitura e anotacao de disponibilidade do blob.
- Repositorios deixam de gravar `arquivo_pdf` para novas refs `fs:`.
- Anexos de treinamento ganham soft delete com `removido_por`, `removido_em` e `motivo_status`.
- Contratos passam a expor estado de blob sem transformar `storage_ref` em URL publica.
- 18.FIX.4 formaliza `arquivo_pdf` e `foto_base64` como residuais congelados, com leitura legado isolada e escrita nova bloqueada por policy/teste.

## 6. Validacao

- Nova escrita `fs:` -> `arquivo_pdf` persiste `NULL`.
- Legado `db:bytea` -> `arquivo_pdf` continua sendo lido.
- `fs:` ausente -> download falha; fallback binario nao mascara ausencia do blob.
- Contratos de documento/anexo expõem `blob_policy.legacy_write = blocked_new_writes` e `blob_policy.legacy_read = isolated_fallback`.
- Anexo removido -> sai das listas ativas e nao e baixado.
- Treinamento pai excluido -> blobs dos anexos sao removidos apos commit.

## 7. Divida Adiada

- Migrar bytes legados `db:bytea` para filesystem canonico.
- Criar rotina transacional/outbox para retry de limpeza fisica apos hard delete de dominio pai.
- Inventariar orfaos e referencias quebradas de forma recorrente.
- Versionamento formal para anexos de treinamento, caso passe a existir replace nesse dominio.
