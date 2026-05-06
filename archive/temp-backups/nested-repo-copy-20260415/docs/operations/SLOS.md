# SLOs Mínimos

## SLI/SLO
- Disponibilidade HTTP (2xx/3xx): >= 99.0% por mês.
- Latência p95 endpoints críticos: <= 1200ms.
- Erros 5xx: <= 1.0% em janelas de 5 minutos.
- Jobs em dead-letter: 0 persistente por mais de 15 minutos.

## Endpoints críticos
- `/login`
- `/dashboard`
- `/treinamentos`
- `/missoes`
- `/notificacoes-email`

## Ação em violação
- Violação de disponibilidade/erro: abrir incidente P1.
- Violação de latência p95 por 3 janelas: abrir incidente P2 e plano de mitigação.
