# ADR 007 - RBAC, audit log e trilha de calculo para operacoes financeiras

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O sistema atual ja possui RBAC por permissoes granulares e audit log acionado explicitamente por use case. O Financeiro tera operacoes sensiveis, incluindo parametros vigentes, calculos de pagamento, fechamento mensal, reabertura e possiveis ajustes.

Como valores financeiros afetam pagamento, nao basta proteger telas. A autorizacao deve existir no backend, e mudancas criticas devem deixar trilha auditavel.

## Decisao

Endpoints financeiros futuros exigirao permissoes explicitas. Mutations criticas devem registrar audit log por use case. Calculos financeiros devem produzir trilha de calculo suficiente para explicar entradas, parametros, regras, calendario, versao logica e totais.

Nao serao criadas ou alteradas permissoes nesta etapa documental; a definicao das permissoes ocorrera na fase de contratos e implementacao.

## Consequencias

- Operacoes financeiras ficam rastreaveis por usuario, data, entidade e escopo.
- O backend continua sendo o ponto de enforcement, nao o menu do frontend.
- Fechamentos e parametros terao maior custo de implementacao por exigirem auditoria.
- Revisoes e investigacoes futuras poderao reconstruir a memoria de calculo.

## Regras praticas

- Criacao, alteracao, cancelamento e exclusao logica de missao operacional devem ser autorizadas.
- Alteracao de parametro financeiro deve exigir permissao explicita e audit log.
- Fechamento, reabertura, aprovacao e cancelamento de fechamento devem exigir permissao explicita e audit log.
- Audit log financeiro deve registrar usuario, data, acao, entidade, identificador, motivo quando aplicavel e antes/depois quando houver mudanca.
- Trilha de calculo deve registrar parametros usados, flags de calendario, participantes, competencia, formulas/versao logica e totais.
- Frontend pode ocultar acoes sem permissao, mas o backend deve negar a operacao.

## O que viola esta decisao

- Confiar apenas na navegacao do frontend para proteger operacao financeira.
- Fazer mutation financeira sem audit log.
- Fechar competencia sem registrar usuario e data do fechamento.
- Alterar parametro vigente sem historico.
- Retornar total financeiro sem memoria de calculo minima.
- Criar permissao generica ampla demais para todas as operacoes financeiras criticas.

## Impacto na proxima fase

A proxima fase deve propor matriz de permissoes financeiras, eventos de auditoria e formato da memoria de calculo antes da implementacao de endpoints mutaveis.
