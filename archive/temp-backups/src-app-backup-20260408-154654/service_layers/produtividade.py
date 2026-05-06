from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..services import business_today

FUNCAO_OPERACIONAL_OPTIONS = ("comandante", "copiloto", "outro")
CATEGORIA_OPERACIONAL_OPTIONS = ("A", "B", "N/A")
BONIFICACAO_CATEGORIAS_ATIVAS = ("A", "B")
TIPO_PERNOITE_OPTIONS = ("cobertura_base", "operacional_comum")


@dataclass
class CompetenciaDataBundle:
    competencia: str
    month_start: date
    month_end_exclusive: date
    regras_map: dict[tuple[str, str], dict]
    parametros: dict[str, Decimal]
    missoes_by_tripulante: dict[int, list[dict]]
    pernoites_by_tripulante: dict[int, list[dict]]
    adicional_manual_by_tripulante: dict[int, Decimal]


@dataclass
class TripulanteSnapshot:
    id: int
    nome: str
    base: str
    funcao: str
    categoria: str
    sdea_ativo: bool
    instrutor_ativo: bool
    checador_ativo: bool
    elegivel_adicional_excepcional: bool
    raw: dict


class ProdutividadeEngine:
    """Engine central de produtividade/bonificacao.

    Fluxo interno:
    1) Coleta de dados por competencia (bundle)
    2) Validacoes/elegibilidade
    3) Calculo de parcelas
    4) Consolidacao final (piso x produtividade)
    5) Memoria de calculo auditavel
    """

    def __init__(self, db):
        self.db = db

    def build_bundle(self, *, competencia: str, tripulante_ids: list[int]) -> CompetenciaDataBundle:
        normalized_competencia = parse_competencia(competencia)
        month_start, month_end_exclusive = competencia_date_range(normalized_competencia)
        ids = sorted({int(item) for item in tripulante_ids if item})

        regras_map = self._fetch_regras_map()
        parametros = self._fetch_parametros()

        if not ids:
            return CompetenciaDataBundle(
                competencia=normalized_competencia,
                month_start=month_start,
                month_end_exclusive=month_end_exclusive,
                regras_map=regras_map,
                parametros=parametros,
                missoes_by_tripulante={},
                pernoites_by_tripulante={},
                adicional_manual_by_tripulante={},
            )

        missoes_rows = self.db.execute(
            """
            SELECT
                mt.tripulante_id,
                m.id,
                m.codigo_voo,
                m.contratante,
                m.data_inicio,
                m.data_fim,
                m.origem,
                m.destino,
                m.tipo_operacao,
                m.conta_missao_produtividade
            FROM missao_tripulantes mt
            JOIN missoes_operacionais m ON m.id = mt.missao_id
            WHERE mt.tripulante_id = ANY(%s)
              AND m.data_inicio < %s
              AND COALESCE(m.data_fim, m.data_inicio) >= %s
            ORDER BY mt.tripulante_id, m.data_inicio, m.id
            """,
            (ids, month_end_exclusive, month_start),
        ).fetchall()
        missoes_by_tripulante: dict[int, list[dict]] = defaultdict(list)
        for row in missoes_rows:
            item = dict(row)
            item.pop("tripulante_id", None)
            missoes_by_tripulante[row["tripulante_id"]].append(item)

        pernoites_rows = self.db.execute(
            """
            SELECT
                p.tripulante_id,
                p.id,
                p.missao_id,
                p.data_pernoite,
                p.tipo_pernoite,
                p.quantidade,
                p.observacoes,
                m.codigo_voo,
                m.contratante
            FROM pernoites_operacionais p
            LEFT JOIN missoes_operacionais m ON m.id = p.missao_id
            WHERE p.tripulante_id = ANY(%s)
              AND p.data_pernoite >= %s
              AND p.data_pernoite < %s
            ORDER BY p.tripulante_id, p.data_pernoite, p.id
            """,
            (ids, month_start, month_end_exclusive),
        ).fetchall()
        pernoites_by_tripulante: dict[int, list[dict]] = defaultdict(list)
        for row in pernoites_rows:
            item = dict(row)
            item.pop("tripulante_id", None)
            pernoites_by_tripulante[row["tripulante_id"]].append(item)

        adicional_rows = self.db.execute(
            """
            SELECT tripulante_id, COALESCE(SUM(valor), 0) AS total
            FROM produtividade_adicionais_excepcionais
            WHERE tripulante_id = ANY(%s)
              AND competencia = %s
              AND ativo = TRUE
            GROUP BY tripulante_id
            """,
            (ids, normalized_competencia),
        ).fetchall()
        adicional_manual_by_tripulante = {row["tripulante_id"]: _to_decimal(row["total"]) for row in adicional_rows}

        return CompetenciaDataBundle(
            competencia=normalized_competencia,
            month_start=month_start,
            month_end_exclusive=month_end_exclusive,
            regras_map=regras_map,
            parametros=parametros,
            missoes_by_tripulante=dict(missoes_by_tripulante),
            pernoites_by_tripulante=dict(pernoites_by_tripulante),
            adicional_manual_by_tripulante=adicional_manual_by_tripulante,
        )

    def calculate_tripulante(self, *, tripulante: dict, competencia: str, bundle: CompetenciaDataBundle | None = None) -> dict:
        bundle = bundle or self.build_bundle(competencia=competencia, tripulante_ids=[tripulante["id"]])
        perfil = self._normalize_tripulante(tripulante)

        regra = self._resolve_regra(bundle.regras_map, categoria=perfil.categoria, funcao=perfil.funcao)
        parametros = bundle.parametros

        missoes = [dict(row) for row in bundle.missoes_by_tripulante.get(perfil.id, [])]
        pernoites = [dict(row) for row in bundle.pernoites_by_tripulante.get(perfil.id, [])]
        adicional_excepcional_manual = bundle.adicional_manual_by_tripulante.get(perfil.id, Decimal("0"))

        validacoes = self._validar_entradas(perfil=perfil, regra=regra)

        missao_calc = self._calcular_missoes(missoes=missoes, valor_missao_unitario=_to_decimal(regra.get("valor_missao")))
        pernoite_calc = self._calcular_pernoites(
            pernoites=pernoites,
            valor_cobertura_unitario=_to_decimal(regra.get("valor_pernoite_cobertura")),
            valor_operacional_unitario=_to_decimal(parametros.get("valor_pernoite_operacional_comum")),
            contar_operacional_a_partir_segundo_dia=(
                int(parametros.get("contar_pernoite_operacional_a_partir_segundo_dia", Decimal("1"))) == 1
            ),
        )
        adicionais_calc = self._calcular_adicionais(
            perfil=perfil,
            regra=regra,
            parametros=parametros,
            adicional_manual=adicional_excepcional_manual,
        )

        piso_minimo_mensal = _to_decimal(regra.get("piso_minimo_mensal"))
        total_produtividade = (
            missao_calc["valor_total_missoes"]
            + pernoite_calc["valor_total_pernoites_cobertura"]
            + pernoite_calc["valor_total_pernoites_operacionais"]
            + adicionais_calc["valor_idioma"]
            + adicionais_calc["valor_instrutor"]
            + adicionais_calc["valor_checador"]
            + adicionais_calc["valor_adicional_excepcional"]
        )

        valor_final_mes = max(piso_minimo_mensal, total_produtividade)
        criterio_fechamento = (
            "piso mínimo"
            if valor_final_mes == piso_minimo_mensal and piso_minimo_mensal > 0
            else "produtividade apurada"
        )

        memoria_calculo = {
            "entradas": {
                "tripulante_id": perfil.id,
                "tripulante_nome": perfil.nome,
                "competencia": bundle.competencia,
                "categoria": perfil.categoria,
                "funcao": perfil.funcao,
                "base": perfil.base,
            },
            "elegibilidade": {
                "sdea_ativo": perfil.sdea_ativo,
                "instrutor_ativo": perfil.instrutor_ativo,
                "checador_ativo": perfil.checador_ativo,
                "elegivel_adicional_excepcional": perfil.elegivel_adicional_excepcional,
            },
            "parcelas": {
                "missoes": missao_calc,
                "pernoites": pernoite_calc,
                "adicionais": adicionais_calc,
            },
            "consolidacao": {
                "piso_minimo_mensal": piso_minimo_mensal,
                "total_produtividade": total_produtividade,
                "valor_final_mes": valor_final_mes,
                "criterio_fechamento": criterio_fechamento,
            },
            "validacoes": validacoes,
        }

        return {
            "tripulante_id": perfil.id,
            "tripulante_nome": perfil.nome,
            "base": perfil.base,
            "funcao": perfil.funcao,
            "categoria": perfil.categoria,
            "competencia": bundle.competencia,
            "piso_minimo_mensal": piso_minimo_mensal,
            "total_missoes_validas": missao_calc["total_missoes_validas"],
            "valor_total_missoes": missao_calc["valor_total_missoes"],
            "total_pernoites_cobertura": pernoite_calc["total_pernoites_cobertura"],
            "valor_total_pernoites_cobertura": pernoite_calc["valor_total_pernoites_cobertura"],
            "total_pernoites_operacionais_elegiveis": pernoite_calc["total_pernoites_operacionais_elegiveis"],
            "valor_total_pernoites_operacionais": pernoite_calc["valor_total_pernoites_operacionais"],
            "valor_idioma": adicionais_calc["valor_idioma"],
            "valor_instrutor": adicionais_calc["valor_instrutor"],
            "valor_checador": adicionais_calc["valor_checador"],
            "valor_adicional_excepcional": adicionais_calc["valor_adicional_excepcional"],
            "total_produtividade": total_produtividade,
            "valor_final_mes": valor_final_mes,
            "criterio_fechamento": criterio_fechamento,
            "missao_detalhes": missao_calc["missoes_validas"],
            "pernoite_detalhes": pernoites,
            "tripulante": perfil.raw,
            "memoria_calculo": memoria_calculo,
        }

    def calculate_consolidado(
        self,
        *,
        competencia: str,
        base: str = "",
        funcao: str = "",
        categoria: str = "",
        nome: str = "",
    ) -> dict:
        tripulantes = self._fetch_tripulantes_filtrados(base=base, funcao=funcao, categoria=categoria, nome=nome)
        bundle = self.build_bundle(competencia=competencia, tripulante_ids=[row["id"] for row in tripulantes])
        rows = [
            self.calculate_tripulante(tripulante=row, competencia=bundle.competencia, bundle=bundle)
            for row in tripulantes
        ]
        rows.sort(key=lambda item: (item["valor_final_mes"], item["total_produtividade"]), reverse=True)

        total_pago_piso = sum(item["valor_final_mes"] for item in rows if item["criterio_fechamento"] == "piso mínimo")
        total_pago_produtividade = sum(
            item["valor_final_mes"] for item in rows if item["criterio_fechamento"] == "produtividade apurada"
        )
        total_missoes = sum(item["total_missoes_validas"] for item in rows)
        total_pernoites = sum(
            item["total_pernoites_cobertura"] + item["total_pernoites_operacionais_elegiveis"] for item in rows
        )
        total_consolidado = sum(item["valor_final_mes"] for item in rows)

        counts_categoria = {key: 0 for key in CATEGORIA_OPERACIONAL_OPTIONS}
        total_com_adicionais_ativos = 0
        for row in rows:
            categoria_key = row["categoria"] if row["categoria"] in counts_categoria else "N/A"
            counts_categoria[categoria_key] += 1
            trip = row["tripulante"]
            if (
                trip.get("sdea_ativo")
                or trip.get("instrutor_ativo")
                or trip.get("checador_ativo")
                or trip.get("elegivel_adicional_excepcional")
            ):
                total_com_adicionais_ativos += 1

        return {
            "competencia": bundle.competencia,
            "rows": rows,
            "summary": {
                "total_tripulantes": len(rows),
                "total_missoes": total_missoes,
                "total_pernoites": total_pernoites,
                "total_pago_piso": total_pago_piso,
                "total_pago_produtividade": total_pago_produtividade,
                "valor_total_consolidado": total_consolidado,
                "categoria_a": counts_categoria["A"],
                "categoria_b": counts_categoria["B"],
                "categoria_na": counts_categoria["N/A"],
                "tripulantes_com_adicionais": total_com_adicionais_ativos,
            },
        }

    def _fetch_tripulantes_filtrados(self, *, base: str, funcao: str, categoria: str, nome: str) -> list[dict]:
        clauses = []
        params: list[Any] = []

        if nome:
            clauses.append("LOWER(nome) LIKE %s")
            params.append(f"%{nome.lower()}%")
        if base:
            clauses.append("LOWER(base) = LOWER(%s)")
            params.append(base)
        if funcao and funcao in FUNCAO_OPERACIONAL_OPTIONS:
            clauses.append("funcao_operacional = %s")
            params.append(funcao)
        if categoria and categoria in BONIFICACAO_CATEGORIAS_ATIVAS:
            clauses.append("categoria_operacional = %s")
            params.append(categoria)
        else:
            clauses.append("categoria_operacional = ANY(%s)")
            params.append(list(BONIFICACAO_CATEGORIAS_ATIVAS))

        clauses.append("ativo = 1")
        where = f"WHERE {' AND '.join(clauses)}"
        rows = self.db.execute(
            f"""
            SELECT
                id,
                nome,
                base,
                funcao_operacional,
                categoria_operacional,
                sdea_ativo,
                instrutor_ativo,
                checador_ativo,
                elegivel_adicional_excepcional
            FROM tripulantes
            {where}
            ORDER BY nome
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def _normalize_tripulante(self, tripulante: dict) -> TripulanteSnapshot:
        funcao = (tripulante.get("funcao_operacional") or "outro").lower().strip()
        categoria = (tripulante.get("categoria_operacional") or "N/A").strip()
        if funcao not in FUNCAO_OPERACIONAL_OPTIONS:
            funcao = "outro"
        if categoria not in CATEGORIA_OPERACIONAL_OPTIONS:
            categoria = "N/A"

        return TripulanteSnapshot(
            id=int(tripulante["id"]),
            nome=(tripulante.get("nome") or "-").strip() or "-",
            base=(tripulante.get("base") or "-").strip() or "-",
            funcao=funcao,
            categoria=categoria,
            sdea_ativo=bool(tripulante.get("sdea_ativo")),
            instrutor_ativo=bool(tripulante.get("instrutor_ativo")),
            checador_ativo=bool(tripulante.get("checador_ativo")),
            elegivel_adicional_excepcional=bool(tripulante.get("elegivel_adicional_excepcional")),
            raw=tripulante,
        )

    def _resolve_regra(self, regras_map: dict[tuple[str, str], dict], *, categoria: str, funcao: str) -> dict:
        direct = regras_map.get((categoria, funcao))
        if direct:
            return direct
        fallback = regras_map.get(("N/A", funcao))
        if fallback:
            return fallback
        return {}

    def _validar_entradas(self, *, perfil: TripulanteSnapshot, regra: dict) -> list[str]:
        warnings: list[str] = []
        if not regra:
            warnings.append("Regra de produtividade nao encontrada para categoria/funcao; valores zerados serao aplicados.")
        if perfil.funcao == "outro":
            warnings.append("Funcao operacional fora de comandante/copiloto; regra 'outro' aplicada.")
        if perfil.categoria == "N/A":
            warnings.append("Categoria operacional N/A; piso e missao dependem de parametrizacao N/A.")
        return warnings

    def _calcular_missoes(self, *, missoes: list[dict], valor_missao_unitario: Decimal) -> dict:
        # Consolidacao por chave operacional para evitar contagem indevida por duplicidade.
        validas = [row for row in missoes if row.get("conta_missao_produtividade")]
        consolidado: dict[str, dict] = {}
        for row in validas:
            chave = f"{(row.get('codigo_voo') or '').strip().lower()}::{(row.get('contratante') or '').strip().lower()}"
            if not chave.strip(":"):
                chave = f"missao-id::{row.get('id')}"
            if chave not in consolidado:
                consolidado[chave] = row

        missoes_validas = list(consolidado.values())
        total_missoes_validas = len(missoes_validas)
        valor_total_missoes = valor_missao_unitario * total_missoes_validas

        return {
            "total_missoes_validas": total_missoes_validas,
            "valor_missao_unitario": valor_missao_unitario,
            "valor_total_missoes": valor_total_missoes,
            "missoes_validas": missoes_validas,
        }

    def _calcular_pernoites(
        self,
        *,
        pernoites: list[dict],
        valor_cobertura_unitario: Decimal,
        valor_operacional_unitario: Decimal,
        contar_operacional_a_partir_segundo_dia: bool,
    ) -> dict:
        total_pernoites_cobertura = sum(
            int(row.get("quantidade") or 0) for row in pernoites if row.get("tipo_pernoite") == "cobertura_base"
        )
        valor_total_pernoites_cobertura = valor_cobertura_unitario * total_pernoites_cobertura

        pernoites_operacionais = [row for row in pernoites if row.get("tipo_pernoite") == "operacional_comum"]
        por_grupo_operacional = defaultdict(int)
        for row in pernoites_operacionais:
            if row.get("missao_id"):
                group_key = f"missao::{row['missao_id']}"
            elif row.get("codigo_voo") or row.get("contratante"):
                group_key = f"oper::{(row.get('codigo_voo') or '').strip().lower()}::{(row.get('contratante') or '').strip().lower()}"
            else:
                group_key = f"avulso::{row['id']}"
            por_grupo_operacional[group_key] += int(row.get("quantidade") or 0)

        total_pernoites_operacionais_elegiveis = 0
        for quantidade in por_grupo_operacional.values():
            if contar_operacional_a_partir_segundo_dia:
                total_pernoites_operacionais_elegiveis += max(quantidade - 1, 0)
            else:
                total_pernoites_operacionais_elegiveis += quantidade

        valor_total_pernoites_operacionais = valor_operacional_unitario * total_pernoites_operacionais_elegiveis

        return {
            "total_pernoites_cobertura": total_pernoites_cobertura,
            "valor_cobertura_unitario": valor_cobertura_unitario,
            "valor_total_pernoites_cobertura": valor_total_pernoites_cobertura,
            "total_pernoites_operacionais_elegiveis": total_pernoites_operacionais_elegiveis,
            "valor_operacional_unitario": valor_operacional_unitario,
            "valor_total_pernoites_operacionais": valor_total_pernoites_operacionais,
            "contar_operacional_a_partir_segundo_dia": contar_operacional_a_partir_segundo_dia,
        }

    def _calcular_adicionais(
        self,
        *,
        perfil: TripulanteSnapshot,
        regra: dict,
        parametros: dict[str, Decimal],
        adicional_manual: Decimal,
    ) -> dict:
        valor_idioma = _to_decimal(regra.get("valor_idioma_mensal")) if perfil.sdea_ativo else Decimal("0")
        valor_instrutor = _to_decimal(regra.get("valor_instrutor_mensal")) if perfil.instrutor_ativo else Decimal("0")
        valor_checador = _to_decimal(regra.get("valor_checador_mensal")) if perfil.checador_ativo else Decimal("0")

        adicional_parametrico = _to_decimal(parametros.get(f"adicional_excepcional_{perfil.funcao}"))
        valor_adicional_excepcional = adicional_manual if adicional_manual > 0 else adicional_parametrico
        if not perfil.elegivel_adicional_excepcional:
            valor_adicional_excepcional = Decimal("0")

        return {
            "valor_idioma": valor_idioma,
            "valor_instrutor": valor_instrutor,
            "valor_checador": valor_checador,
            "valor_adicional_excepcional": valor_adicional_excepcional,
            "adicional_excepcional_manual": adicional_manual,
            "adicional_excepcional_parametrico": adicional_parametrico,
        }

    def _fetch_regras_map(self) -> dict[tuple[str, str], dict]:
        rows = self.db.execute(
            """
            SELECT *
            FROM produtividade_regras
            WHERE ativo = TRUE
            """
        ).fetchall()
        return {(row["categoria_operacional"], row["funcao_operacional"]): dict(row) for row in rows}

    def _fetch_parametros(self) -> dict[str, Decimal]:
        rows = self.db.execute("SELECT chave, valor_numerico FROM produtividade_parametros").fetchall()
        return {row["chave"]: _to_decimal(row["valor_numerico"]) for row in rows}


def parse_competencia(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        today = business_today()
        return f"{today.year:04d}-{today.month:02d}"
    try:
        dt = datetime.strptime(raw, "%Y-%m")
        return f"{dt.year:04d}-{dt.month:02d}"
    except ValueError:
        today = business_today()
        return f"{today.year:04d}-{today.month:02d}"


def competencia_date_range(competencia: str) -> tuple[date, date]:
    reference = datetime.strptime(parse_competencia(competencia), "%Y-%m").date().replace(day=1)
    if reference.month == 12:
        next_month = reference.replace(year=reference.year + 1, month=1, day=1)
    else:
        next_month = reference.replace(month=reference.month + 1, day=1)
    return reference, next_month


def moeda(value: Decimal | float | int) -> str:
    numeric = Decimal(value or 0).quantize(Decimal("0.01"))
    s = f"{numeric:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def bool_label(value: int | bool | None) -> str:
    return "Sim" if bool(value) else "Não"


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def build_competencia_bundle(db, *, competencia: str, tripulante_ids: list[int]) -> CompetenciaDataBundle:
    return ProdutividadeEngine(db).build_bundle(competencia=competencia, tripulante_ids=tripulante_ids)


def calculate_tripulante_competencia(
    db,
    *,
    tripulante: dict,
    competencia: str,
    bundle: CompetenciaDataBundle | None = None,
) -> dict:
    return ProdutividadeEngine(db).calculate_tripulante(tripulante=tripulante, competencia=competencia, bundle=bundle)


def calculate_competencia_consolidada(
    db,
    *,
    competencia: str,
    base: str = "",
    funcao: str = "",
    categoria: str = "",
    nome: str = "",
) -> dict:
    return ProdutividadeEngine(db).calculate_consolidado(
        competencia=competencia,
        base=base,
        funcao=funcao,
        categoria=categoria,
        nome=nome,
    )
