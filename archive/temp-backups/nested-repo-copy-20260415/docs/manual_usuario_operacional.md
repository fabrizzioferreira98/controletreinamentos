# Manual de Usuário Operacional

## 1. Introdução
Este sistema centraliza a gestão operacional de tripulantes, habilitações, missões, pernoites, produtividade e monitoramento gerencial.

Módulos principais:
- Dashboards (visão geral e painéis TV)
- Operações (missões, pernoites, gestão de bases)
- Relatórios (consolidado de habilitações, produtividade)
- Cadastros (tripulantes, treinamentos, equipamentos, tipos)
- Usuários e permissões

Perfis:
- `gestora`: acesso total
- `operador`: acesso conforme permissões configuradas

## 2. Acesso ao Sistema
### 2.1 Login
1. Acesse a URL do sistema.
2. Informe `login` e `senha`.
3. Clique em `Entrar`.

### 2.2 Logout
1. Clique em `Sair` na barra lateral.

### 2.3 Controle de Permissão
- Usuários sem permissão não visualizam módulos na sidebar.
- Tentativas de acesso direto por URL sem permissão retornam bloqueio (`403`) e redirecionamento.

## 3. Navegação (Sidebar)
Estrutura:
- **Dashboards**
  - Visão geral
  - Painel TV vencimentos
  - Painel TV produtividade
- **Operações**
  - Missões
  - Pernoites
  - Gestão de Bases
- **Relatórios**
  - Consolidado de habilitações
  - Relatório geral de produtividade
  - Relatório individual (acesso via listas e consolidado)
- **Cadastros**
  - Tripulantes
  - Treinamentos
  - Equipamentos
  - Tipos de treinamento
- **Usuários**
  - Usuários
  - Permissões
  - Destinatários de e-mail
  - Backups
  - Log de ações

## 4. Cadastros
## 4.1 Tripulantes
Campos principais:
- Nome (obrigatório)
- CPF (obrigatório)
- Código ANAC (obrigatório)
- E-mail, Telefone
- Base, Status, Função operacional, Categoria operacional
- Flags operacionais:
  - Tripulante ativo
  - SDEA ativo
  - Instrutor designado
  - Checador designado
  - Elegível para adicional excepcional

Impacto operacional:
- Função/categoria influenciam cálculo de piso e missão.
- Flags influenciam adicionais mensais.

## 4.2 Equipamentos
- Nome, tipo e status ativo/inativo.

## 4.3 Tipos de treinamento
- Nome
- Periodicidade (meses)
- Exige equipamento (sim/não)
- Ativo/inativo

## 4.4 Treinamentos
- Tripulante, tipo, equipamento (quando obrigatório)
- Data de realização e vencimento
- Observação

## 5. Operações
## 5.1 Missões
Campos:
- Código do voo/chamado
- Contratante
- Data início/fim
- Origem/destino
- Tipo de operação
- Conta para produtividade
- Tripulantes vinculados

Regra importante:
- Missão válida é consolidada por `codigo_voo + contratante`.
- Evita contagem por trecho duplicado.

## 5.2 Pernoites
Campos:
- Tripulante
- Missão (opcional)
- Data
- Tipo (`cobertura_base` ou `operacional_comum`)
- Quantidade
- Observações

Regras:
- Cobertura de base soma diretamente.
- Operacional comum pode contar só a partir do 2º dia (conforme parâmetro ativo).

## 5.3 Gestão de Bases
- Monitoramento de tripulantes por base
- Status operacional e histórico

## 6. Bônus / Produtividade
Competência:
- Base mensal no formato `YYYY-MM`.

Entradas da engine:
- Categoria operacional (`A`, `B`, `N/A`)
- Função (`comandante`, `copiloto`, `outro`)
- Missões válidas
- Pernoites elegíveis
- Flags (SDEA, instrutor, checador, elegível excepcional)
- Adicional excepcional manual/paramétrico

Fórmula:
- `valor_final_mes = max(piso_minimo_mensal, total_produtividade)`

Parcelas:
- Valor de missões
- Valor pernoites cobertura
- Valor pernoites operacionais (se aplicável)
- Adicional idioma
- Adicional instrutor
- Adicional checador
- Adicional excepcional

Critério final:
- `piso mínimo` ou `produtividade apurada`

## 7. Habilitações e Vencimentos
Classificação visual:
- Mais de 90 dias: verde
- Até 90 dias: amarelo
- Até 60 dias: laranja
- Até 30 dias: vermelho
- Até 15 dias: vermelho pulsante
- Vencida: destaque crítico
- Sem data: neutro

O sistema usa o vencimento mais crítico para indicadores visuais do tripulante.

## 8. Relatórios
## 8.1 Consolidado de habilitações
Disponível em `Relatórios > Consolidado de habilitações`.

Filtros:
- Nome do tripulante
- Base
- Tipo de habilitação
- Status
- Ordenação

Exportações:
- `Exportar CSV`
- `Emitir PDF` (PDF real gerado no servidor)

## 8.2 Produtividade consolidada
- Filtros por competência, nome, base, função e categoria.
- Cards de resumo no topo.
- Tabela com critério final e link para relatório individual.

## 8.3 Relatório individual de produtividade
- Memória completa de cálculo por tripulante.
- Detalhamento de missões e pernoites considerados.

## 9. Dashboards e Painéis TV
## 9.1 Painel TV Vencimentos
- Modo escuro
- Atualização automática
- Destaques de vencidos e críticos
- Barra inferior rotativa (estilo plantão)
- Layout sem scroll para operação contínua

## 9.2 Painel TV Produtividade
- Indicadores consolidados da competência
- Ranking de produtividade
- Leitura rápida para gestão

## 10. Usuários e Permissões
No módulo `Usuários`:
1. Criar/editar usuário.
2. Selecionar permissões por grupo e submódulo.
3. Salvar.

Boas práticas:
- Conceder mínimo acesso necessário.
- Revisar permissões periodicamente.

## 11. Boas Práticas Operacionais
- Cadastrar missões com código e contratante corretos.
- Evitar duplicidades de lançamento.
- Registrar pernoites no tipo correto.
- Conferir competência antes de fechar produtividade.
- Revisar relatórios de vencimento semanalmente.

## 12. Solução de Problemas
### 12.1 Valores de produtividade zerados
Verifique:
- Se há missões/pernoites na competência
- Se o tripulante está ativo
- Se categoria/função estão corretas

### 12.2 Diferença entre esperado e calculado
Verifique no relatório individual:
- Missões contabilizadas
- Pernoites elegíveis
- Adicionais ativos
- Critério final (piso x produtividade)

### 12.3 Falha em exportação de PDF
Verifique:
- Permissão de relatório habilitações
- Integridade dos dados filtrados

## 13. Glossário
- **Competência**: mês de apuração (`YYYY-MM`).
- **Missão válida**: missão consolidada por código + contratante.
- **Piso mínimo**: valor garantido por regra de categoria/função.
- **Produtividade apurada**: soma das parcelas calculadas.
- **Critério de fechamento**: regra escolhida automaticamente entre piso e produtividade.
