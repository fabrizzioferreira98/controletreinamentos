# Paridade Minima Entre Ambientes

## Objetivo

Separar o que pode divergir entre local, homolog e producao sem transformar diferenca perigosa em falso verde aceitavel.

Este documento complementa `docs/operations/LOCAL_RUNTIME.md`: o runtime local diz como subir; esta doc diz quando a validacao local ainda representa o sistema real.

## Mapa de diferencas por eixo

| eixo | local hoje | homolog/stage | producao | classificacao | regra minima agora |
| --- | --- | --- | --- | --- | --- |
| auth | `APP_ENV=development`, cookie `Lax`, sem proxy confiavel por padrao | `APP_ENV=homolog`, `SESSION_COOKIE_SAMESITE=None`, `TRUST_PROXY_HEADERS=1`, dominio de cookie | `APP_ENV=production`, mesmas exigencias de secure env | diferenca perigosa | validacao de auth cross-origin ou atras de proxy so vale com env seguro, origens reais e cookies reais |
| banco | pode subir sem `DATABASE_URL` e falhar depois; massa minima depende de bootstrap manual | banco obrigatorio com `DATABASE_URL` explicito | banco obrigatorio com `DATABASE_URL` explicito | falso verde direto | validacao local so conta com `DATABASE_URL`, schema aplicado, seed minima e usuario autenticavel |
| storage | fallback para temp/instance local se `MEDIA_STORAGE_ROOT` e `APP_INSTANCE_PATH` estiverem vazios | raiz dedicada fora do checkout (`D:\...`) | raiz dedicada fora do checkout (`D:\...`) | falso verde direto | upload/download/PDF so contam com raiz explicita e gravavel |
| worker | processo manual separado | processo operacional dedicado | processo operacional dedicado | bloqueador de validacao real | fluxo que enfileira job so esta validado se um worker consumir fila real |
| scheduler | sem daemon oficial unico; execucao manual | Task Scheduler/rotina operacional | Task Scheduler/rotina operacional | diferenca toleravel temporaria | se a release depende de rotina recorrente, a evidencia precisa vir do scheduler equivalente ou declarar escopo fora |
| notificacoes | SMTP/Resend podem ficar fake; execucao manual e possivel | provider e destinatarios reais configurados | provider e destinatarios reais configurados | diferenca toleravel temporaria | local so pode omitir notificacao quando ela nao fizer parte da evidencia de validacao |
| PDFs | mesmo backend gera PDF, mas storage/local path pode ser irreal | mesmo backend + storage real | mesmo backend + storage real | diferenca perigosa | contrato PDF vale; persistencia do artefato so vale com storage real |
| uploads/downloads | frontend/backoffice pode funcionar gravando em temp local | grava em storage dedicado | grava em storage dedicado | falso verde direto | anexos, fotos e downloads exigem `MEDIA_STORAGE_ROOT` explicito para contar como validacao |
| build frontend | build existe, mas servidor local do SPA nao e canonico | origem estatica separada por Caddy | origem estatica separada por Caddy | diferenca perigosa | fluxo de frontend separado so esta validado com origem estatica real e `FRONTEND_*` coerentes |
| variaveis de ambiente | `.env.example` agora deixa explicitas as variaveis sensiveis, mas varias podem ficar vazias | env de homolog exige runtime/storage/metricas/cron/origens | env de prod exige runtime/storage/metricas/cron/origens | diferenca aceitavel | local pode manter variaveis vazias apenas quando a capacidade correspondente nao entrar como evidencia |
| integracoes externas | SMTP/Resend e outras integracoes podem ser simuladas ou nao configuradas | integra com endpoints reais controlados | integra com endpoints reais | diferenca toleravel temporaria | validacao local precisa declarar claramente quais integracoes estao fake |
| massa de dados | seed minima + usuarios canonicos de teste; sem massa de volume real | massa controlada de homolog | massa operacional real | diferenca aceitavel | smoke local nunca substitui validacao com dados de homolog; massa minima precisa ser declarada |

## Classificacao por risco

### Diferenca aceitavel

- volume de dados menor no local;
- uso de provider fake ou desligado, desde que notificacoes/integracoes nao sejam usadas como evidencia;
- `APP_ENV=development` para fluxo estritamente local e hibrido, desde que nao se tente validar proxy/cookie/origem de ambiente seguro.

### Diferenca toleravel temporaria

- scheduler local manual em vez de daemon recorrente;
- notificacoes manuais em vez de entrega recorrente real;
- integracoes externas desligadas para desenvolvimento, quando a release nao depende delas.

### Diferenca perigosa

- auth local sem cookie/origem real sendo usado como prova de fluxo cross-origin;
- frontend separado sem servidor estatico real;
- PDFs validados sem storage equivalente ao ambiente alvo.

### Falso verde direto

- backend sobe e `/healthz` responde, mas `DATABASE_URL` real, worker ou storage ainda nao estao prontos;
- upload/anexo grava em `temp`/`instance` e parece normal;
- smoke local passa sem `METRICS_TOKEN`, worker ou cron.

### Bloqueador de validacao real

- worker desligado em fluxo que depende de fila;
- scheduler nao executado em fluxo recorrente;
- storage nao explicito em qualquer validacao de upload/download/PDF;
- auth/frontend sem origens reais em qualquer validacao de frontend separado.

## Falsos verdes concretos identificados

- `ops/scripts/smoke/post_deploy_smoke.py` confirma rotas e metricas, mas nao prova worker, scheduler, storage real nem paridade de frontend separado.
- `ops/scripts/qa/hml_runtime_polish_smoke.py` roda com `APP_ENV=testing` e desliga origens de frontend; ele ajuda a detectar regressao funcional, mas nao certifica cookies, proxy, TLS nem Caddy de homolog/producao.
- `backend/src/controle_treinamentos/__init__.py` permite boot sem `DATABASE_URL` fora de secure env; app subir nao significa fluxo autenticado funcional.
- `backend/src/controle_treinamentos/infra/media_storage.py` cai para runtime/instance local quando `MEDIA_STORAGE_ROOT` esta vazio; upload bem-sucedido nesse modo nao prova paridade.
- notificacoes e backups manuais validam disparo pontual, nao a recorrencia do scheduler.
- build de `frontend/dist` sem servidor HTTP real nao valida navegacao do frontend separado.

## O que precisa ser igual

- schema de banco e seed minima compativeis com o ambiente alvo;
- pelo menos um usuario canonico autenticavel;
- um worker real consumindo fila ao validar qualquer fluxo assincrono;
- uma raiz de storage explicita ao validar uploads, downloads ou PDFs;
- `FRONTEND_*` e cookies compatveis com o ambiente alvo ao validar frontend separado;
- `METRICS_TOKEN` configurado quando a validacao incluir metricas.

## O que pode ser diferente

- volume de dados;
- scheduler manual, desde que o fluxo recorrente nao faca parte da evidencia;
- provider de notificacao fake, desde que a evidencia nao inclua envio real;
- local hibrido backend/HTML, desde que nao seja vendido como paridade de SPA separado.

## O que invalida a validacao local

- usar `/healthz` ou smoke simples como prova de sistema completo;
- deixar `MEDIA_STORAGE_ROOT`, worker ou origem estatica fora e ainda assim marcar upload/job/frontend como validados;
- usar `APP_ENV=development` para afirmar paridade de auth segura/cross-origin;
- testar com dados irreais sem declarar a massa minima realmente necessaria;
- aceitar scheduler manual silencioso em release que depende de rotina recorrente.
