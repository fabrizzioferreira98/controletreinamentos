# Observabilidade de Produção

## Logs estruturados
- Todo request agora gera evento JSON `http_request` com:
  - `request_id`
  - `method`
  - `path`
  - `endpoint`
  - `status`
  - `duration_ms`
  - `user_id`
- Respostas incluem header `X-Request-ID` para correlação entre frontend, backend e incidentes.

## Métricas mínimas
- Endpoint interno: `GET /api/internal/metrics`
- Segurança:
  - se `METRICS_TOKEN` estiver configurado, enviar `X-Metrics-Token`.
- Métricas expostas:
  - `requests_total`
  - `status_2xx/3xx/4xx/5xx`
  - `total_duration_ms`
  - `avg_duration_ms`

## Alertas obrigatórios
- Disponibilidade HTTP < 99.0% em janela de 5 min.
- `status_5xx` acima de baseline por 10 min.
- `avg_duration_ms` > 800ms por 10 min.
- Fila de jobs com `dead_letter > 0`.
- `stale_running > 0` no monitoramento de jobs.

## Rastreio de erro
- Todo erro 500 deve conter `request_id` no payload JSON (API/Ajax).
- Toda investigação deve iniciar por `request_id` + timestamp aproximado + endpoint.
