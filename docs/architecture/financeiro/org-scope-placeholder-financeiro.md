# Decisao concreta de org_scope para o Financeiro

## Status

Decisao tecnica para futuras migrations financeiras. Nao cria schema nesta etapa.

## Contexto

O produto atual e single-tenant/self-hosted Windows/local e nao possui org_scope vivo. O Financeiro, porem, e sensivel e deve nascer com caminho claro para isolamento organizacional futuro.

## Decisao

Futuras tabelas financeiras devem usar a coluna conceitual:

```text
org_id TEXT NOT NULL DEFAULT 'default_single_tenant'
```

Enquanto nao existir tabela de organizacoes, `org_id='default_single_tenant'` representa o deploy single-tenant atual. Este valor e um placeholder tecnico de escopo, nao uma regra financeira de negocio.

Quando existir entidade organizacional real, uma migration futura podera mapear `default_single_tenant` para a organizacao criada e, se necessario, trocar a coluna para FK ou manter chave textual conforme decisao global de tenancy.

## Aplicacao nas futuras tabelas financeiras

`org_id` deve existir em:

- missoes operacionais;
- participantes/materializacoes financeiras, se houver;
- calculos horarios persistidos;
- calculos de produtividade persistidos;
- parametros financeiros;
- feriados/calendario financeiro;
- competencias/fechamentos;
- snapshots;
- divergencias;
- exportacoes;
- metadados de audit log financeiro quando possivel.

## Impacto em queries futuras

Repositories SQL financeiros devem receber `org_id` como parte do contexto de consulta e aplicar filtro:

```text
WHERE org_id = :org_id
```

Indices e restricoes unicas financeiras devem considerar `org_id`, por exemplo:

- `org_id + competencia`;
- `org_id + mission_id`;
- `org_id + tipo + funcao + categoria + vigencia`;
- `org_id + competencia + tripulante_id`.

Listagens, detalhes, fechamentos e recalculos nao devem acessar dados financeiros sem escopo.

## Impacto em contratos

Contratos de leitura podem retornar `org_id` para auditoria e suporte. Contratos de escrita nao devem aceitar `org_id` arbitrario do frontend nesta fase single-tenant; o backend deve resolver o escopo.

Quando multi-tenant real existir, a origem de `org_id` deve vir de contexto autenticado/organizacional, nao de campo livre enviado pelo cliente.

## Limites da decisao

- Esta decisao nao implementa multi-tenant real.
- Nao ha isolamento completo sem enforcement em banco, repositories, auth, audit log e testes.
- Nao ha refatoracao global do produto nesta etapa.
- Nao deve ser anunciada capacidade SaaS multi-tenant ate que isolamento efetivo exista.

## O que bloquear antes de migrations

- Criar tabela financeira sem `org_id`.
- Criar unica global que deveria ser por organizacao.
- Aceitar `org_id` do frontend como autoridade.
- Implementar filtro organizacional apenas no frontend.
- Fechar competencia sem registrar `org_id` no snapshot.
