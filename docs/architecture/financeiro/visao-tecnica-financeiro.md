# Visao tecnica do modulo Financeiro

## Objetivo

O Financeiro sera um novo dominio do SaaS operacional de aviacao. Ele cobre missoes operacionais, bonificacoes, parametros e fechamento mensal. O modulo nao restaura as superficies legadas de Missoes ou Produtividade removidas do produto.

## Fronteiras do modulo

O Financeiro deve consumir o Cadastro de Tripulantes existente. Dados como nome, CPF, codigo ANAC, e-mail, telefone, base, status, funcao operacional, categoria, flags de SDEA, instrutor, checador, elegibilidade e foto continuam pertencendo ao cadastro de tripulantes.

O Financeiro referencia tripulantes como comandante e copiloto por identificador e por contratos de leitura. Ele nao duplica cadastro.

## Backend

O backend Flask e a fonte da verdade para valores financeiros. A implementacao futura deve seguir o padrao atual do repositorio:

- rotas HTTP em `backend/src/controle_treinamentos/api/http/`;
- contratos e serializadores em `backend/src/controle_treinamentos/contracts/`;
- use cases em `backend/src/controle_treinamentos/application/`;
- repositories SQL em `backend/src/controle_treinamentos/repositories/`;
- API sob `/api/v1/financeiro`.

Rotas devem delegar regra de negocio para use cases. Repositories concentram SQL. Contratos definem entradas e saidas.

## Frontend

O frontend SPA deve criar uma feature `financeiro` em `frontend/src/features/financeiro` quando a implementacao comecar. A navegacao futura deve passar por `frontend/src/app/route-registry.js` e `frontend/src/shell/navigation.js`.

O frontend pode consumir API, formatar moeda, formatar duracao, exibir estados e mostrar memoria de calculo. Ele nao calcula adicional noturno, pre-jornada, pos-jornada, produtividade, garantia minima, tabelas financeiras ou fechamento.

## Ciclo operacional esperado

1. Registrar missao operacional com data, voo/chamado, aeronave, comandante, copiloto, apresentacao unica, abandono unico e flags operacionais.
2. Calcular bonificacoes no backend com base em missao, participantes, parametros vigentes e calendario.
3. Revisar bonificacoes e memoria de calculo por competencia.
4. Fechar competencia mensal com snapshot de missoes, participantes, parametros, memoria, totais, usuario e data.
5. Reabrir ou corrigir somente por fluxo autorizado e auditado.

## Seguranca e governanca

Endpoints financeiros futuros devem exigir RBAC explicito. Mutations criticas devem registrar audit log por use case. As respostas devem seguir o envelope atual com `success`, `status`, `code`, `message`, `request_id` e `correlation_id`.

Como o produto atual e single-tenant, o Financeiro deve nascer com estrategia incremental de `org_scope`: usar `org_id` ou equivalente se houver entidade organizacional, ou documentar placeholder antes de criar migrations.

## Fora de escopo nesta etapa

- Criar schema ou migrations.
- Criar rotas HTTP.
- Criar frontend.
- Alterar Cadastro de Tripulantes.
- Alterar RBAC global.
- Implementar calculos financeiros.
- Reativar Missoes ou Produtividade legadas.
