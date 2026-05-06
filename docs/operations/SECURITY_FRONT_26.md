# Frente 26 - Seguranca

Esta e a leitura viva curta da frente 26 na fase atual. Ela registra risco real e trilha de correcao sem reabrir arquitetura, auth, storage ou operacao Windows/self-hosted.

## 1. Mapa real

| superficie | estado atual | leitura de risco |
| --- | --- | --- |
| Auth e sessao | Login com hash de senha, CSRF, rate limit em memoria, cookies HttpOnly/SameSite/Secure por ambiente e expiracao de sessao. | Suficiente para single-host atual; rate limit distribuido fica como divida futura se houver escala horizontal. |
| API | Contrato JSON, permissao por endpoint, request/correlation id e CORS por allowlist. | Suficiente; manter novos endpoints fora de `PUBLIC_ENDPOINTS` salvo justificativa explicita. |
| Upload/download/storage | PDF/foto com assinatura, MIME declarado, tamanho, hash, storage_ref `fs:` sob raiz operacional e permissoes de arquivo. | Suficiente para storage local; refs remotas seguem congeladas ate existir adapter real. |
| HTML renderizado | Jinja com escaping padrao, headers de seguranca, CSP conservadora com `unsafe-inline` residual. | Aceitavel na fase atual; CSP sem inline exige refatoracao maior e fica para depois. |
| Admin/ops | Usuarios, auditoria, backup, jobs e notificacoes protegidos por capabilities e auditados. | Risco principal e abuso por usuario privilegiado; manter auditoria e idempotencia. |
| Integracoes externas | E-mail SMTP/Resend, Sentry, metricas tokenizadas, backup S3 opcional. | Operam por variaveis de ambiente; segredos reais nao devem entrar no repo. |

## 2. Hotspots e fila

| item | acao | motivo |
| --- | --- | --- |
| `safe_next_url` | corrigir agora | Evita redirect ambiguo por `//`, barra invertida e encoding perigoso. |
| Exemplos de `SMTP_PASSWORD` preenchido | corrigir agora | Placeholder parecia senha usavel em env de exemplo. |
| `frontend/dist` | isolar | Build gerado; nao e fonte nem criterio de seguranca. |
| Logout sem CSRF obrigatorio | congelar | Mantem encerramento idempotente de sessao invalida; risco limitado a logout forjado. |
| Rate limit em memoria | corrigir depois | Adequado em single-host; insuficiente se houver multiplas instancias. |
| `last_error` de jobs para admin | corrigir depois | Pode conter detalhes operacionais; hoje restrito a `usuarios:manage`. |
| Dependencias | corrigir depois | Pins existem, mas a fase atual nao executa SCA/CVE sem `pip-audit` ou ferramenta equivalente. |

## 3. Conclusao

A frente 26 fica fechada na fase atual com controles reais mapeados. O residual curto e: SCA de dependencias, rate limit distribuido se a topologia mudar, revisao de exibicao de `last_error` em telas administrativas e remocao futura de `unsafe-inline` quando o frontend permitir.
