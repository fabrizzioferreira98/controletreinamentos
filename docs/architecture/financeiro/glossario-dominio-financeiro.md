# Glossario de dominio financeiro

## Financeiro

Novo dominio responsavel por missoes operacionais, bonificacoes, parametros e fechamento mensal. Nao e restauracao de Missoes ou Produtividade legadas.

## Missao operacional

Fato operacional que origina calculos financeiros. Deve conter data, Cavok ou numero do voo, contratante ou chamado, aeronave, comandante, copiloto, apresentacao unica, abandono unico, trecho, pernoite, cobertura de base e operacao especial quando aplicavel.

## Categoria financeira da aeronave

Classificacao cadastral do equipamento usada futuramente pelo Financeiro. Valores aceitos: `a`, `b`, `turbohelice_palmas` e `nao_aplicavel`. A categoria e informada no cadastro de equipamentos e nao calcula valores sozinha.

## Participante

Tripulante vinculado a uma missao operacional para fins de calculo. No escopo inicial, os participantes esperados sao comandante e copiloto.

## Comandante

Tripulante da missao com funcao de comandante. Usa os horarios unicos da missao para calculo financeiro.

## Copiloto

Tripulante da missao com funcao de copiloto. Usa os horarios unicos da missao para calculo financeiro.

## Apresentacao

Horario unico de inicio operacional da missao. Pertence a missao e e herdado por comandante e copiloto.

## Abandono

Horario unico de encerramento operacional da missao. Pertence a missao e e herdado por comandante e copiloto.

## Pre-jornada

Periodo automatico calculado pelo backend antes da jornada principal, conforme parametro vigente.

## Pos-jornada

Periodo automatico calculado pelo backend apos a jornada principal, conforme parametro vigente.

## Bonificacao horaria

Valor calculado por participante a partir de horarios da missao, calendario, parametros vigentes e regras financeiras.

## Bonificacao por funcao/produtividade

Valor consolidado por competencia a partir de funcao operacional, produtividade, parametros vigentes e regras financeiras.

## Competencia

Periodo de referencia do calculo e fechamento financeiro, normalmente mensal.

## Parametro financeiro

Regra ou valor usado pelo backend para calculo financeiro, como adicional de comandante, copiloto, produtividade, garantia minima, ICAO, instrutor, checador, cobertura de base, excecoes, pre-jornada e pos-jornada.

## Vigencia

Intervalo em que um parametro financeiro e valido. Parametros devem ter inicio de vigencia e, quando substituidos ou encerrados, fim de vigencia ou regra equivalente.

## Calendario financeiro

Fonte de informacao para domingos, feriados, periodos noturnos e outras condicoes temporais usadas em calculo.

## Memoria de calculo

Explicacao estruturada do resultado financeiro, contendo entradas usadas, parametros vigentes, flags de calendario, regras aplicadas e totais calculados.

## Snapshot de fechamento

Registro congelado de uma competencia fechada, incluindo missoes consideradas, participantes, parametros usados, memoria de calculo, totais, usuario e data do fechamento.

## Fechamento mensal

Operacao que consolida e congela os resultados financeiros de uma competencia. Deve ser autorizada, auditada e reversivel somente por fluxo controlado.

## Reabertura

Operacao controlada para permitir correcao de competencia fechada. Deve exigir permissao explicita, motivo e audit log.

## org_scope

Escopo organizacional usado para isolar dados financeiros por organizacao em uma evolucao SaaS. O produto atual e single-tenant, mas novas estruturas financeiras devem prever `org_id` ou placeholder equivalente antes de migrations.

## Audit log financeiro

Registro de operacoes financeiras criticas com usuario, data, acao, entidade, identificador, motivo quando aplicavel e dados antes/depois quando houver alteracao.

## Backend fonte da verdade

Principio de que valores financeiros sao calculados e decididos pelo backend. O frontend consome, formata e exibe resultados, sem aplicar regras financeiras.
