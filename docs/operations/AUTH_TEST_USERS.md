# Usuarios de teste canonicos da frente 19.1

Este contrato evita que login, reentrada, usuario inativo e autorizacao sejam validados por contas soltas ou historicas.
Contas reais, pessoais ou operacionais nao devem ser usadas em E2E, smoke, carga autenticada ou contract tests.

## Conjunto canonico

| Login | Finalidade | Estado esperado |
| --- | --- | --- |
| `qa_admin` | Admin/gestora para desenvolvimento, QA manual e smoke autenticado. | Ativo, perfil `gestora`. |
| `qa_operador` | Usuario padrao para fluxo autenticado comum. | Ativo, perfil `operador`. |
| `qa_inativo` | Cenario de autenticacao com usuario inativo. | Inativo. |
| `qa_restrito` | Cenario de autorizacao sem capability suficiente. | Ativo, permissao reduzida. |

`E2E_LOGIN` pode apontar para um destes logins ou para um login tecnico adicional do ambiente quando a esteira exigir isolamento.
Nesse caso, o login deve ser passado como `--keep-login` no saneamento.

## Usuarios temporarios

| Padrao | Origem | Regra |
| --- | --- | --- |
| `qa_runtime_smoke_*` | `ops/scripts/qa/hml_runtime_polish_smoke.py` | Remover no cleanup quando nao houver referencia; se houver referencia, desativar. |
| `e2e_restricted_*` | `tests/e2e/test_critical_journeys.py` | Remover no cleanup do proprio teste. |
| `e2e_landing_*` | `tests/e2e/test_critical_journeys.py` | Remover no cleanup do proprio teste. |

## Saneamento

Inventario sem mutacao:

```powershell
.venv\Scripts\python.exe ops\scripts\admin\sanitize_test_users.py --json
```

Aplicar saneamento conservador, mantendo canonicos e desativando excesso:

```powershell
.venv\Scripts\python.exe ops\scripts\admin\sanitize_test_users.py --apply --keep-login $env:E2E_LOGIN --json
```

Permitir remocao fisica apenas de usuarios de teste nao canonicos sem referencias:

```powershell
.venv\Scripts\python.exe ops\scripts\admin\sanitize_test_users.py --apply --allow-delete --keep-login $env:E2E_LOGIN --json
```

Regras:

- `manter`: somente usuarios canonicos ou login tecnico explicitamente preservado.
- `consolidar`: duplicata de papel que deve apontar para um usuario canonico.
- `desativar`: usuario de teste nao canonico com referencia ou sem permissao de remocao.
- `remover`: usuario de teste nao canonico sem referencia, somente com `--allow-delete`.
- Usuario fora dos padroes tecnicos nao entra no plano.
