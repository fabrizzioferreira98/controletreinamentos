# Plano de Teste de Carga

## Escopo
- Listagens: `/treinamentos`, `/missoes`
- Dashboard: `/dashboard`
- Notificações: `/notificacoes-email`
- Login: `/login`

## Execução baseline
`python ops/scripts/perf/load_test_smoke.py --base-url <URL> --seconds 60 --workers 20`

## Métricas de saída
- disponibilidade
- p50/p95/p99
- histograma de status

## Sinais de gargalo
- aumento de p95 com crescimento de workers;
- crescimento de 5xx;
- queda de disponibilidade;
- tempo de resposta desproporcional em notificações/dashboard.

## Bloqueadores de release
- disponibilidade < 99%
- p95 > 1200ms sustentado
- qualquer 5xx persistente nos endpoints críticos
