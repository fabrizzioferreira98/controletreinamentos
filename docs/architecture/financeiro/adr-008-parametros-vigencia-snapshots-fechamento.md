# ADR 008 - Parametros financeiros com vigencia e snapshots no fechamento mensal

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O Financeiro depende de parametros que mudam ao longo do tempo, como valores de comandante, copiloto, produtividade, garantia minima, ICAO, instrutor, checador, cobertura de base, excecoes, pre-jornada e pos-jornada.

O fechamento mensal precisa preservar o resultado calculado para uma competencia mesmo que parametros sejam alterados depois.

## Decisao

Parametros financeiros terao vigencia. O fechamento mensal deve congelar snapshot de missoes consideradas, participantes, parametros usados, memoria de calculo, totais, usuario e data do fechamento.

Alteracoes futuras de parametros nao devem modificar retroativamente competencias fechadas. Correcoes devem ocorrer por reabertura controlada, novo calculo auditado ou mecanismo equivalente definido na fase de contratos.

## Consequencias

- O resultado de uma competencia fechada fica reproduzivel.
- O historico financeiro nao depende do valor atual de parametros.
- A modelagem precisa tratar sobreposicao, inicio e fim de vigencia.
- O fechamento passa a ser entidade de controle, nao apenas uma consulta agregada.

## Regras praticas

- Todo parametro financeiro deve ter inicio de vigencia.
- Parametros que deixam de valer devem ter fim de vigencia ou substituicao controlada.
- A API deve impedir vigencias ambiguas quando isso comprometer calculo.
- Fechamento deve guardar a lista de missoes e participantes considerados.
- Fechamento deve guardar parametros usados e memoria de calculo.
- Fechamento deve guardar totais por participante e por competencia quando aplicavel.
- Fechamento deve guardar usuario e data/hora do fechamento.

## O que viola esta decisao

- Usar apenas uma tabela de parametros atuais para recalcular passado fechado.
- Fechar competencia sem snapshot.
- Permitir parametros sobrepostos sem regra de precedencia.
- Alterar totais de fechamento sem reabertura, motivo e audit log.
- Calcular pagamento com parametros sem vigencia.

## Impacto na proxima fase

A modelagem futura deve definir entidades de parametro, vigencia e fechamento antes de criar migrations. Os contratos de fechamento devem representar snapshot e memoria de calculo como dados persistidos, nao como uma consulta volatil.
