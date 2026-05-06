# Estrategia de Protecao de Testes

## Papel

Esta estrategia consolida as frentes 23.1 a 23.5 em uma politica de protecao operacional. O objetivo nao e aumentar volume bruto de testes, e sim definir qual camada protege cada risco critico e quais suites entram em confianca minima, gate e regressao operacional.

## Base fixa

| frente | camada | evidencia viva |
| --- | --- | --- |
| 23.1 | unitarios | `tests/unit/` protege regras puras, validadores, formatadores, helpers, calculos, politicas de upload, auth, auditoria e logging. |
| 23.2 | integracao | `tests/integration/` protege banco, repositorios, storage, PDFs, rotas resilientes e costuras backend. |
| 23.3 | contratos | `tests/contract/` protege endpoints, payloads, erros, datas, ids, nullability, compat residual e drift HTTP. |
| 23.4 | frontend funcional | `tests/contract/test_frontend_ux_functional_guards.py` protege auth flow, fallback de rota, feedback, formularios e estados especiais sem snapshot cosmetico. |
| 23.5 | end-to-end | `tests/e2e/test_critical_journeys.py` protege jornadas sensiveis contra homologacao real com banco, sessao, permissao, arquivos, foto, exports e jobs. |

## Cobertura obrigatoria

| item | camada responsavel | criterio |
| --- | --- | --- |
| Regras puras, validadores, formatadores, matrizes e motores de calculo | unitario | Deve falhar rapido e isolado quando regra de dominio ou politica muda. |
| Repositorio + service + banco, storage, PDF e jobs | integracao | Deve provar que a costura real funciona sem depender de browser ou E2E. |
| Endpoints canonicos, erros, ids, datas, nullability e compat residual | contrato | Deve impedir drift de borda estavel. |
| Auth flow, feedback de erro, formularios criticos e fallback de rota | frontend funcional/contrato | Deve proteger comportamento operacional de UI sem teste visual cosmetico. |
| Login/logout, sessao expirada, permissao, upload/download, foto, documento, geracao/exportacao e backup/job | E2E de homologacao | Deve provar que fluxos sensiveis funcionam em ambiente real controlado. |

## Fora agora

| item | motivo |
| --- | --- |
| Snapshot visual amplo | Alto ruido e baixa protecao operacional. |
| E2E para todos os CRUDs | Duplicaria contratos e integracao; usar E2E so para jornada sensivel. |
| Browser E2E completo em todo commit | Depende de infraestrutura e tende a flakiness sem ambiente dedicado. |
| Teste unitario de detalhe de framework, query trivial ou HTML estatico | Nao reduz risco relevante. |
| Metricas de cobertura como meta isolada | Pode incentivar teste ornamental. |

## Priorizacao

1. Gate rapido: arquitetura, unitarios, contratos e integracoes sem dependencia externa.
2. Frontend funcional minimo: guards de auth, formularios, rota, feedback e estados especiais.
3. Regressao operacional: ops, backup/restore, release evidence, jobs, storage e PDF.
4. E2E homologacao: somente com `E2E_DATABASE_URL`, `E2E_LOGIN` e `E2E_PASSWORD`, antes de release ou mudanca sensivel.
5. Exploracao visual/manual: apenas para mudanca de layout, acessibilidade ou interacao rica que nao tenha protecao melhor em camada inferior.

## Redundancia e flakiness

| risco | regra |
| --- | --- |
| Contrato repetindo unitario | Contrato deve validar borda estavel; regra pura fica no unitario. |
| E2E repetindo integracao | E2E so entra se houver valor de jornada completa: sessao, permissao, storage, banco, renderer ou job juntos. |
| Teste frontend cosmetico | Proibido como protecao principal; preferir estado funcional, erro, navegacao e formulario. |
| E2E com banco real | Nao e gate de commit sem ambiente controlado; usar skip explicito quando env obrigatoria faltar. |
| Sleep, rate-limit e dados compartilhados | Resetar estado, usar massa canonica, limpar entidades criadas e evitar dependencia de ordem. |

## Suites oficiais

| suite | comando base | papel |
| --- | --- | --- |
| Minima de confianca local | `.venv\Scripts\python.exe -m pytest tests\architecture tests\unit tests\contract tests\integration tests\ops -q` | Sinal rapido de regressao tecnica, contrato, costura e politica operacional sem homologacao real. |
| Gate de release | `.venv\Scripts\python.exe ops\scripts\release\run_release_strict.py --base-url <url-alvo> --evidence-manifest <manifest.json> --regression-checklist <checklist-preenchido>` | Gate oficial com evidencias, checklist e validacoes operacionais. |
| E2E de homologacao | `.venv\Scripts\python.exe -m pytest tests\e2e -q` | Jornada ponta a ponta com banco real, usuario canonico e massa controlada. |

## Criterio de uso

- Mudanca em regra pura exige unitario.
- Mudanca em schema, repositorio, storage, PDF ou job exige integracao.
- Mudanca em endpoint, serializer, erro, data, id, nullability ou compat exige contrato.
- Mudanca em login, navegacao, formulario, feedback ou estado especial de UI exige frontend funcional.
- Mudanca que combina sessao, permissao, banco, storage, documento, exportacao ou job exige E2E de homologacao ou justificativa explicita de camada melhor.

## Estrategia final

A protecao oficial fica organizada por risco, nao por quantidade: unitario protege regra, integracao protege costura, contrato protege borda, frontend funcional protege operacao de UI, E2E protege jornada sensivel e ops protege release/diagnostico. Qualquer teste novo deve declarar qual risco reduz; caso contrario, nao entra na suite obrigatoria.
