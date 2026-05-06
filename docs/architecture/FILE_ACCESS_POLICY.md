# File Access Policy

Esta politica governa preview, download e acesso binario a arquivos persistidos.
Ela complementa a politica de upload e persistencia sem alterar a camada de
storage.

## 1. Politica De Acesso

- Preview e download sao acoes distintas, mesmo quando usam o mesmo endpoint.
- Autorizacao e declarada por dominio e por acao antes de bytes serem enviados.
- Links atuais nao sao publicos nem assinados; o equivalente operacional e rota autenticada por sessao.
- Expiracao de link atual acompanha a sessao autenticada. Nao ha URL publica reutilizavel.
- Conteudo sensivel usa `Cache-Control: private, no-store`.
- Resposta binaria sempre declara `X-Content-Type-Options: nosniff`.
- Erro de blob ausente, vazio ou invalido nao deve virar resposta binaria vazia.
- Auditoria de acesso e emitida em log estruturado de aplicacao com usuario, request id, dominio, acao e entidade.

## 2. Permissoes Por Dominio

| Dominio | Preview | Download | Substituir | Excluir | Link |
| --- | --- | --- | --- | --- | --- |
| `tripulante_file` | `tripulantes_file:view` | `tripulantes_file:view` | `tripulantes_file:replace` | `tripulantes_file:delete` | autenticado por sessao |
| `tripulante_file_consolidated` | `tripulantes_file:view` | `tripulantes_file:view` | n/a | n/a | autenticado por sessao |
| `training_attachment` | `treinamentos_anexos:view` | `treinamentos_anexos:view` | n/a | `treinamentos_anexos:delete` | autenticado por sessao |
| `tripulante_photo` | `tripulantes:view` ou `relatorio_individual:view` | mesma permissao, sem link de download dedicado | `tripulantes:edit` | `tripulantes:edit` | autenticado por sessao |

## 3. Fluxos Priorizados

- API de documento File: `GET /api/v1/tripulantes/{id}/files/{file_id}`.
- SSR de documento File: `GET /tripulantes/{id}/file/{file_id}`.
- Aba File consolidada: `GET /tripulantes/{id}/file/origem/{origem}/{file_id}`.
- API de anexo de treinamento: `GET /api/v1/treinamentos/{id}/attachments/{attachment_id}`.
- SSR de anexo de treinamento: `GET /treinamentos/{id}/anexos/{attachment_id}`.
- Foto de tripulante: endpoints API e SSR de foto.

## 4. Streaming, Cache E Headers

- Resposta binaria e entregue por iterador em chunks, com `Content-Length` calculado.
- `download=1`, `download=true`, `download=yes` e `download=sim` resolvem acao `download`; demais acessos resolvem `preview`.
- PDF em preview recebe `Content-Disposition: inline`; download recebe `attachment`.
- Fotos sao sempre preview no fluxo atual e nao recebem `Content-Disposition`.
- Cabecalhos `X-File-Access-Action`, `X-File-Link-Policy` e `X-File-Link-Expires` tornam a politica visivel ao cliente.

## 5. Compatibilidade

- URLs existentes continuam funcionando.
- `?download=1` continua forcando download.
- Permissao de download continua igual a permissao de visualizacao por compatibilidade, mas agora e declarada separadamente.
- URLs assinadas ficam adiadas ate existir storage remoto documental ativo ou necessidade de link publico temporario.
