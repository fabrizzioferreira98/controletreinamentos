# ADR 004 - Separacao entre fatos operacionais, calculos derivados, parametros e fechamento

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O Cadastro de Missao sera a origem dos calculos financeiros. Cada missao tera comandante e copiloto, com horario de apresentacao unico e horario de abandono unico. Comandante e copiloto herdam os mesmos horarios da missao.

Os valores financeiros nao sao fatos operacionais digitados. Eles derivam da missao, dos participantes, dos parametros vigentes e do calendario aplicavel.

## Decisao

O Financeiro sera dividido em quatro conceitos:

- Fatos operacionais: dados da missao e seus participantes.
- Calculos derivados: valores financeiros calculados por participante ou por competencia.
- Parametros financeiros: regras e valores com vigencia.
- Fechamento mensal: congelamento dos fatos, parametros, memoria e totais de uma competencia.

Uma missao operacional deve registrar dados operacionais como data, Cavok ou numero do voo, contratante ou chamado, aeronave, comandante, copiloto, apresentacao unica, abandono unico, trecho, pernoite, cobertura de base e operacao especial.

## Consequencias

- A missao permanece a fonte operacional do calculo, mas nao armazena totals como verdade primaria.
- Recalculos podem ser explicados a partir de fatos, parametros e calendario.
- Fechamentos precisam snapshotar a memoria de calculo para preservar historico.
- Excecoes devem ser explicitas, autorizadas e auditadas.

## Regras praticas

- Horario de apresentacao pertence a missao, nao ao comandante nem ao copiloto isoladamente.
- Horario de abandono pertence a missao, nao ao comandante nem ao copiloto isoladamente.
- Bonificacao horaria deve ser calculada por participante.
- Bonificacao por funcao/produtividade deve ser consolidada por competencia.
- Campos financeiros calculados devem ser tratados como derivados.
- Ajustes manuais, quando existirem, devem ser excecoes auditadas, nao substitutos da regra de calculo.

## O que viola esta decisao

- Gravar adicional, produtividade ou garantia minima como valores digitados sem memoria de calculo.
- Permitir horarios divergentes por tripulante na mesma missao quando a regra define horarios unicos.
- Misturar cadastro de parametros com fechamento mensal.
- Recalcular competencia fechada sem registrar reabertura, usuario, data e motivo.
- Duplicar dados cadastrais de tripulantes dentro de fatos financeiros.

## Impacto na proxima fase

O desenho de contratos e banco deve separar claramente endpoints de missoes, calculos ou previews, parametros e fechamentos. Testes devem cobrir que calculos derivam dos fatos e parametros, nao de totais enviados pelo frontend.
