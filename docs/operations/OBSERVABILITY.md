# Observabilidade de Produção

## Logs estruturados
- Todo request agora gera evento JSON `http_request` com:
  - `request_id`
  - `correlation_id`
  - `method`
  - `path`
  - `endpoint`
  - `status`
  - `duration_ms`
  - `user_id`
- Respostas incluem header `X-Request-ID` para correlação entre frontend, backend e incidentes.
- Respostas incluem header `X-Correlation-ID` para encadear multiplos requests do mesmo fluxo operacional.

## Correlacao minima
- Frontend envia `X-Request-ID` por chamada e reaproveita `X-Correlation-ID` por sessao de navegador.
- Backend aceita `X-Request-ID` e `X-Correlation-ID`, devolve ambos nos headers e injeta ambos nos logs JSON.
- Erros de API retornam `request_id` e `correlation_id`; `/api/internal/errors/<request_id>` preserva a correlacao capturada.
- Jobs gravam `origin_request_id` e carregam `correlation_id` no payload interno `_trace`; logs de enqueue, start, success/fail e worker usam o mesmo par.
- Release gate registra `release_id` e `correlation_id` nos logs do wrapper e propaga o par ao motor interno.
- Runtime pode receber `APP_RELEASE_ID`; startup, request log e evento de erro passam a expor esse release para correlacionar incidente com versao promovida.

## Métricas mínimas
- Endpoint interno: `GET /api/internal/metrics`
- Segurança: `METRICS_TOKEN` deve estar configurado e a coleta deve enviar `X-Metrics-Token`.
- HTTP técnico:
  - `http_requests_total{method,endpoint,status}`
  - `http_request_duration_seconds{method,endpoint}`
- Auth técnico:
  - `auth_events_total{outcome,channel}`
- Jobs e worker:
  - `background_job_executions_total{job_type,status}`
  - `background_job_duration_seconds{job_type,status}`
  - `background_job_queue_backlog{state}`
  - `background_job_oldest_queued_seconds`
  - `background_worker_cycles_total{status}`
- PDF:
  - `pdf_generations_total{renderer,status}`
  - `pdf_generation_duration_seconds{renderer,status}`
  - `pdf_generation_size_bytes{renderer,status}`
  - `pdf_document_responses_total{policy,kind,status}`
- Upload, download e storage:
  - `file_access_responses_total{policy,action,source,status}`
  - `file_access_response_duration_seconds{policy,action,source,status}`
  - `file_access_response_size_bytes{policy,action,source,status}`
  - `storage_operations_total{operation,policy,status}`
  - `storage_operation_duration_seconds{operation,policy,status}`
  - `storage_transfer_size_bytes{operation,policy,status}`
- Fluxos críticos:
  - `critical_flow_failures_total{flow,reason}`
  - `critical_flow_duration_seconds{flow,status}`
- Recursos e ambiente:
  - `runtime_process_memory_bytes{kind}`
  - `runtime_process_cpu_percent`
  - `runtime_disk_usage_percent{scope}`
  - `runtime_resource_metrics_available{collector}`
  - `runtime_environment_signal{app_env,database_configured,metrics_token_configured,sentry_configured}`

Essas métricas são técnicas. Indicadores de negócio, como totais de treinamentos,
tripulantes ou vencimentos, continuam no dashboard operacional e não substituem
os sinais de latência, erro, fila, throughput e recurso.

## Sinais mínimos por ambiente
- `development`: endpoint protegido por token quando habilitado, HTTP, auth, geração de PDF, storage local, fila local e recurso do processo.
- `homolog`/`staging`: todos os sinais de `development`, mais backlog de jobs, falha por fluxo crítico, backup e disco de `instance`.
- `production`: todos os sinais de `homolog`, com alerta ativo para 5xx, latência, dead letter, stale running, falhas de backup/storage/PDF e uso de disco/processo.

## Alertas obrigatórios
- Disponibilidade HTTP < 99.0% em janela de 5 min.
- `http_requests_total` com status 5xx acima de baseline por 10 min.
- P95 de `http_request_duration_seconds` > 800ms por 10 min nos endpoints críticos.
- `background_job_queue_backlog{state="dead_letter"} > 0`.
- `background_job_queue_backlog{state="stale_running"} > 0`.
- Falha em `critical_flow_failures_total` para `backup`, `storage:*`, `pdf_generation:*` ou `background_job:*`.
- Surto de autenticacao acima de `AUTH_FAILURE_ALERT_THRESHOLD` na janela configurada.
- Falhas repetidas em contrato/integracao a partir de `request_error_events`, sem alertar erro isolado.
- `runtime_disk_usage_percent{scope="instance"} >= 85`.

## Sinal vs ruido
- Alarme critico: banco indisponivel, dead-letter, lock stale, ultimo backup falhou, PDF/storage indisponivel, surto de auth ou falhas repetidas de contrato/integracao acima do limiar critico.
- Aviso operacional: backlog crescendo, backup atrasado, storage em atencao, destinatarios de notificacao ausentes ou falhas recentes abaixo do limiar critico.
- Ruido: erro 4xx isolado, uma falha transitoria sem repeticao, indicador de negocio de dashboard sem impacto tecnico imediato.

## Painel operacional
- `/admin/monitoramento`: foco em banco, servicos locais, recursos do host, jobs, backup, notificacoes, auth, falhas recentes, integridade, storage e historico recente.
- `/admin/backups`: drill-down de execucoes de backup e acao manual controlada.

## Rastreio de erro
- Todo erro 500 deve conter `request_id` no payload JSON (API/Ajax).
- Toda investigação deve iniciar por `request_id` + timestamp aproximado + endpoint.
- Métricas apontam o fluxo afetado; logs estruturados explicam a ocorrência individual.
