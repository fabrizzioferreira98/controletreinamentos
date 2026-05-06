from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import textwrap
from dataclasses import dataclass, field
from pathlib import Path


PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0
MARGIN_X = 54.0
MARGIN_Y = 56.0
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)
LINE_SPACING = 1.35

BG = (0.06, 0.08, 0.14)
SURFACE = (0.10, 0.13, 0.20)
TEXT = (0.92, 0.94, 0.97)
MUTED = (0.68, 0.72, 0.80)
ACCENT = (0.78, 0.12, 0.23)
ACCENT_2 = (0.14, 0.31, 0.74)
SUCCESS = (0.26, 0.74, 0.42)
WARNING = (0.90, 0.68, 0.19)


def pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass
class Page:
    commands: list[str] = field(default_factory=list)
    number: int = 1

    def rect(self, x: float, y: float, w: float, h: float, color: tuple[float, float, float]):
        r, g, b = color
        self.commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float, color: tuple[float, float, float]):
        r, g, b = color
        self.commands.append(
            f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def text(self, x: float, y: float, text: str, *, font: str = "F1", size: float = 12, color=TEXT):
        r, g, b = color
        self.commands.append(
            f"BT /{font} {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ({pdf_escape(text)}) Tj ET"
        )


class PDFBuilder:
    def __init__(self, title: str, subtitle: str, *, accent=ACCENT, accent_2=ACCENT_2):
        self.title = title
        self.subtitle = subtitle
        self.accent = accent
        self.accent_2 = accent_2
        self.pages: list[Page] = []
        self.page = None
        self.cursor_y = 0.0
        self.section_page_starts: list[tuple[str, int]] = []

    def new_page(self):
        page = Page(number=len(self.pages) + 1)
        page.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, BG)
        page.rect(0, PAGE_HEIGHT - 30, PAGE_WIDTH, 30, self.accent_2)
        page.rect(0, 0, PAGE_WIDTH, 20, self.accent)
        page.rect(MARGIN_X, PAGE_HEIGHT - 98, 120, 20, self.accent)
        page.line(MARGIN_X, PAGE_HEIGHT - 110, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 110, 1.2, (0.22, 0.26, 0.35))
        page.text(MARGIN_X + 10, PAGE_HEIGHT - 93, self.title.upper(), font="F2", size=9, color=(1.0, 1.0, 1.0))
        page.text(MARGIN_X, PAGE_HEIGHT - 70, self.title, font="F2", size=12, color=TEXT)
        page.text(PAGE_WIDTH - MARGIN_X - 24, PAGE_HEIGHT - 70, f"{page.number:02d}", font="F2", size=12, color=MUTED)
        page.text(MARGIN_X, 30, self.subtitle, font="F3", size=9, color=MUTED)
        page.line(MARGIN_X, 44, PAGE_WIDTH - MARGIN_X, 44, 1, (0.22, 0.26, 0.35))
        self.pages.append(page)
        self.page = page
        self.cursor_y = PAGE_HEIGHT - 140

    def ensure_space(self, height_needed: float):
        if self.page is None or self.cursor_y - height_needed < MARGIN_Y:
            self.new_page()

    def add_cover(self, eyebrow: str, audience: str):
        page = Page(number=1)
        page.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, BG)
        page.rect(0, PAGE_HEIGHT - 240, PAGE_WIDTH, 240, self.accent_2)
        page.rect(0, 0, PAGE_WIDTH, 14, self.accent)
        page.rect(0, 200, PAGE_WIDTH, 1.5, (0.18, 0.22, 0.30))
        page.rect(MARGIN_X, PAGE_HEIGHT - 120, 148, 26, self.accent)
        page.line(MARGIN_X, PAGE_HEIGHT - 250, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 250, 2.2, (0.35, 0.39, 0.50))
        page.text(MARGIN_X + 14, PAGE_HEIGHT - 111, eyebrow, font="F2", size=12, color=(0.98, 0.98, 1.0))
        page.text(MARGIN_X, PAGE_HEIGHT - 196, self.title, font="F2", size=34, color=(1.0, 1.0, 1.0))
        page.text(MARGIN_X, PAGE_HEIGHT - 234, audience, font="F3", size=15, color=(0.92, 0.95, 1.0))
        page.text(
            MARGIN_X,
            PAGE_HEIGHT - 334,
            "Manual oficial do Treinamentos Brasil vida para uso em ambiente operacional regulado.",
            size=17,
            color=TEXT,
        )
        page.text(
            MARGIN_X,
            PAGE_HEIGHT - 366,
            "Conteúdo estruturado para consulta, treinamento interno e padronização da operação.",
            size=12,
            color=MUTED,
        )
        page.rect(MARGIN_X, 152, PAGE_WIDTH - (MARGIN_X * 2), 136, SURFACE)
        page.rect(MARGIN_X, 152, 10, 136, self.accent)
        page.text(MARGIN_X + 24, 258, "Identidade visual", font="F2", size=14, color=TEXT)
        page.text(
            MARGIN_X + 24,
            232,
            "Tema escuro, hierarquia tipográfica inspirada em IBM Plex e foco em leitura de documentos técnicos.",
            size=11,
            color=MUTED,
        )
        page.text(MARGIN_X + 24, 206, "Produto: Treinamentos Brasil vida · Marca operacional: Brasilvida", size=11, color=MUTED)
        page.text(MARGIN_X + 24, 180, "Documento gerado a partir do código-fonte e das regras ativas do sistema.", size=11, color=MUTED)
        page.text(MARGIN_X, 74, "Versão documental: 1.0 · Emissão: 22/03/2026", size=10, color=MUTED)
        page.text(MARGIN_X, 54, "Uso interno e institucional.", size=10, color=MUTED)
        self.pages.append(page)
        self.page = None

    def add_toc(self, entries: list[str]):
        self.new_page()
        self.section_title("Sumário")
        self.paragraph(
            "Este manual foi organizado para leitura sequencial, mas cada seção também pode ser consultada de forma independente conforme a necessidade do público.",
            size=12,
            color=MUTED,
        )
        for index, entry in enumerate(entries, start=1):
            self.ensure_space(30)
            self.page.rect(MARGIN_X, self.cursor_y - 10, CONTENT_WIDTH, 26, SURFACE if index % 2 else BG)
            self.page.rect(MARGIN_X, self.cursor_y - 10, 6, 26, self.accent if index % 2 else self.accent_2)
            self.page.text(MARGIN_X + 16, self.cursor_y, f"{index:02d}. {entry}", size=12, color=TEXT)
            self.cursor_y -= 32
        self.cursor_y -= 10

    def section_title(self, title: str):
        self.ensure_space(58)
        self.section_page_starts.append((title, self.page.number))
        self.page.rect(MARGIN_X, self.cursor_y - 8, CONTENT_WIDTH, 34, SURFACE)
        self.page.rect(MARGIN_X, self.cursor_y - 8, 12, 34, self.accent_2)
        self.page.text(MARGIN_X + 22, self.cursor_y + 2, title, font="F2", size=17, color=(1.0, 1.0, 1.0))
        self.cursor_y -= 44

    def subsection(self, title: str):
        self.ensure_space(36)
        self.page.text(MARGIN_X, self.cursor_y, title, font="F2", size=13, color=TEXT)
        self.page.line(MARGIN_X, self.cursor_y - 6, PAGE_WIDTH - MARGIN_X, self.cursor_y - 6, 1, (0.22, 0.26, 0.35))
        self.cursor_y -= 24

    def paragraph(self, text: str, *, size: float = 11.5, color=TEXT):
        width_factor = 0.52 if size <= 12 else 0.50
        wrap_chars = max(42, int(CONTENT_WIDTH / (size * width_factor)))
        for raw_paragraph in text.split("\n"):
            lines = textwrap.wrap(raw_paragraph, wrap_chars) or [""]
            needed = len(lines) * size * LINE_SPACING + 8
            self.ensure_space(needed)
            for line in lines:
                self.page.text(MARGIN_X, self.cursor_y, line, size=size, color=color)
                self.cursor_y -= size * LINE_SPACING
            self.cursor_y -= 7

    def bullets(self, items: list[str], *, size: float = 11.5):
        for item in items:
            wrap_chars = max(38, int((CONTENT_WIDTH - 20) / (size * 0.52)))
            lines = textwrap.wrap(item, wrap_chars) or [""]
            needed = len(lines) * size * LINE_SPACING + 6
            self.ensure_space(needed)
            self.page.text(MARGIN_X, self.cursor_y, "-", font="F2", size=size, color=self.accent)
            self.page.text(MARGIN_X + 16, self.cursor_y, lines[0], size=size, color=TEXT)
            self.cursor_y -= size * LINE_SPACING
            for line in lines[1:]:
                self.page.text(MARGIN_X + 16, self.cursor_y, line, size=size, color=TEXT)
                self.cursor_y -= size * LINE_SPACING
            self.cursor_y -= 5

    def callout(self, title: str, lines: list[str], tone: str = "info"):
        color = {"info": self.accent_2, "warning": WARNING, "success": SUCCESS}.get(tone, self.accent_2)
        body_height = 36 + len(lines) * 16
        self.ensure_space(body_height + 12)
        self.page.rect(MARGIN_X, self.cursor_y - body_height + 8, CONTENT_WIDTH, body_height, SURFACE)
        self.page.rect(MARGIN_X, self.cursor_y - body_height + 8, 10, body_height, color)
        self.page.text(MARGIN_X + 22, self.cursor_y - 10, title, font="F2", size=12.5, color=TEXT)
        y = self.cursor_y - 34
        for line in lines:
            self.page.text(MARGIN_X + 22, y, line, size=10.8, color=MUTED)
            y -= 16
        self.cursor_y -= body_height + 12

    def build(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        font1_id = 1
        font2_id = 2
        font3_id = 3
        font4_id = 4
        pages_id = 5
        first_content_id = 6
        page_count = len(self.pages)
        content_ids = [first_content_id + (index * 2) for index in range(page_count)]
        page_ids = [first_content_id + (index * 2) + 1 for index in range(page_count)]
        catalog_id = first_content_id + (page_count * 2)

        max_object_id = catalog_id
        objects: list[bytes] = [b""] * max_object_id
        objects[font1_id - 1] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
        objects[font2_id - 1] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
        objects[font3_id - 1] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>"
        objects[font4_id - 1] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"

        pages_kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects[pages_id - 1] = f"<< /Type /Pages /Count {page_count} /Kids [{pages_kids}] >>".encode("latin-1")

        for index, page in enumerate(self.pages):
            stream = "\n".join(page.commands).encode("latin-1", "replace")
            content_id = content_ids[index]
            page_id = page_ids[index]
            objects[content_id - 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
            objects[page_id - 1] = (
                f"<< /Type /Page /Parent {pages_id} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R /F3 {font3_id} 0 R /F4 {font4_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("latin-1")

        objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")

        pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("latin-1"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")

        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects)+1}\n".encode("latin-1"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
                "latin-1"
            )
        )
        output_path.write_bytes(pdf)


def generate_developer_manual(output_dir: Path):
    builder = PDFBuilder("Treinamentos Brasil vida", "Manual do Desenvolvedor", accent=(0.78, 0.12, 0.23), accent_2=(0.14, 0.31, 0.74))
    builder.add_cover("MANUAL TÉCNICO", "Arquitetura, dados, regras de negócio e manutenção")
    builder.add_toc(
        [
            "Visão arquitetural e stack",
            "Estrutura do repositório",
            "Modelo de dados e relacionamentos",
            "Regras de negócio e cálculo de status",
            "Notificações por e-mail",
            "Autenticação, autorização e auditoria",
            "Manutenção, deploy e extensão do código",
        ]
    )
    builder.section_title("1. Visão arquitetural e stack")
    builder.paragraph(
        "O Treinamentos Brasil vida é um sistema administrativo interno desenvolvido em Flask com renderização server-side por Jinja2 e persistência em PostgreSQL via psycopg2. A aplicação adota arquitetura monolítica leve, com app factory, rotas HTTP organizadas por domínio e um módulo específico para Gestão de Bases."
    )
    builder.bullets(
        [
            "Framework principal: Flask 3.1.3 com Flask-Login para sessão autenticada e Flask-WTF para CSRF.",
            "Persistência: PostgreSQL acessado por pool ThreadedConnectionPool, sem ORM, com SQL explícito e migrations idempotentes embutidas no bootstrap.",
            "Frontend: templates Jinja2, CSS próprio e JavaScript pontual para interações assíncronas, com frontend oficial servido localmente quando ativado.",
            "Deploy: Waitress + Caddy em servidor local Windows, com PostgreSQL no host e operação self-hosted.",
        ]
    )
    builder.callout(
        "Ponto de atenção",
        [
            "O repositório ainda usa migrations automáticas no startup.",
            "Para ambientes altamente regulados, recomenda-se evoluir para migrations versionadas e pipeline de homologação explícito.",
        ],
        tone="warning",
    )

    builder.section_title("2. Estrutura do repositório")
    builder.bullets(
        [
            "backend/src/controle_treinamentos/compat/http_entrypoints/index.py: entrypoint HTTP de compatibilidade para inicialização segura.",
            "backend/src/controle_treinamentos/compat/http_entrypoints/cron.py: endpoint protegido por CRON_SECRET para disparo de rotinas agendadas.",
            "backend/src/controle_treinamentos/__init__.py: app factory, segurança, cookies, CSP, registro de blueprint e bootstrap do app.",
            "backend/src/controle_treinamentos/routes.py: rotas centrais de dashboard, tripulantes, treinamentos, equipamentos, tipos, usuários e notificações.",
            "backend/src/controle_treinamentos/bases.py: blueprint de Gestão de Bases com mapa, pilotos e histórico operacional.",
            "backend/src/controle_treinamentos/db.py: schema, seed de bases, índices, conexão e migrations idempotentes.",
            "backend/src/controle_treinamentos/services.py: regras reutilizáveis de datas, vencimento e ordenação.",
            "backend/src/controle_treinamentos/mailer.py: construção do consolidado de e-mail e envio SMTP.",
            "backend/src/controle_treinamentos/audit.py: trilha de auditoria imutável para eventos críticos.",
        ]
    )

    builder.section_title("3. Modelo de dados e relacionamentos")
    builder.paragraph("Entidades principais implementadas no banco:")
    builder.bullets(
        [
            "usuarios: controla autenticação, perfil (operador ou gestora), status ativo e autoria das ações.",
            "tripulantes: cadastro operacional principal, com nome, CPF, licença ANAC, base textual, status textual e observações.",
            "equipamentos: ativos utilizados em treinamentos.",
            "tipos_treinamento: catálogo com periodicidade em meses e flag ativa.",
            "treinamentos: fato central que relaciona tripulante, tipo, equipamento e datas de realização/vencimento.",
            "notificacoes_email: destinatários ativos do consolidado diário.",
            "bases: cadastro geográfico das bases operacionais com nome, UF e coordenadas.",
            "pilotos: espelho operacional do tripulante vinculado a uma base via tripulante_id.",
            "historico_status_piloto: trilha imutável de status e movimentações entre bases.",
            "auditoria_eventos: trilha transversal para create, update e delete de entidades críticas.",
        ]
    )
    builder.callout(
        "Relacionamento-chave",
        [
            "A correção estrutural mais importante foi a criação do vínculo pilotos.tripulante_id.",
            "Com isso, Gestão de Bases e cadastro principal deixam de ser fontes independentes de verdade.",
        ],
        tone="success",
    )

    builder.section_title("4. Regras de negócio e cálculo de status")
    builder.subsection("Cálculo do status de treinamentos")
    builder.bullets(
        [
            "Sem informação: data_vencimento ausente.",
            "Vencido: data_vencimento anterior ao business_today().",
            "A vencer: data_vencimento dentro da janela de até 30 dias.",
            "Regular: data_vencimento acima de 30 dias.",
        ]
    )
    builder.paragraph(
        "A data de referência foi centralizada em business_today(), com timezone America/Sao_Paulo. Isso reduz divergências entre dashboard, filtros, relatório individual e notificação por e-mail."
    )
    builder.subsection("Registro de treinamentos")
    builder.bullets(
        [
            "Modo automático: calcula vencimento a partir da data de realização e da periodicidade do tipo.",
            "Modo manual: exige data de vencimento explícita.",
            "A data de realização não pode ser posterior à data de vencimento.",
            "Referências a tripulante, equipamento e tipo são validadas no servidor.",
        ]
    )
    builder.subsection("Gestão de bases")
    builder.bullets(
        [
            "Novo piloto operacional é criado a partir de um tripulante já existente.",
            "Mudança de status grava histórico em historico_status_piloto e sincroniza o tripulante ligado.",
            "Movimentação entre bases grava base anterior, base nova, autor e observação opcional.",
        ]
    )

    builder.section_title("5. Notificações por e-mail")
    builder.paragraph(
        "A rotina atual monta um consolidado com três blocos: vencidos, vencendo em até 7 dias e vencendo entre 8 e 30 dias. O processamento ocorre no backend, com destinatários vindos da tabela notificacoes_email e envio via SMTP configurável."
    )
    builder.bullets(
        [
            "Trigger manual: tela de Destinatários de E-mail.",
            "Trigger automático: backend/src/controle_treinamentos/compat/http_entrypoints/cron.py com Authorization Bearer CRON_SECRET.",
            "Persistência operacional: sistema_controle mantém notification_last_run e notification_last_sent_at.",
            "Resultado estruturado: NotificationResult diferencia no_recipients, no_due_items, smtp_not_configured, smtp_error e sent.",
        ]
    )
    builder.callout(
        "Sobre os gatilhos 90/60/30",
        [
            "O produto já possui filtros de janela em 90/60/30 dias na interface de treinamentos.",
            "Para adotar notificações segmentadas em 90/60/30, a evolução deve ocorrer em build_notification_blocks() e no template de preview.",
        ],
        tone="warning",
    )

    builder.section_title("6. Autenticação, autorização e auditoria")
    builder.bullets(
        [
            "Flask-Login mantém current_user como fonte principal da sessão autenticada.",
            "role_required() protege recursos administrativos.",
            "Cookies de sessão e remember possuem HttpOnly, SameSite=Lax e Secure em produção.",
            "Há limitação de tentativas de login por janela temporal e lockout temporário.",
            "A trilha de auditoria grava payload anterior, payload novo, autor, data/hora e observação opcional.",
        ]
    )

    builder.section_title("7. Manutenção, deploy e extensão do código")
    builder.bullets(
        [
            "Para manutenção, priorize a centralização de regras reutilizáveis em services.py e audit.py antes de espalhar lógica em views.",
            "Ao criar nova entidade crítica, adicione validação server-side, auditoria, feedback visual e testes de fumaça com test_client.",
            "Antes de publicar em produção ou homologação, valide SECRET_KEY, DATABASE_URL, CRON_SECRET e variáveis SMTP no servidor local.",
            "Para ampliar Gestão de Bases, mantenha tripulantes como cadastro mestre e use tripulante_id como vínculo obrigatório.",
            "Para ambiente regulado, planeje a próxima iteração com migrations versionadas, observabilidade estruturada e suíte automatizada com PostgreSQL de homologação.",
        ]
    )
    builder.callout(
        "Checklist de extensão segura",
        [
            "1. Defina a regra de negócio em services.py.",
            "2. Garanta autorização explícita por perfil.",
            "3. Registre auditoria de create/update/delete.",
            "4. Atualize README, .env.example e documentação de operação.",
        ],
        tone="success",
    )
    builder.build(output_dir / "manual-desenvolvedor-aerotrack.pdf")


def generate_user_manual(output_dir: Path):
    builder = PDFBuilder("Treinamentos Brasil vida", "Manual do Usuário", accent=(0.20, 0.58, 0.89), accent_2=(0.16, 0.42, 0.72))
    builder.add_cover("MANUAL OPERACIONAL", "Uso diário para operadoras e gestoras")
    builder.add_toc(
        [
            "Acesso ao sistema e perfis",
            "Dashboard e interpretação dos indicadores",
            "Cadastro de tripulantes",
            "Equipamentos, tipos e treinamentos",
            "Relatório individual por tripulante",
            "Gestão de bases e pilotos",
            "Destinatários e notificações por e-mail",
            "Boas práticas de uso",
        ]
    )
    builder.section_title("1. Acesso ao sistema e perfis")
    builder.bullets(
        [
            "Perfil operador: consulta dados, registra e edita treinamentos, altera status operacional em Gestão de Bases quando autorizado pela função.",
            "Perfil gestora: além das consultas, pode manter cadastros mestres, usuários, destinatários de e-mail e movimentações administrativas.",
            "Ao abrir o sistema, informe login e senha na tela inicial e clique em Entrar no sistema.",
        ]
    )
    builder.callout(
        "Boas práticas de acesso",
        [
            "Nunca compartilhe sua senha.",
            "Em caso de mensagem de bloqueio por tentativas, aguarde o período de segurança e tente novamente.",
        ],
        tone="warning",
    )

    builder.section_title("2. Dashboard e interpretação dos indicadores")
    builder.paragraph(
        "O dashboard mostra a visão consolidada da operação: total de tripulantes, equipamentos, tipos e treinamentos, além do resumo por status e da lista dos itens mais críticos."
    )
    builder.bullets(
        [
            "Vencido: treinamento com data de vencimento já ultrapassada.",
            "A vencer: treinamento dentro da janela de atenção de 30 dias.",
            "Regular: treinamento ainda fora da janela crítica.",
            "Sem informação: treinamento sem data de vencimento cadastrada.",
        ]
    )

    builder.section_title("3. Cadastro de tripulantes")
    builder.paragraph(
        "Na aba Tripulantes é possível consultar, filtrar e abrir o relatório individual. Gestoras também podem cadastrar, editar e excluir registros quando não houver treinamentos vinculados."
    )
    builder.bullets(
        [
            "Campos principais: nome, CPF, código/licença ANAC, base, status e observações.",
            "Use o campo de observações para registrar informações complementares operacionais.",
            "Em filtros, é possível buscar por nome, status e base.",
            "Se o tripulante estiver vinculado à Gestão de Bases, alterações relevantes de nome/base/status são sincronizadas.",
        ]
    )

    builder.section_title("4. Equipamentos, tipos e treinamentos")
    builder.subsection("Equipamentos")
    builder.paragraph("Cadastre cada aeronave, equipamento ou recurso associado aos treinamentos. Equipamentos inativos podem permanecer no histórico sem serem usados em novos lançamentos.")
    builder.subsection("Tipos de treinamento")
    builder.paragraph("Cadastre o nome do treinamento e a periodicidade em meses. Essa periodicidade alimenta o cálculo automático do vencimento.")
    builder.subsection("Treinamentos")
    builder.bullets(
        [
            "Selecione tripulante, equipamento (quando aplicável) e tipo de treinamento.",
            "Informe a data de realização e escolha entre cálculo automático ou data de vencimento manual.",
            "O sistema rejeita datas incoerentes, como realização posterior ao vencimento.",
            "Após salvar, o registro aparece imediatamente nas listagens, filtros e relatório individual.",
        ]
    )
    builder.callout(
        "Interpretação prática",
        [
            "Ao cadastrar um treinamento com periodicidade de 12 meses em modo automático, o sistema calcula o vencimento automaticamente.",
            "Use o modo manual apenas quando houver exigência documental específica.",
        ],
        tone="info",
    )

    builder.section_title("5. Relatório individual por tripulante")
    builder.bullets(
        [
            "Na lista de tripulantes, clique em Relatório.",
            "O relatório organiza os treinamentos do tripulante por criticidade e vencimento.",
            "A página pode ser impressa diretamente pelo navegador para compor dossiês ou checagens operacionais.",
            "Se o tripulante ainda não possuir treinamentos, o relatório exibe um estado vazio orientativo.",
        ]
    )

    builder.section_title("6. Gestão de bases e pilotos")
    builder.paragraph(
        "A aba Gestão de Bases exibe um mapa do Brasil com cards flutuantes por base, contagem total de pilotos e distribuição por status. Ao clicar em Ver pilotos, abre-se um painel lateral com a composição da base."
    )
    builder.bullets(
        [
            "Status disponíveis: Ativo, Folga, Férias, Atestado, Afastado e Treinamento.",
            "Gestoras podem adicionar piloto operacional a partir de um tripulante já cadastrado.",
            "O painel lateral permite alterar status, mover base e consultar histórico cronológico.",
            "Os filtros por status atualizam o mapa sem recarregar a página.",
        ]
    )

    builder.section_title("7. Destinatários e notificações por e-mail")
    builder.paragraph(
        "Na área de Destinatários de E-mail, gestoras definem quem recebe o consolidado diário de vencimentos e podem fazer um disparo manual quando necessário."
    )
    builder.bullets(
        [
            "Cadastre um e-mail por linha lógica de destinatário e marque como ativo.",
            "O resumo da tela mostra destinatários ativos, último envio, última rotina e estado do SMTP.",
            "O preview apresenta exatamente o conteúdo do consolidado que será enviado.",
            "Se o SMTP estiver indisponível, a aplicação informa a falha sem derrubar o restante do sistema.",
        ]
    )

    builder.section_title("8. Boas práticas de uso")
    builder.bullets(
        [
            "Preencha bases e status de forma padronizada para preservar a consistência dos filtros.",
            "Evite usar observações para guardar dados obrigatórios que já possuem campo próprio.",
            "Revise regularmente os treinamentos a vencer, principalmente antes de movimentações operacionais.",
            "Após adicionar o sistema à tela inicial do iPhone, apague atalhos antigos se o ícone não atualizar imediatamente.",
        ]
    )
    builder.build(output_dir / "manual-usuario-aerotrack.pdf")


def generate_marketing_manual(output_dir: Path):
    builder = PDFBuilder("Treinamentos Brasil vida", "Manual de Marketing", accent=(0.89, 0.37, 0.16), accent_2=(0.45, 0.18, 0.58))
    builder.add_cover("MANUAL COMERCIAL", "Posicionamento, valor e discurso do produto")
    builder.add_toc(
        [
            "Visão geral do produto",
            "Proposta de valor",
            "Principais funcionalidades",
            "Benefícios operacionais",
            "Casos de uso",
            "Diferenciais competitivos",
            "Mensagens-chave para apresentação comercial",
        ]
    )
    builder.section_title("1. Visão geral do produto")
    builder.paragraph(
        "Treinamentos Brasil vida é uma plataforma de gestão operacional voltada ao controle de habilitações, treinamentos, distribuição por bases e alertas preventivos. O produto nasceu para substituir controles frágeis em planilhas por uma visão única, auditável e sempre atualizada da prontidão operacional."
    )
    builder.callout(
        "Em uma frase",
        [
            "Treinamentos Brasil vida transforma o controle de vencimentos e movimentações operacionais em um processo centralizado, confiável e acionável.",
        ],
        tone="success",
    )

    builder.section_title("2. Proposta de valor")
    builder.bullets(
        [
            "Centraliza cadastros, treinamentos, vencimentos e distribuição por bases em um único sistema.",
            "Reduz risco operacional ao destacar rapidamente itens vencidos e próximos do vencimento.",
            "Elimina retrabalho, duplicidade e perda de contexto comum em planilhas compartilhadas.",
            "Entrega governança com trilha de auditoria e histórico de movimentações críticas.",
        ]
    )

    builder.section_title("3. Principais funcionalidades")
    builder.bullets(
        [
            "Dashboard com leitura rápida dos indicadores e dos treinamentos mais críticos.",
            "Cadastro estruturado de tripulantes, equipamentos, tipos de treinamento e usuários.",
            "Registro de treinamentos com cálculo automático ou manual de vencimento.",
            "Relatório individual por tripulante pronto para impressão e conferência operacional.",
            "Gestão de Bases com mapa interativo e status em tempo real da distribuição de pilotos.",
            "Envio de alertas por e-mail para destinatários definidos pela gestão.",
        ]
    )

    builder.section_title("4. Benefícios operacionais")
    builder.bullets(
        [
            "Centralização: uma única fonte confiável de informação para operação e gestão.",
            "Automação: redução da dependência de conferência manual de datas críticas.",
            "Velocidade de resposta: visualização imediata do que precisa de ação.",
            "Rastreabilidade: histórico de mudanças de base, status e eventos críticos.",
            "Escalabilidade: suporta crescimento da equipe e do volume de treinamentos sem virar caos operacional.",
        ]
    )

    builder.section_title("5. Casos de uso")
    builder.bullets(
        [
            "Gestão diária de vencimentos e priorização de reciclagens.",
            "Consolidação de evidências para auditorias internas e externas.",
            "Controle de distribuição por base em operações descentralizadas.",
            "Acompanhamento de afastamentos, férias, folgas e períodos de treinamento.",
            "Substituição de planilhas fragmentadas por processo padronizado com governança.",
        ]
    )

    builder.section_title("6. Diferenciais competitivos")
    builder.bullets(
        [
            "Combina gestão de treinamentos e gestão de bases no mesmo produto.",
            "Foco em operação regulada, com ênfase em consistência, histórico e autorização por perfil.",
            "Implementação enxuta, rápida de implantar e fácil de adaptar ao processo da empresa.",
            "Interface administrativa clara, com leitura imediata em desktop e boa usabilidade em mobile e tablet.",
        ]
    )

    builder.section_title("7. Mensagens-chave para apresentação comercial")
    builder.bullets(
        [
            "Treinamentos Brasil vida reduz risco operacional antes que ele vire ocorrência.",
            "Com o sistema, a gestão sai do modo reativo e passa a atuar preventivamente.",
            "O produto reduz dependência de planilhas, e-mail solto e memória operacional.",
            "A organização ganha controle, rastreabilidade e velocidade sem complexidade de implantação.",
        ]
    )
    builder.callout(
        "Pitch curto",
        [
            "Treinamentos Brasil vida é a plataforma que organiza a prontidão operacional da equipe em um único lugar.",
            "Ela centraliza treinamentos, vencimentos, bases e alertas para que a gestão aja antes do problema acontecer.",
        ],
        tone="info",
    )
    builder.build(output_dir / "manual-marketing-aerotrack.pdf")


def main():
    output_dir = Path(__file__).resolve().parent
    generate_developer_manual(output_dir)
    generate_user_manual(output_dir)
    generate_marketing_manual(output_dir)
    print(f"PDFs gerados em: {output_dir}")


if __name__ == "__main__":
    main()
