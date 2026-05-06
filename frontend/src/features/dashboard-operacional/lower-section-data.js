import { BACKEND_LINKS } from "../../compat/backend-links.js";

/**
 * @typedef {"VMC" | "MVFR" | "IFR" | "IMC" | "UNKNOWN"} WeatherCondition
 * @typedef {"normal" | "attention" | "critical" | "unknown"} BaseWeatherSeverity
 * @typedef {"critical" | "warning" | "attention" | "info"} NotamSeverity
 *
 * @typedef {Object} BaseWeatherStatus
 * @property {string} icao
 * @property {string} city
 * @property {WeatherCondition} condition
 * @property {number | null} temperatureC
 * @property {number | null} windKt
 * @property {string | null} coverage
 * @property {number | null} visibilityKm
 * @property {BaseWeatherSeverity} severity
 *
 * @typedef {Object} RelevantNotam
 * @property {string} id
 * @property {string} code
 * @property {string} icao
 * @property {string} description
 * @property {string} updatedAt
 * @property {string} validUntil
 * @property {NotamSeverity} severity
 *
 * @typedef {Object} QuickAction
 * @property {string} id
 * @property {string} label
 * @property {string} icon
 * @property {string} href
 * @property {boolean} [enabled]
 * @property {string} [futureIntent]
 *
 * @typedef {Object} DashboardLowerSectionData
 * @property {BaseWeatherStatus[]} weatherByBase
 * @property {RelevantNotam[]} relevantNotams
 * @property {QuickAction[]} quickActions
 */

export const DASHBOARD_OPERATIONAL_QUICK_ACTIONS = Object.freeze([
  Object.freeze({
    id: "new-flight",
    label: "Novo Voo",
    icon: "plane",
    href: "#/dashboard-operacional",
    futureIntent: "operacoes.voos.create",
    enabled: false,
  }),
  Object.freeze({
    id: "incident",
    label: "Registrar Ocorr\u00eancia",
    icon: "alert-triangle",
    href: "#/dashboard-operacional",
    futureIntent: "operacoes.ocorrencias.create",
    enabled: false,
  }),
  Object.freeze({
    id: "crew",
    label: "Gerenciar Tripulantes",
    icon: "users",
    href: "#/tripulantes",
    enabled: true,
  }),
  Object.freeze({
    id: "expiration-report",
    label: "Relat\u00f3rio de Vencimentos",
    icon: "calendar",
    href: "#/relatorios/habilitacoes",
    enabled: true,
  }),
  Object.freeze({
    id: "export",
    label: "Exportar Dados",
    icon: "download",
    href: BACKEND_LINKS.treinamentosConsolidadoExportCsv,
    enabled: true,
  }),
  Object.freeze({
    id: "calendar",
    label: "Ver Calend\u00e1rio",
    icon: "calendar-days",
    href: "#/dashboard",
    enabled: true,
  }),
]);

/** @type {DashboardLowerSectionData} */
export const DASHBOARD_LOWER_SECTION_EMPTY = Object.freeze({
  weatherByBase: Object.freeze([]),
  relevantNotams: Object.freeze([]),
  quickActions: Object.freeze([]),
});
