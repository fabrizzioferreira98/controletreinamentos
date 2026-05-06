# Contrato de memoria de calculo financeiro

## Status

Especificacao conceitual para responses, snapshots e auditoria. Nao implementa calculo.

## Objetivo

A memoria de calculo explica como o backend chegou a um valor financeiro. Ela deve permitir revisao por financeiro, auditoria e suporte, sem transferir a responsabilidade de calculo para o frontend.

## Estrutura conceitual

```json
{
  "calculation_version": "finance-v1",
  "org_id": "default_single_tenant",
  "competencia": "2026-04",
  "source": {
    "type": "finance_mission",
    "id": 123
  },
  "participant": {
    "tripulante_id": 10,
    "funcao": "comandante"
  },
  "inputs": {},
  "parameters": [],
  "calendar_flags": {},
  "steps": [],
  "totals": {},
  "warnings": [],
  "generated_at": "2026-04-29T12:00:00-03:00"
}
```

## Campos obrigatorios

| Campo | Tipo conceitual | Obrigatorio | Observacao |
| --- | --- | --- | --- |
| `calculation_version` | string | Sim | Versao da logica de calculo |
| `org_id` | string | Sim | Escopo organizacional aplicado |
| `competencia` | string `YYYY-MM` | Sim | Competencia calculada |
| `source.type` | string | Sim | `finance_mission`, `finance_period` ou outro agregado financeiro |
| `source.id` | integer/string | Sim | Identificador da origem |
| `participant.tripulante_id` | integer/null | Conforme calculo | Obrigatorio em calculo por participante |
| `participant.funcao` | string/null | Conforme calculo | `comandante`, `copiloto` ou null |
| `inputs` | object | Sim | Entrada operacional usada |
| `parameters` | array | Sim | Parametros vigentes usados |
| `calendar_flags` | object | Sim | Domingo, feriado, periodo noturno e flags temporais |
| `steps` | array | Sim | Passos explicativos |
| `totals` | object | Sim | Resultados finais |
| `warnings` | array | Sim | Alertas sem bloquear calculo |
| `generated_at` | datetime | Sim | Data/hora da geracao |

## Step de calculo

Cada item de `steps` deve explicar:

| Campo | Tipo conceitual | Obrigatorio | Observacao |
| --- | --- | --- | --- |
| `rule_key` | string | Sim | Chave tecnica da regra aplicada |
| `rule_label` | string | Sim | Nome legivel da regra |
| `entrada_usada` | object | Sim | Fato operacional considerado |
| `parametro_usado` | object/null | Sim | Parametro e vigencia aplicados |
| `formula_conceitual` | string | Sim | Descricao da formula, nao codigo executavel |
| `resultado_intermediario` | object | Sim | Resultado parcial |
| `resultado_final` | object | Sim | Resultado do passo |
| `notes` | array | Nao | Observacoes de auditoria |

## Parametro usado

Cada parametro referenciado em `parameters` ou `step.parametro_usado` deve conter:

- `parameter_id`;
- `tipo`;
- `funcao`;
- `categoria`;
- `valor`;
- `unidade`;
- `vigencia_inicio`;
- `vigencia_fim`;
- `applied_at`;

## Entradas permitidas

Para calculo horario, `inputs` pode conter:

- `mission_id`;
- `data_missao`;
- `horario_apresentacao`;
- `horario_abandono`;
- `trecho`;
- `houve_pernoite`;
- `quantidade_pernoites`;
- `cobertura_base`;
- `operacao_especial`;
- `tripulante_id`;
- `funcao`.

Para produtividade, `inputs` pode conter:

- `competencia`;
- `tripulante_id`;
- `funcao`;
- `categoria_operacional`;
- `flags_operacionais` lidas do Cadastro de Tripulantes;
- contagens agregadas de missoes por categoria;
- flags de cobertura ou excecao.

## Regras de uso

- A memoria e produzida pelo backend.
- O frontend pode exibir a memoria, filtrar visualmente e formatar valores.
- O frontend nao pode recalcular os passos.
- Snapshots de fechamento devem persistir a memoria usada.
- Alteracao de parametro depois do fechamento nao altera memoria ja snapshotada.
- Memoria nao deve duplicar dados cadastrais sensiveis de tripulantes.
