# Contratos de dominio financeiro

## Status

Especificacao conceitual para orientar contratos Python, schema futuro e testes. Este documento nao cria classes executaveis, migrations ou rotas.

## Convencoes

- `org_id` usa a decisao de placeholder documentada em `org-scope-placeholder-financeiro.md`.
- Valores monetarios devem trafegar como string decimal em contratos HTTP para evitar perda de precisao.
- Datas usam ISO 8601.
- `competencia` usa formato `YYYY-MM`.
- Tripulantes sao referenciados por id. Nome, CPF, ANAC, contato, foto e flags cadastrais continuam no Cadastro de Tripulantes.
- Campos calculados sao somente leitura para clientes.

## FinanceMission

Representa o fato operacional que gera calculos financeiros.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `id` | integer | Sim em leitura | Backend | Identificador da missao operacional |
| `org_id` | string | Sim | Backend | Placeholder single-tenant ate existir organizacao real |
| `competencia` | string `YYYY-MM` | Sim | Backend/request | Competencia financeira da missao |
| `data_missao` | date | Sim | Request | Data operacional da missao |
| `cavok_numero_voo` | string | Sim | Request | Numero do voo/Cavok |
| `contratante` | string | Nao | Request | Contratante associado |
| `chamado` | string | Nao | Request | Chamado operacional |
| `aeronave_id` | integer | Sim | Request | Referencia a aeronave/equipamento existente |
| `categoria_financeira_aeronave` | enum | Sim | Backend/request | Categoria usada para calculo financeiro |
| `comandante_tripulante_id` | integer | Sim | Request | Referencia ao Cadastro de Tripulantes |
| `copiloto_tripulante_id` | integer | Sim | Request | Referencia ao Cadastro de Tripulantes |
| `horario_apresentacao` | datetime | Sim | Request | Horario unico da missao |
| `horario_abandono` | datetime | Sim | Request | Horario unico da missao |
| `trecho` | string | Sim | Request | Trecho operacional |
| `houve_pernoite` | boolean | Sim | Request | Indica pernoite |
| `quantidade_pernoites` | integer | Sim | Request | Zero quando nao houve pernoite |
| `cobertura_base` | boolean | Sim | Request | Flag operacional para calculo |
| `operacao_especial` | boolean | Sim | Request | Flag operacional para calculo |
| `status` | enum | Sim em leitura | Backend | `rascunho`, `confirmada`, `cancelada`, `em_fechamento`, `fechada` |
| `observacoes` | string | Nao | Request | Observacoes operacionais |

Regras obrigatorias:

- `horario_apresentacao` e `horario_abandono` pertencem a missao, nao ao comandante/copiloto separadamente.
- `comandante_tripulante_id` e `copiloto_tripulante_id` nao podem representar o mesmo tripulante.
- Missoes fechadas nao devem aceitar alteracao direta; correcoes exigem reabertura/fluxo auditado.
- O contrato nao inclui nome, CPF, ANAC, e-mail, telefone ou foto do tripulante.

## FinanceMissionParticipant

Representa um participante calculavel da missao. Pode ser materializado em tabela futura ou retornado como view/contrato derivado.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `mission_id` | integer | Sim | FinanceMission | Missao de origem |
| `tripulante_id` | integer | Sim | FinanceMission | Referencia ao Cadastro de Tripulantes |
| `funcao` | enum | Sim | Backend | `comandante` ou `copiloto` |
| `hourly_bonus_calculation_id` | integer/null | Nao | Backend | Calculo horario associado |
| `calculation_status` | enum | Sim em leitura | Backend | `pendente`, `calculado`, `divergente`, `cancelado` |
| `total_calculado` | decimal string | Nao | Backend | Derivado, somente leitura |
| `calculation_version` | string | Nao | Backend | Versao da logica aplicada |

## HourlyBonusCalculation

Representa calculo horario por participante.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `id` | integer | Sim em leitura | Backend | Identificador do calculo |
| `org_id` | string | Sim | Backend | Escopo organizacional |
| `mission_id` | integer | Sim | Backend | Missao de origem |
| `tripulante_id` | integer | Sim | Backend | Participante calculado |
| `funcao` | enum | Sim | Backend | `comandante` ou `copiloto` |
| `jornada_total_minutos` | integer | Sim | Backend | Derivado dos horarios da missao |
| `minutos_diurnos` | integer | Sim | Backend | Derivado |
| `minutos_noturnos` | integer | Sim | Backend | Derivado |
| `horas_noturnas_convertidas` | decimal string | Sim | Backend | Derivado |
| `minutos_pre` | integer | Sim | Backend | Pre-jornada automatica |
| `minutos_pos` | integer | Sim | Backend | Pos-jornada automatica |
| `domingo_feriado` | boolean | Sim | Backend | Derivado do calendario |
| `valor_adicional_noturno` | decimal string | Sim | Backend | Derivado |
| `valor_domingo_feriado_diurno` | decimal string | Sim | Backend | Derivado |
| `valor_domingo_feriado_noturno` | decimal string | Sim | Backend | Derivado |
| `valor_pre` | decimal string | Sim | Backend | Derivado |
| `valor_pos` | decimal string | Sim | Backend | Derivado |
| `total` | decimal string | Sim | Backend | Soma calculada |
| `memoria_calculo` | CalculationMemory | Sim | Backend | Explicacao estruturada |
| `calculation_version` | string | Sim | Backend | Versao da logica |
| `parametros_usados` | array | Sim | Backend | Parametros e vigencias aplicadas |

## ProductivityBonusCalculation

Representa calculo de funcao/produtividade por competencia e tripulante.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `id` | integer | Sim em leitura | Backend | Identificador do calculo |
| `org_id` | string | Sim | Backend | Escopo organizacional |
| `competencia` | string `YYYY-MM` | Sim | Backend | Competencia calculada |
| `tripulante_id` | integer | Sim | Backend | Referencia ao Cadastro de Tripulantes |
| `funcao` | enum | Sim | Backend | Funcao usada no calculo |
| `categoria_aplicavel` | enum | Sim | Backend | Categoria financeira aplicada |
| `valor_icao` | decimal string | Sim | Backend | Derivado |
| `valor_instrutor` | decimal string | Sim | Backend | Derivado |
| `valor_checador` | decimal string | Sim | Backend | Derivado |
| `valor_missoes_categoria_a` | decimal string | Sim | Backend | Derivado |
| `valor_missoes_categoria_b` | decimal string | Sim | Backend | Derivado |
| `valor_cobertura_base` | decimal string | Sim | Backend | Derivado |
| `valor_excecao_palmas` | decimal string | Sim | Backend | Derivado |
| `produtividade_calculada` | decimal string | Sim | Backend | Derivado |
| `garantia_minima` | decimal string | Sim | Backend | Parametro vigente aplicado |
| `total_devido` | decimal string | Sim | Backend | Resultado final |
| `memoria_calculo` | CalculationMemory | Sim | Backend | Explicacao estruturada |
| `parametros_usados` | array | Sim | Backend | Parametros e vigencias aplicadas |

## FinanceParameter

Representa regra ou valor financeiro com vigencia.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `id` | integer | Sim em leitura | Backend | Identificador do parametro |
| `org_id` | string | Sim | Backend | Escopo organizacional |
| `tipo` | enum | Sim | Request | Ex.: `adicional_noturno`, `pre_jornada`, `garantia_minima`, `produtividade`, `icao`, `instrutor`, `checador`, `cobertura_base`, `excecao_palmas` |
| `funcao` | enum/null | Nao | Request | `comandante`, `copiloto` ou null quando nao aplicavel |
| `categoria` | enum/null | Nao | Request | Categoria financeira quando aplicavel |
| `valor` | decimal string | Sim | Request | Valor aprovado, nao hardcoded em codigo |
| `unidade` | enum | Sim | Request | `BRL`, `percentual`, `minutos`, `multiplicador`, `boolean` |
| `vigencia_inicio` | date | Sim | Request | Inicio da validade |
| `vigencia_fim` | date/null | Nao | Request | Fim da validade |
| `status` | enum | Sim | Backend/request | `ativo`, `inativo`, `substituido`, `rascunho` |
| `motivo` | string | Sim para mutacoes | Request | Justificativa auditavel |
| `created_by` | integer | Sim em leitura | Backend | Usuario criador |
| `created_at` | datetime | Sim em leitura | Backend | Data de criacao |

Regras de vigencia:

- Toda regra usada em calculo precisa ter vigencia.
- Sobreposicoes ambiguas para mesmo `org_id`, `tipo`, `funcao` e `categoria` devem ser rejeitadas ou resolvidas por regra documentada antes da implementacao.
- Alterar parametro nao recalcula competencia fechada sem fluxo controlado.

## FinancePeriod

Representa a competencia financeira.

| Campo | Tipo conceitual | Obrigatorio | Origem | Observacao |
| --- | --- | --- | --- | --- |
| `org_id` | string | Sim | Backend | Escopo organizacional |
| `competencia` | string `YYYY-MM` | Sim | Backend/request | Periodo de referencia |
| `status` | enum | Sim | Backend | `aberta`, `em_conferencia`, `fechada`, `reaberta` |
| `totals` | object | Sim em leitura | Backend | Totais por competencia, participante e tipo |
| `snapshot` | object/null | Sim quando fechada | Backend | Congelamento de fechamento |
| `closed_by` | integer/null | Nao | Backend | Usuario que fechou |
| `closed_at` | datetime/null | Nao | Backend | Data/hora de fechamento |
| `reopen_reason` | string/null | Nao | Request/backend | Motivo da reabertura |

Snapshot minimo:

- missoes consideradas;
- participantes;
- parametros usados;
- memoria de calculo;
- totais;
- usuario e data do fechamento;
- `calculation_version`;
- `org_id`.

## CalculationMemory

Contrato detalhado em `contrato-memoria-calculo-financeiro.md`.

Obrigatorio em calculos horarios, produtividade e snapshots de fechamento.
