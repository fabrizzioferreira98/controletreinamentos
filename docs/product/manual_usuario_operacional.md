# Manual Operacional de Usuario

## 1. Introducao

Este sistema centraliza a gestao operacional de tripulantes, habilitacoes, pernoites, bases, arquivos, usuarios, auditoria e monitoramento.

Modulos vivos:

- Dashboard de visao geral
- Operacoes: pernoites e bases
- Relatorios: consolidado de habilitacoes
- Cadastros: tripulantes, treinamentos, equipamentos e tipos
- Administracao: usuarios, permissoes, notificacoes, backups, auditoria e monitoramento

## 2. Acesso

- Acesse a URL oficial do sistema.
- Informe login e senha.
- Use Sair para encerrar a sessao.
- Se um menu nao aparecer, verifique as permissoes do usuario.

## 3. Navegacao

A navegacao e organizada por area funcional. Use o dashboard para leitura rapida de vencimentos e pendencias, e acesse as listas operacionais para acoes de cadastro, edicao e consulta.

## 4. Tripulantes

O cadastro de tripulantes concentra dados de identidade, base, status, funcao operacional, arquivos e foto.

Boas praticas:

- Manter nome, CPF, codigo ANAC, email, telefone, base e status atualizados.
- Usar a aba de arquivos para documentos persistidos.
- Usar o relatorio individual de treinamentos para conferir historico e vencimentos.

## 5. Treinamentos e Habilitacoes

Treinamentos registram realizacao, vencimento, equipamento, tipo e evidencias anexas.

O consolidado de habilitacoes agrupa vencimentos por tripulante e permite exportacao CSV/PDF.

Classificacao operacional:

- Mais de 90 dias: em dia
- Ate 90 dias: atencao inicial
- Ate 60 dias: atencao elevada
- Ate 30 dias: risco alto
- Ate 15 dias: critico
- Vencida: acao imediata
- Sem data: sem vencimento informado

## 6. Operacoes

### 6.1 Pernoites

Registre tripulante, data, tipo e quantidade. Pernoite avulso permanece como compat operacional para casos existentes ou excepcionais.

### 6.2 Bases

Use Gestao de Bases para acompanhar distribuicao operacional, status e historico de movimentacao.

## 7. Relatorios e PDFs

Relatorios vivos:

- Consolidado de habilitacoes
- Relatorio individual de treinamentos do tripulante
- Auditoria
- Manual do usuario

Antes de distribuir um PDF, confira filtros, data de emissao e totais de resumo.

## 8. Usuarios e Permissoes

Permissoes controlam visualizacao e acoes. O backend valida autorizacao mesmo que a interface oculte itens sem permissao.

Boas praticas:

- Aplicar menor privilegio.
- Revisar acessos em mudanca de funcao.
- Manter usuarios inativos bloqueados.

## 9. Auditoria, Backups e Monitoramento

- Auditoria registra eventos sensiveis.
- Backups devem seguir a rotina oficial do ambiente self-hosted.
- Monitoramento acompanha saude operacional, jobs e disponibilidade.

## 10. Solucao de Problemas

- Menu nao aparece: verificar permissoes.
- Relatorio divergente: validar filtros e dados de cadastro.
- PDF nao abre: verificar se a resposta foi gerada como `application/pdf`.
- Sem envio de email: validar destinatarios ativos e provider configurado.
- Sessao expirada: autenticar novamente.

## 11. Glossario

- Habilitacao: requisito tecnico com vencimento monitorado.
- Pernoite: estadia operacional registrada por tipo e quantidade.
- Dashboard: visao resumida de indicadores.
- Evidencia: arquivo ou anexo usado para apoiar um registro.
- Permissao: autorizacao de acesso por modulo ou acao.
