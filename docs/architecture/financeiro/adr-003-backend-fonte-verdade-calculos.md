# ADR 003 - Backend como fonte da verdade para calculos financeiros

## Status

Proposto e vinculante para a fase de desenho e implementacao futura do modulo Financeiro.

## Contexto

O Financeiro produz valores sensiveis de pagamento e precisa de consistencia, rastreabilidade e seguranca. O frontend atual e uma SPA JavaScript puro e pode ser alterado pelo cliente em runtime, portanto nao deve decidir valores financeiros.

As regras futuras incluem bonificacao horaria por participante, bonificacao por funcao/produtividade por competencia, pre-jornada e pos-jornada automaticos, parametros com vigencia e fechamento mensal com snapshots.

## Decisao

O backend sera a fonte da verdade para calculos financeiros. Calculos de adicional noturno, domingo/feriado, pre-jornada, pos-jornada, produtividade, garantia minima, ICAO, instrutor, checador, cobertura de base, excecoes e fechamento pertencem ao backend.

O frontend apenas consome resultados da API, formata valores e exibe memoria de calculo retornada pelo backend.

## Consequencias

- Resultados financeiros ficam auditaveis e reproduziveis.
- A mesma missao deve gerar o mesmo resultado para qualquer cliente que consulte a API.
- Mudancas de regra financeira exigem alteracao de backend e testes correspondentes.
- O frontend fica mais simples e menos perigoso para operacoes financeiras.

## Regras praticas

- O backend deve receber fatos operacionais, parametros vigentes e competencia, e retornar valores calculados.
- O backend deve retornar memoria de calculo suficiente para revisao operacional e auditoria.
- O frontend pode formatar moeda, duracao, datas, estados e tabelas de exibicao.
- O frontend pode exibir memoria de calculo, alertas e diferencas retornadas pela API.
- O frontend nao pode calcular adicional noturno, pre-jornada, pos-jornada, produtividade, garantia minima ou fechamento.
- O frontend nao pode aplicar tabela financeira nem alterar valor calculado.

## O que viola esta decisao

- Implementar formulas financeiras em `frontend/src/features/financeiro` ou `frontend/src/services`.
- Enviar valor calculado pelo frontend para o backend como valor final confiavel.
- Permitir edicao direta de total calculado sem trilha de excecao auditada.
- Fazer fechamento mensal com base em soma feita no browser.
- Duplicar regras de calendario financeiro no frontend.

## Impacto na proxima fase

Os contratos futuros devem distinguir campos digitados, campos derivados e memoria de calculo. Os testes de API devem garantir que o backend calcula e que o frontend nao recebe responsabilidade decisoria sobre valores.
