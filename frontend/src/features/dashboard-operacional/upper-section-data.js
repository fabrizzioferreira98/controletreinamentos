/**
 * @typedef {"critical" | "warning" | "planning" | "normal"} DashboardUpperSeverity
 *
 * @typedef {Object} LicenseExpirationSummary
 * @property {number} total
 * @property {number} expired
 * @property {number} dueToday
 * @property {number} dueIn7Days
 * @property {number} dueIn30Days
 * @property {number} valid
 *
 * @typedef {Object} BaseStatusOption
 * @property {string} key
 * @property {string} label
 * @property {string} class
 * @property {string} marker_class
 *
 * @typedef {Object} BasePilotPreview
 * @property {number} id
 * @property {string} nome
 * @property {string} matricula
 * @property {number} tripulante_id
 * @property {number} base_id
 * @property {string} base_nome
 * @property {string} base_uf
 * @property {string} status
 * @property {string} status_label
 * @property {string} status_class
 * @property {boolean} possui_foto
 * @property {string} foto_url
 * @property {string} iniciais
 *
 * @typedef {Object} BaseOperationalStatus
 * @property {number} id
 * @property {string} icao
 * @property {string} nome
 * @property {string} uf
 * @property {number} latitude
 * @property {number} longitude
 * @property {boolean} ativa
 * @property {number} total_pilotos
 * @property {Record<string, number>} counts
 * @property {BasePilotPreview[]} pilotos
 *
 * @typedef {Object} BaseOperationalSummary
 * @property {number} basesActive
 * @property {number} crew
 * @property {number} alerts
 * @property {number} restrictions
 *
 * @typedef {Object} BaseOperationsSnapshot
 * @property {BaseOperationalStatus[]} bases
 * @property {BasePilotPreview[]} pilotos
 * @property {BaseStatusOption[]} statusOptions
 * @property {BaseOperationalSummary} summary
 *
 * @typedef {Object} CriticalQualification
 * @property {string} label
 * @property {number} affected
 * @property {DashboardUpperSeverity} severity
 * @property {string} helper
 *
 * @typedef {Object} DashboardUpperSectionData
 * @property {LicenseExpirationSummary} licenseSummary
 * @property {BaseOperationsSnapshot} baseOperations
 * @property {CriticalQualification[]} criticalQualifications
 */

export const DASHBOARD_EMPTY_BASE_OPERATIONS = Object.freeze({
  summary: Object.freeze({
    basesActive: 0,
    crew: 0,
    alerts: 0,
    restrictions: 0,
  }),
  bases: Object.freeze([]),
  pilotos: Object.freeze([]),
  statusOptions: Object.freeze([]),
});

/** @type {DashboardUpperSectionData} */
export const DASHBOARD_UPPER_SECTION_EMPTY = Object.freeze({
  licenseSummary: Object.freeze({}),
  baseOperations: DASHBOARD_EMPTY_BASE_OPERATIONS,
  criticalQualifications: Object.freeze([]),
});
