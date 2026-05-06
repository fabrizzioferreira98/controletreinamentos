# Upload Policy

Esta politica governa a entrada de arquivos em API, SSR legado e fluxos novos.
Ela complementa as politicas de storage: storage diz onde o blob fica; upload
diz o que pode entrar.

## 1. Politica Transversal

- Validacao exige contexto: extensao, MIME declarado, assinatura de conteudo e limite de tamanho precisam bater com o dominio.
- Extensao sozinha nunca aprova arquivo.
- MIME sozinho nunca aprova arquivo.
- Nome original e apenas metadata exibivel; identidade estrutural usa hash, id do dominio e nome fisico opaco.
- MIME ausente ou `application/octet-stream` e aceito apenas como compatibilidade quando o conteudo real passa na validacao do dominio.
- Metadados minimos de PDF: `nome_original`, `nome_interno`, `mime_type`, `tamanho_bytes`, `arquivo_hash`, `storage_ref`, `status`, `enviado_por`, `enviado_em`.
- Autorizacao de upload precisa estar explicita no endpoint antes de chamar o caso de uso.
- Deduplicacao e regra de dominio, nao efeito colateral de nome ou storage.

## 2. Politica Por Dominio

| Dominio | Tipo aceito | MIME aceito | Tamanho | Permissao | Deduplicacao |
| --- | --- | --- | --- | --- | --- |
| `tripulantes.file` | `.pdf` | `application/pdf` | `TRIPULANTE_FILE_MAX_MB` | `tripulantes_file:create` | rejeita hash ativo igual no mesmo tripulante |
| `treinamentos.anexos` | `.pdf` | `application/pdf` | `TRAINING_ATTACHMENT_MAX_MB` | `treinamentos_anexos:create` | rejeita hash ativo igual no mesmo treinamento |
| `treinamentos.programa.evidencias` | `.pdf` | `application/pdf` | `TRAINING_ATTACHMENT_MAX_MB` | `treinamentos:create` + `treinamentos_anexos:create` quando houver arquivo | rejeita hash ativo igual no mesmo treinamento |
| `tripulantes.foto` | `.jpg`, `.jpeg`, `.png`, `.webp` | `image/jpeg`, `image/png`, `image/webp` | `MAX_PHOTO_BYTES` | `tripulantes:edit` | substitui foto corrente |

## 3. Fluxos Priorizados

- API `POST /api/v1/tripulantes/<id>/files`: multipart e JSON/base64 para documentos do tripulante.
- SSR `/tripulantes/<id>/file/upload` e `/substituir`: upload multiplo e replace de documento PDF.
- API/SSR de `treinamentos/<id>/attachments`: anexo PDF de treinamento.
- Batch `POST /api/v1/treinamentos-tripulantes/batch`: evidencias PDF em JSON/base64, com permissao adicional quando houver arquivo.
- Foto de tripulante: data URI de imagem, validado por MIME declarado e assinatura real.

## 4. Hotspots Controlados

- `service_layers/upload_policy.py` declara a politica oficial.
- `service_layers/pure_validation.py` aplica a politica transversal para PDFs e imagens.
- Casos de uso de `tripulante_media`, `treinamentos` e `training_program` sanitizam nome efetivo antes de persistir metadata.
- Repositorios mantem hash, nome interno opaco e status para deduplicacao e auditoria.

## 5. Compatibilidade

- `application/octet-stream` e MIME ausente continuam aceitos para clientes legados, mas somente quando extensao e conteudo real sao validos.
- Registros antigos em `db:bytea` e `fs:` legado continuam legiveis pela politica de storage.
- Hints do frontend podem continuar conservadores; o backend e a autoridade final da politica.
