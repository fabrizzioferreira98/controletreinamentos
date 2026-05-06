from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT_FILE = Path(__file__).resolve().parent / "manual-usuario-operacional-completo.pdf"


def section(title: str) -> Paragraph:
    return Paragraph(title, STYLES["ManualSection"])


def subsection(title: str) -> Paragraph:
    return Paragraph(title, STYLES["ManualSubsection"])


def p(text: str) -> Paragraph:
    return Paragraph(text, STYLES["ManualBody"])


def bullets(items: list[str]) -> ListFlowable:
    rows = [ListItem(Paragraph(item, STYLES["ManualBody"]), leftIndent=4) for item in items]
    return ListFlowable(rows, bulletType="bullet", bulletFontName="Helvetica-Bold", bulletFontSize=8, leftPadding=18)


def build_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(colors.HexColor("#0f172a"))
    canvas.drawString(16 * mm, 285 * mm, "Treinamentos Brasil vida · Manual de Usuário Operacional")
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.setLineWidth(0.5)
    canvas.line(16 * mm, 283 * mm, 194 * mm, 283 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.line(16 * mm, 12 * mm, 194 * mm, 12 * mm)
    canvas.drawString(16 * mm, 8 * mm, f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.drawRightString(194 * mm, 8 * mm, f"Página {doc.page}")
    canvas.restoreState()


def build_manual():
    story = []

    story.append(Paragraph("Manual de Usuário Operacional", STYLES["ManualTitle"]))
    story.append(Paragraph("Sistema Treinamentos Brasil vida", STYLES["ManualSubtitle"]))
    story.append(Spacer(1, 8))
    story.append(
        p(
            "Este documento é a referência oficial de uso da plataforma para equipes operacionais, administrativas e gestoras. "
            "O conteúdo foi estruturado para treinamento de novos usuários e consulta diária em ambiente de produção."
        )
    )
    story.append(Spacer(1, 10))

    story.append(section("1. Apresentação do sistema"))
    story.append(
        p(
            "O sistema Treinamentos Brasil vida centraliza controle de tripulantes, treinamentos, vencimentos de habilitações, "
            "missões, pernoites, produtividade e monitoramento gerencial. A plataforma elimina dependência de planilhas dispersas, "
            "reduz risco operacional e cria rastreabilidade de decisões."
        )
    )
    story.append(bullets([
        "Problemas que resolve: falta de visibilidade de vencimentos, inconsistências de cálculo, baixa rastreabilidade e retrabalho operacional.",
        "Módulos principais: Dashboards, Operações, Relatórios, Cadastros e Usuários/Permissões.",
        "Perfis típicos: operador (execução diária) e gestora (administração e governança).",
    ]))

    story.append(section("2. Acesso ao sistema"))
    story.append(subsection("2.1 Login e saída"))
    story.append(bullets([
        "Acesse a URL oficial do sistema, informe login e senha e clique em Entrar.",
        "Para encerrar sessão, use a opção Sair na barra lateral.",
        "Após inatividade prolongada, o sistema pode solicitar novo login por segurança.",
    ]))
    story.append(subsection("2.2 Erros de acesso e segurança"))
    story.append(bullets([
        "Se ocorrer bloqueio por tentativas inválidas, aguarde o tempo de segurança e tente novamente.",
        "Usuário inativo não consegue autenticar.",
        "Não compartilhe senha; cada usuário deve usar credenciais individuais.",
        "Se um menu não aparecer, normalmente é ausência de permissão, não falha de sistema.",
    ]))

    story.append(section("3. Navegação geral"))
    story.append(
        p(
            "A navegação lateral é organizada por grupos para reduzir ruído visual e facilitar uso contínuo em operação. "
            "Cada grupo reúne telas com finalidade similar."
        )
    )
    story.append(bullets([
        "Dashboards: visão geral, painel TV vencimentos e painel TV produtividade.",
        "Operações: missões, pernoites e gestão de bases.",
        "Relatórios: consolidado de habilitações e produtividade.",
        "Cadastros: tripulantes, treinamentos, equipamentos e tipos de treinamento.",
        "Usuários: gestão de acessos, destinatários de e-mail, backups e auditoria.",
    ]))
    story.append(
        p(
            "O item ativo do menu indica a tela atual. Grupos e itens ocultos indicam ausência de autorização para aquele usuário."
        )
    )

    story.append(section("4. Dashboard / visão geral"))
    story.append(
        p(
            "A tela inicial apresenta indicadores operacionais agregados. Use essa visão para identificar tendência de risco, "
            "volumes de pendência e necessidade de ação imediata."
        )
    )
    story.append(bullets([
        "Cards principais: totais de tripulantes, treinamentos e distribuição por status.",
        "Alertas: destacam itens vencidos e próximos do vencimento.",
        "Uso recomendado: abrir no início e no fim da rotina diária para validação rápida de cenário.",
    ]))

    story.append(section("5. Cadastros"))
    story.append(subsection("5.1 Cadastro de tripulantes"))
    story.append(
        p(
            "Finalidade: manter a base mestre de pessoas que serão usadas em treinamentos, operações e cálculos de produtividade."
        )
    )
    story.append(bullets([
        "Campos obrigatórios: nome, CPF, código ANAC, base, status, função operacional, categoria operacional.",
        "Campos operacionais relevantes: SDEA ativo, instrutor, checador, elegível adicional excepcional, ativo/inativo.",
        "Impacto: dados incorretos de função/categoria afetam diretamente o cálculo de produtividade e fechamento mensal.",
        "Boa prática: revisar base/status e flags operacionais no fechamento da competência.",
    ]))
    story.append(subsection("5.2 Equipamentos"))
    story.append(bullets([
        "Finalidade: catálogo de aeronaves/recursos usados em treinamentos.",
        "Campos típicos: nome, tipo e ativo.",
        "Impacto: melhora rastreabilidade do histórico de habilitações.",
    ]))
    story.append(subsection("5.3 Tipos de treinamento"))
    story.append(bullets([
        "Finalidade: definir catálogo de treinamentos e periodicidade.",
        "Campos críticos: nome, periodicidade em meses, exige equipamento, ativo.",
        "Impacto: periodicidade influencia cálculo automático do vencimento.",
    ]))
    story.append(subsection("5.4 Demais cadastros-base"))
    story.append(
        p("Usuários e destinatários de e-mail também são cadastros-base para governança e comunicação da operação.")
    )

    story.append(section("6. Operações"))
    story.append(subsection("6.1 Missões"))
    story.append(bullets([
        "Cadastrar com código do voo/chamado, contratante, período, rota e tipo de operação.",
        "Regra operacional: missão válida é consolidada por identificador + contratante; não deve ser tratada por trecho isolado.",
        "Vincule corretamente os tripulantes participantes para refletir no cálculo.",
    ]))
    story.append(subsection("6.2 Pernoites"))
    story.append(bullets([
        "Informe tripulante, data, missão relacionada (quando existir), tipo de pernoite e quantidade.",
        "Diferença crítica: cobertura de base x operacional comum.",
        "Impacto: pernoite elegível entra na produtividade conforme regra parametrizada.",
    ]))
    story.append(subsection("6.3 Gestão de bases"))
    story.append(bullets([
        "Permite visão geográfica e operacional da distribuição de tripulantes.",
        "Suporta acompanhamento por status e histórico de movimentação.",
        "Use para identificar concentração de risco por base.",
    ]))

    story.append(section("7. Habilitações e vencimentos"))
    story.append(
        p(
            "O sistema classifica vencimentos automaticamente por criticidade com base nos dias restantes. "
            "Essa classificação é reaproveitada em listas, consolidado e painel TV."
        )
    )
    status_table = Table(
        [
            ["Regra", "Interpretação operacional"],
            ["Mais de 90 dias", "Em dia (verde)"],
            ["Até 90 dias", "Atenção inicial (amarelo)"],
            ["Até 60 dias", "Atenção elevada (laranja)"],
            ["Até 30 dias", "Risco alto (vermelho)"],
            ["Até 15 dias", "Crítico (vermelho pulsante)"],
            ["Vencida", "Ação imediata (destaque máximo)"],
            ["Sem data", "Neutro / sem vencimento informado"],
        ],
        colWidths=[60 * mm, 120 * mm],
    )
    status_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(status_table)
    story.append(Spacer(1, 8))
    story.append(bullets([
        "Para tripulantes com múltiplas habilitações, o sistema destaca o vencimento mais crítico.",
        "Erros comuns: data de vencimento ausente, data inválida e treinamento sem vínculo correto.",
    ]))

    story.append(PageBreak())
    story.append(section("8. Bônus / produtividade / bonificação"))
    story.append(
        p(
            "A produtividade mensal é calculada por competência (AAAA-MM) em engine centralizada. "
            "O fechamento sempre compara piso mínimo versus produtividade apurada."
        )
    )
    story.append(subsection("8.1 Conceitos-chave"))
    story.append(bullets([
        "Competência: mês de apuração.",
        "Categoria operacional: A, B ou N/A.",
        "Função: comandante, copiloto ou outro.",
        "Piso mínimo: garantia mensal por categoria/função, quando aplicável.",
        "Missão válida: consolidada por chave operacional e contratante.",
        "Pernoite elegível: conforme tipo e parâmetro da regra.",
    ]))
    story.append(subsection("8.2 Parcela de cálculo"))
    story.append(bullets([
        "Missões válidas × valor por missão.",
        "Pernoites cobertura × valor de cobertura.",
        "Pernoites operacionais elegíveis × valor parametrizado.",
        "Adicionais: SDEA, instrutor, checador e excepcional (quando elegível).",
    ]))
    story.append(subsection("8.3 Regra final"))
    story.append(p("Fórmula: valor_final_mes = max(piso_minimo_mensal, total_produtividade)."))
    story.append(subsection("8.4 Exemplo didático"))
    story.append(
        bullets([
            "Exemplo: comandante categoria A com 4 missões, 2 pernoites cobertura e SDEA ativo.",
            "A engine calcula cada parcela separadamente, soma produtividade e compara com piso.",
            "Se produtividade superar piso, critério final = produtividade apurada.",
            "Se produtividade ficar abaixo, critério final = piso mínimo.",
        ])
    )
    story.append(subsection("8.5 Erros comuns que afetam bônus"))
    story.append(bullets([
        "Missão duplicada por lançamento operacional incorreto.",
        "Pernoite lançado no tipo errado.",
        "Categoria/função desatualizada no cadastro do tripulante.",
        "Competência consultada diferente da competência lançada.",
    ]))

    story.append(section("9. Relatórios"))
    story.append(subsection("9.1 Relatório individual"))
    story.append(bullets([
        "Mostra memória de cálculo completa por tripulante e competência.",
        "Use para auditoria de fechamento e conferência de parcelas.",
    ]))
    story.append(subsection("9.2 Relatório geral"))
    story.append(bullets([
        "Consolida toda a equipe por competência com filtros por base, função, categoria e nome.",
        "Permite ordenar por valor final, produtividade, base e nome.",
    ]))
    story.append(subsection("9.3 Consolidado de habilitações"))
    story.append(bullets([
        "Agrupa habilitações por tripulante e destaca criticidade de vencimento.",
        "Permite exportar CSV e emitir PDF oficial do consolidado.",
    ]))

    story.append(section("10. PDFs e documentos gerados"))
    story.append(bullets([
        "Consolidado de habilitações: PDF oficial server-side para uso institucional.",
        "CSV: exportação analítica para tratamento externo.",
        "Antes de compartilhar, validar filtros aplicados, data de emissão e totais de resumo.",
    ]))

    story.append(section("11. Painéis TV e dashboards gerenciais"))
    story.append(bullets([
        "Painel TV de vencimentos: monitoramento contínuo de criticidade com alertas e ranking.",
        "Painel TV de produtividade: leitura executiva da competência mensal.",
        "Uso recomendado: tela dedicada em operação, com atualização automática e sem interação constante.",
        "Interpretar primeiro os blocos críticos/vencidos para priorizar ação.",
    ]))

    story.append(section("12. Usuários e permissões"))
    story.append(bullets([
        "Cadastro de usuário define identidade de acesso.",
        "Permissões por aba/subaba controlam visualização e ação (criar, editar, excluir, consultar).",
        "O backend valida autorização, não apenas o menu.",
        "Boa prática: princípio do menor privilégio (liberar só o necessário).",
    ]))

    story.append(section("13. Boas práticas operacionais"))
    story.append(bullets([
        "Revisar cadastros-base semanalmente.",
        "Conferir missões/pernoites antes do fechamento mensal.",
        "Validar vencimentos críticos diariamente.",
        "Revisar permissões de usuários em mudanças de função.",
        "Conferir relatórios e PDFs antes de distribuição oficial.",
    ]))

    story.append(section("14. Solução de problemas"))
    story.append(subsection("14.1 Cenários comuns"))
    story.append(bullets([
        "Valor de produtividade zerado: verificar lançamentos de missão/pernoite e competência.",
        "Relatório divergente: validar filtros e cadastro de categoria/função.",
        "Menu não aparece: verificar permissões do usuário.",
        "Sem envio de e-mail: validar destinatários ativos, provider configurado e existência de itens elegíveis.",
        "Painel sem dados: revisar consistência de cadastro e filtros de base/competência.",
    ]))

    story.append(section("15. Glossário"))
    story.append(bullets([
        "Competência: período mensal de apuração (AAAA-MM).",
        "Missão: operação consolidada por chave operacional/contratante.",
        "Pernoite: estadia operacional registrada por tipo.",
        "Cobertura de base: pernoite elegível específico para cobertura operacional.",
        "Categoria operacional: classe de regra (A, B, N/A).",
        "Piso mínimo: valor garantido de fechamento mensal.",
        "Produtividade: soma das parcelas variáveis e adicionais.",
        "Habilitação: requisito técnico com vencimento monitorado.",
        "Dashboard: visão executiva de indicadores.",
        "Painel TV: tela contínua para monitoramento operacional à distância.",
        "Permissão: autorização de acesso por módulo/ação.",
    ]))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Fim do manual. Documento oficial para treinamento, consulta e operação diária.",
            ParagraphStyle("ManualEnd", parent=STYLES["ManualBody"], alignment=1, textColor=colors.HexColor("#334155")),
        )
    )

    return story


def build_pdf(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=22 * mm,
        bottomMargin=16 * mm,
        title="Manual de Usuário Operacional",
        author="Treinamentos Brasil vida",
        subject="Documentação oficial de uso do sistema",
    )
    doc.build(build_manual(), onFirstPage=build_header_footer, onLaterPages=build_header_footer)


if __name__ == "__main__":
    STYLES = getSampleStyleSheet()
    STYLES.add(ParagraphStyle("ManualTitle", parent=STYLES["Heading1"], fontName="Helvetica-Bold", fontSize=24, leading=30, textColor=colors.HexColor("#0f172a")))
    STYLES.add(ParagraphStyle("ManualSubtitle", parent=STYLES["Normal"], fontName="Helvetica", fontSize=12, leading=16, textColor=colors.HexColor("#475569"), spaceAfter=12))
    STYLES.add(ParagraphStyle("ManualSection", parent=STYLES["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#0f172a"), spaceBefore=8, spaceAfter=6))
    STYLES.add(ParagraphStyle("ManualSubsection", parent=STYLES["Heading3"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1e293b"), spaceBefore=6, spaceAfter=4))
    STYLES.add(ParagraphStyle("ManualBody", parent=STYLES["Normal"], fontName="Helvetica", fontSize=9.6, leading=13.4, textColor=colors.HexColor("#334155")))

    build_pdf(OUTPUT_FILE)
    print(f"Manual gerado em: {OUTPUT_FILE}")
