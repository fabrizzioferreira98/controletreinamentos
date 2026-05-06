from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
ROUTE_REGISTRY = FRONTEND_SRC / "app" / "route-registry.js"
SHELL_NAVIGATION = FRONTEND_SRC / "shell" / "navigation.js"
PAGE_MODULE = FRONTEND_SRC / "pages-financeiro.js"
FEATURE_PAGE = FRONTEND_SRC / "features" / "financeiro" / "missoes-page.js"
SERVICE = FRONTEND_SRC / "services" / "financeiro-missoes-api.js"
CSS_FILE = FRONTEND_SRC / "app.css"
VISUAL_AUDIT_SCRIPT = ROOT / "tools" / "screenshots" / "capture_financeiro_missoes_visual_audit.py"

FINANCEIRO_MISSOES_ROUTE = "#/financeiro/missoes"
FINANCEIRO_MISSOES_API = "/api/v1/financeiro/missoes"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_js_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//.*", "", source)


def test_financeiro_missoes_operacionais_route_remains_technical_without_operational_nav_entry():
    route_registry = _read(ROUTE_REGISTRY)
    navigation = _read(SHELL_NAVIGATION)
    page_module = _read(PAGE_MODULE)

    assert route_registry.count(f'"{FINANCEIRO_MISSOES_ROUTE}"') == 1
    assert f'"{FINANCEIRO_MISSOES_ROUTE}"' in route_registry
    assert 'moduleName: "financeiro"' in route_registry
    assert 'exportName: "renderFinanceiroMissoesPage"' in route_registry
    assert 'permissions: ["finance:missions:read"]' in route_registry
    assert navigation.count(f'href: "{FINANCEIRO_MISSOES_ROUTE}"') == 0
    assert f'href: "{FINANCEIRO_MISSOES_ROUTE}"' not in navigation
    assert 'label: "Lançamentos de Jornada"' in navigation
    assert 'from "./features/financeiro/missoes-page.js";' in page_module


def test_financeiro_missoes_has_single_canonical_route_owner_without_legacy_imports():
    route_registry = _read(ROUTE_REGISTRY)
    page_module = _read(PAGE_MODULE)
    feature = _read(FEATURE_PAGE)

    assert 'moduleName: "financeiro"' in route_registry
    assert 'exportName: "renderFinanceiroMissoesPage"' in route_registry
    assert page_module.count('from "./features/financeiro/missoes-page.js";') == 1
    assert page_module.count("renderFinanceiroMissoesPage as renderFinanceiroMissoesFeaturePage") == 1
    assert "export async function renderFinanceiroMissoesPage()" in feature

    forbidden_fragments = (
        "renderFinanceiroMissoesLegacy",
        "legacy-missoes",
        "missoes-legacy",
        "old-missoes",
        "oldFinanceiroMissoes",
        "MISSION_EMPTY_TITLE_COMPAT",
        "data-legacy-title",
        "fallbackMissoes",
    )
    combined = "\n".join((route_registry, page_module, feature))
    for fragment in forbidden_fragments:
        assert fragment not in combined


def test_financeiro_missoes_loading_empty_and_error_states_do_not_render_old_screen():
    feature = _read(FEATURE_PAGE)

    assert "renderPageState" in feature
    assert "Carregando Missoes Operacionais" in feature
    assert "financeiro-missoes-page" in feature
    assert "Nao foi possivel carregar Missoes Operacionais" in feature
    assert "Nenhuma missão operacional encontrada" in feature
    assert "data-legacy-title" not in feature
    assert "Nenhuma missao operacional encontrada." not in feature


def test_financeiro_missoes_service_has_preflight_and_recalculation_endpoints():
    service = _read(SERVICE)

    assert FINANCEIRO_MISSOES_API in service
    assert "cancelFinanceiroMissao" in service
    assert "/cancelar" in service
    assert "deleteFinanceiroMissao" in service
    assert "method: \"DELETE\"" in service
    assert "previewFinanceiroMissao" in service
    assert "/preview" in service
    assert "preflightFinanceiroMissaoCalculo" in service
    assert "/preflight-calculo" in service
    assert "recalculateFinanceiroMissao" in service
    assert "/recalcular" in service


def test_financeiro_missoes_cancel_service_does_not_use_recalculate_or_delete_endpoint():
    service = _read(SERVICE)
    cancel_service = service[service.index("export async function cancelFinanceiroMissao"):]
    cancel_service = cancel_service[: cancel_service.index("export async function deleteFinanceiroMissao")]

    assert "method: \"POST\"" in cancel_service
    assert "/cancelar" in cancel_service
    assert "/recalcular" not in cancel_service
    assert "method: \"DELETE\"" not in cancel_service


def test_financeiro_missoes_delete_service_uses_delete_endpoint_distinct_from_cancel():
    service = _read(SERVICE)
    delete_service = service[service.index("export async function deleteFinanceiroMissao"):]
    delete_service = delete_service[: delete_service.index("export async function recalculateFinanceiroMissao")]

    assert "method: \"DELETE\"" in delete_service
    assert "/cancelar" not in delete_service
    assert "/recalcular" not in delete_service


def test_financeiro_missoes_recalculate_flow_calls_preflight_before_post():
    feature = _read(FEATURE_PAGE)

    assert "financeMissionRecalculateButton" in feature
    assert "runMissionPreflight" in feature
    assert 'const operationKey = `recalculate:${selectedMission.id}`;' in feature
    assert "beginFinanceMissionOperation(operationKey, recalculateFeedback)" in feature
    assert "endFinanceMissionOperation(operationKey)" in feature
    preflight_marker = "const preflightSummary = await runMissionPreflight(selectedMission.id);"
    recalc_marker = "const result = await recalculateFinanceiroMissao(selectedMission.id);"
    assert preflight_marker in feature
    assert recalc_marker in feature
    assert feature.index(preflight_marker) < feature.index(recalc_marker)


def test_financeiro_missoes_inline_preview_uses_safe_debounced_preview_endpoint():
    feature = _read(FEATURE_PAGE)
    service = _read(SERVICE)

    for expected in (
        "Prévia financeira",
        "Informe data, aeronave, tripulação e categoria operacional para gerar a prévia financeira.",
        "Calculando prévia financeira...",
        "Prévia disponível",
        "Pendente de dados",
        "Bloqueada por inconsistência",
        "Erro de cálculo",
        "Recalculada com sucesso",
        "previewFinanceiroMissao",
        "PREVIEW_DEBOUNCE_MS",
        "previewRequestSeq",
        "lastPreviewSignature",
        "setupFinanceMissionPreview",
        "data-finance-preview-card",
        'form.dataset.financeOperationState === "saving"',
    ):
        assert expected in feature

    assert "previewFinanceiroMissao" in service
    assert "method: \"POST\"" in service
    preview_service = service[service.index("export async function previewFinanceiroMissao"):]
    preview_service = preview_service[: preview_service.index("export async function getFinanceiroMissao")]
    assert "/preview" in preview_service
    assert "/recalcular" not in preview_service


def test_financeiro_missoes_shows_human_preflight_block_messages():
    feature = _read(FEATURE_PAGE)

    assert "Nao e possivel recalcular porque" in feature
    assert "Recalculo bloqueado pelo preflight" in feature
    assert "Revise pendencias de parametros, vigencia e elegibilidade" in feature


def test_financeiro_missoes_exposes_operational_actions_and_filters():
    feature = _read(FEATURE_PAGE)

    for expected in (
        "Excluir missao",
        "Cancelar missao",
        "Excluir missao definitivamente?",
        "Cancelar missao operacional?",
        "financeMissionCancelButton",
        "data-finance-cancel-action",
        "Recalcular missão",
        "Ver preflight",
        "Ver calculo",
        "Ver memoria",
        "Ir para Bonificacoes",
        "#/financeiro/bonificacoes/horaria",
        "Categoria operacional",
        "Condição operacional especial",
        "Impacta cálculo financeiro",
        "Opcional. Use quando a missão tiver uma condição reconhecida que altere a bonificação, como Palmas turboélice. Em branco, o cálculo segue a regra padrão.",
        "financeMissionSpecialOperationOptions",
        "Normaliza no calculo",
        'name="calculo_status"',
        "Todos os estados de calculo",
        "busca por Cavok/chamado/contratante",
    ):
        assert expected in feature
    assert feature.count('name="operacao_especial"') == 1
    assert "Regra especial da missão" not in feature


def test_financeiro_missoes_declares_explicit_operational_workflow_states():
    feature = _read(FEATURE_PAGE)

    for expected in (
        "Nenhuma missão selecionada",
        "Fluxo de lançamento",
        "Fluxo da missão",
        "Nova missão",
        "Editando missão existente",
        "Missão salva",
        "Missão persistida",
        "Alterações ainda não salvas",
        "Rascunho de nova missão",
        "A prévia usa o rascunho alterado",
        "A prévia aparece sem criar missão ou bonificação",
        "Salvar missão cria o registro operacional",
        "Recalcular não aparece antes de a missão existir no backend",
        "Cálculo vigente atualizado",
        'data-workflow-state="missao_salva"',
        'data-workflow-state="${workflowState}"',
        'data-finance-draft-state',
        'data-finance-operation="save"',
        'data-finance-operation="recalculate"',
        'data-finance-edit-focus',
    ):
        assert expected in feature


def test_financeiro_missoes_protects_save_and_recalculate_from_double_submit():
    feature = _read(FEATURE_PAGE)

    for expected in (
        "financeMissionOperationLocks",
        "beginFinanceMissionOperation",
        "Operação em andamento. Aguarde a conclusão antes de tentar novamente.",
        'const operationKey = `save:${selectedMission?.id || "new"}`;',
        'const operationKey = `recalculate:${selectedMission.id}`;',
        'const operationKey = `${action.action}:${selectedMission.id}`;',
        'form.dataset.financeOperationState = "saving";',
        "delete form.dataset.financeOperationState;",
        "endFinanceMissionOperation(operationKey)",
    ):
        assert expected in feature


def test_financeiro_missoes_respects_rbac_for_recalculate_action():
    feature = _read(FEATURE_PAGE)

    assert 'capabilities.has("finance:missions:recalculate")' in feature
    assert "Seu perfil nao possui permissao para recalcular missoes." in feature
    assert 'selectedMission && selectedMission.status !== "cancelada" && !missionIsDeleted(selectedMission) && capabilities.has("finance:missions:recalculate")' in feature
    assert 'mission && canRecalculate && mission.status !== "cancelada" && !missionIsDeleted(mission)' in feature


def test_financeiro_missoes_cancel_flow_is_confirmed_idempotent_and_clears_active_selection():
    feature = _read(FEATURE_PAGE)

    for expected in (
        "missionDestructiveAction",
        "missionHasFinancialHistory",
        "Preserva historico financeiro e invalida o calculo vigente vinculado.",
        "Remove a missao dos fluxos operacionais comuns sem usar o cancelamento financeiro.",
        "confirmAction({",
        "deleteFinanceiroMissao(selectedMission.id, { motivo: action.reason })",
        "cancelFinanceiroMissao(selectedMission.id, { motivo: action.reason })",
        "beginFinanceMissionOperation(operationKey, feedback)",
        "endFinanceMissionOperation(operationKey)",
        'const keepSelected = action.action === "cancel" && filters.status === "cancelada";',
        'preview_status: action.action === "delete" ? "excluida" : "cancelada"',
        'operationalStatus === "cancelada"',
    ):
        assert expected in feature


def test_financeiro_missoes_recalculate_service_does_not_use_create_or_preview_endpoint():
    service = _read(SERVICE)
    recalc_service = service[service.index("export async function recalculateFinanceiroMissao"):]
    recalc_service = recalc_service[: recalc_service.index("export async function preflightFinanceiroMissaoCalculo")]

    assert "method: \"POST\"" in recalc_service
    assert "/recalcular" in recalc_service
    assert "/preview" not in recalc_service
    assert "createFinanceiroMissao" not in recalc_service


def test_financeiro_missoes_declares_loading_empty_error_forbidden_and_calculation_states():
    feature = _read(FEATURE_PAGE)

    for expected in (
        'type: "loading"',
        "Nenhuma missão operacional encontrada",
        "Sessao expirada",
        "Acesso negado",
        "Nao foi possivel carregar Missoes Operacionais",
        "cancelada",
        "obsoleto",
        "pendente",
        "bloqueada",
    ):
        assert expected in feature
    assert "MISSION_EMPTY_TITLE_COMPAT" not in feature
    assert "data-legacy-title" not in feature


def test_financeiro_frontend_does_not_implement_financial_calculation_logic():
    feature = _read(FEATURE_PAGE)
    service = _read(SERVICE)
    combined = _strip_js_comments(f"{feature}\n{service}").lower()

    forbidden_fragments = (
        "adicional_noturno",
        "hora_noturna",
        "horas_noturnas",
        "minutos_noturnos",
        "pre_jornada",
        "pos_jornada",
        "garantia_minima",
        "produtividade_calculada",
        "total_devido",
        "formatcurrency",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined

    assert "preflight" in combined
    assert "recalcular" in combined


def test_financeiro_missoes_mobile_layout_avoids_horizontal_overflow():
    feature = _read(FEATURE_PAGE)
    css = _read(CSS_FILE)

    assert "responsive-cards" in feature
    assert ".financeiro-missoes-page .table-wrap.ui-table-wrap" in css
    assert "overflow-x: hidden;" in css
    assert ".financeiro-missoes-page .financeiro-missoes-recalc-actions" in css
    assert "@media (max-width: 1400px)" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "filterDisclosure.open = true;" in feature
    assert "older form resets" not in css
    assert "financeiro-missoes-legacy" not in css


def test_financeiro_missoes_visual_audit_script_covers_required_breakpoints_and_states():
    source = _read(VISUAL_AUDIT_SCRIPT)

    for expected in (
        "1920, 1080",
        "1600, 900",
        "1366, 768",
        "1280, 720",
        "1024, 768",
        "768, 1024",
        "390, 844",
        "Estado vazio",
        "Nova missão",
        "Missão selecionada",
        "Editando missão",
        "Prévia sem dados",
        "Prévia disponível",
        "Pendência de cálculo",
        "Recalculando",
        "Recalculado com sucesso",
        "Erro de recálculo",
        "runtime\" / \"visual-audit\" / SLUG",
        "{SLUG}__metadata.json",
        "{SLUG}__relatorio.md",
        "navigation-stability",
    ):
        assert expected in source


def test_financeiro_missoes_page_keeps_operational_form_contract():
    feature = _read(FEATURE_PAGE)

    for field_name in (
        "competencia",
        "data_missao",
        "cavok_numero_voo",
        "aeronave_id",
        "categoria_financeira_aeronave",
        "comandante_tripulante_id",
        "copiloto_tripulante_id",
        "horario_apresentacao",
        "horario_abandono",
        "trecho",
        "houve_pernoite",
        "quantidade_pernoites",
        "cobertura_base",
        "operacao_especial",
        "observacoes",
    ):
        if field_name in {"aeronave_id", "comandante_tripulante_id", "copiloto_tripulante_id"}:
            assert field_name in feature
        else:
            assert f'name="{field_name}"' in feature

    for forbidden in (
        "comandante_horario_apresentacao",
        "copiloto_horario_apresentacao",
        "comandante_horario_abandono",
        "copiloto_horario_abandono",
        "participante_horario",
    ):
        assert forbidden not in feature
