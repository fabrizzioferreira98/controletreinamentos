# Storage Naming Policy

Esta politica governa novos nomes fisicos de arquivos, nomes exibidos ao usuario
e referencias internas de storage. Ela nao redefine registros legados ja
persistidos: referencias antigas continuam legiveis enquanto existirem no banco.

## 1. Estado Atual

- Fotos de tripulante/piloto -> antes usavam `tripulantes/{id-slug}/foto/{uuid}.{ext}` -> o path carregava nome de pessoa e mudava semanticamente quando o nome era alterado.
- PDFs da aba File -> antes usavam `tripulantes/{id-slug}/documentos/{uuid}_{nome_original}.pdf` -> o nome exibido participava do nome fisico.
- Anexos de treinamento -> antes usavam `tripulantes/{id-slug}/treinamentos/{treinamento_id}/{uuid}_{nome_original}.pdf` -> misturava dominio de tripulante com dominio de treinamento.
- Referencias internas -> seguem como `fs:{relative_path}` -> a referencia e tecnica, nao URL publica.
- Nomes exibidos -> ficam em `nome_original` -> devem continuar orientados ao usuario, nao ao storage.

## 2. Policy Proposta

- Nome fisico -> opaco, sem nome do usuario, sem path recebido, com prefixo de dominio e token unico.
- Nome exibido -> valor sanitizado de upload, guardado como metadata em `nome_original`.
- Referencia interna -> `fs:` com caminho relativo canonico por dominio.
- Tripulante/foto -> `fs:tripulantes/tripulante-{id}/fotos/foto-{uuid}.{ext}`.
- Tripulante/documento -> `fs:tripulantes/tripulante-{id}/documentos/documento-{uuid}.pdf`.
- Treinamento/anexo -> `fs:treinamentos/treinamento-{id}/anexos/anexo-{uuid}.pdf`.
- Compatibilidade -> qualquer `fs:` antigo continua resolvido por `storage_ref_to_path`.

## 3. Hotspots

- `nome_interno` de PDF -> risco: virar nome bonito por acidente -> impacto: path sensivel e colisao sem politica.
- slug de tripulante no path -> risco: drift apos rename -> impacto: paths inconsistentes e suporte confuso.
- anexo de treinamento dentro da pasta de tripulante -> risco: fronteira de dominio ambigua -> impacto: migracao, busca e retencao mais dificeis.
- `storage_ref` em contratos -> risco: consumidor tratar como URL/contrato publico -> impacto: troca futura de storage fica mais cara.

## 4. Mudancas Aplicadas

- `core/storage_naming.py` centraliza nomes fisicos canonicos e validacao de nome fisico.
- `infra/media_storage.py` grava novas fotos, documentos e anexos em paths canonicos.
- `service_layers/pure_validation.py` passa a gerar `nome_interno` opaco por dominio.
- Testes cobrem escrita canonica, leitura de referencias antigas e separacao entre nome exibido e nome fisico.

## 5. Compatibilidade / Legado

- `fs:tripulantes/{id-slug}/foto/...` -> manter leitura, congelar como legado.
- `fs:tripulantes/{id-slug}/documentos/...` -> manter leitura, migrar apenas em rotina controlada.
- `fs:tripulantes/{id-slug}/treinamentos/{id}/...` -> manter leitura, migrar apenas em rotina controlada.
- `db:bytea` e `foto_base64` -> manter fallback, congelar para novas escritas.
- `nome_original` -> manter como metadata de exibicao.
- `nome_interno` -> migrar para nome fisico opaco em novas escritas.

## 6. Validacao

- Upload de PDF da aba File -> `nome_original` preserva exibicao sanitizada e `nome_interno` vira `documento-{uuid}.pdf`.
- Upload de anexo de treinamento -> `nome_interno` vira `anexo-{uuid}.pdf`.
- Escrita de foto -> referencia passa para `tripulantes/tripulante-{id}/fotos/foto-{uuid}.{ext}`.
- Leitura de storage legado -> `read_media_bytes` continua abrindo `fs:` antigo.
- Nome fisico com `../` ou separador de path -> rejeitado antes de gravar.

## 7. Divida Adiada

- Remover `storage_ref` dos contratos publicos.
- Migrar fisicamente arquivos legados para paths canonicos.
- Alinhar hard delete de anexos de treinamento com politica documental de soft delete.
- Criar inventario recorrente de orfaos e referencias quebradas.
