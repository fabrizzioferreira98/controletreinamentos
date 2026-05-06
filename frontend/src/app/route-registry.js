export const routeModuleLoaders = {
  financeiro: () => import("../pages-financeiro.js"),
  tripulantes: () => import("../pages-dashboard-tripulantes.js"),
  treinamentos: () => import("../pages-treinamentos-relatorios.js"),
};

export const staticRouteDefinitions = {
  "#/dashboard": {
    moduleName: "tripulantes",
    exportName: "renderDashboardPage",
    permissions: ["dashboard:view"],
  },
  "#/dashboard-operacional": {
    moduleName: "tripulantes",
    exportName: "renderOperationalDashboardPage",
    permissions: ["dashboard:view"],
  },
  "#/dashboard-operacional-tv": {
    moduleName: "tripulantes",
    exportName: "renderOperationalDashboardTvPage",
    permissions: ["dashboard:view"],
  },
  "#/tripulantes": {
    moduleName: "tripulantes",
    exportName: "renderTripulantesListPage",
    permissions: ["tripulantes:view", "relatorio_individual:view"],
  },
  "#/relatorios/individual": {
    moduleName: "tripulantes",
    exportName: "renderRelatorioIndividualPage",
    permissions: ["relatorio_individual:view"],
  },
  "#/tripulantes/new": {
    moduleName: "tripulantes",
    exportName: "renderTripulanteFormPage",
    permissions: ["tripulantes:create"],
  },
  "#/treinamentos": {
    moduleName: "treinamentos",
    exportName: "renderTreinamentosListPage",
    permissions: ["treinamentos:view"],
  },
  "#/treinamentos/new": {
    moduleName: "treinamentos",
    exportName: "renderTreinamentosListPage",
    permissions: ["treinamentos:create"],
  },
  "#/treinamentos/raiz": {
    moduleName: "treinamentos",
    exportName: "renderTrainingRootPage",
    permissions: ["tipos_treinamento:view"],
  },
  "#/relatorios/habilitacoes": {
    moduleName: "treinamentos",
    exportName: "renderRelatorioHabilitacoesPage",
    permissions: ["relatorio_habilitacoes:view"],
  },
  "#/financeiro/missoes": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroMissoesPage",
    permissions: ["finance:missions:read"],
  },
  "#/financeiro/lancamentos-jornada": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroLancamentosJornadaPage",
    permissions: ["finance:bonuses:read"],
  },
  // Compatibility hashes for old finance bonus bookmarks. They intentionally
  // render the same canonical Jornada owner instead of a second screen.
  "#/financeiro/bonificacoes": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroLancamentosJornadaPage",
    permissions: ["finance:bonuses:read"],
  },
  "#/financeiro/bonificacoes/horaria": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroLancamentosJornadaPage",
    permissions: ["finance:bonuses:read"],
  },
  "#/financeiro/bonificacoes/produtividade": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroLancamentosJornadaPage",
    permissions: ["finance:bonuses:read"],
  },
  "#/financeiro/fechamento-parametros": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroFechamentoParametrosPage",
    permissions: ["finance:parameters:read", "finance:periods:read"],
  },
};

export const dynamicRouteDefinitions = [
  {
    pattern: /^#\/tripulantes\/\d+$/,
    moduleName: "tripulantes",
    exportName: "renderTripulanteFormPage",
    permissions: ["tripulantes:edit"],
    args: (routeKey) => [Number(routeKey.split("/").pop())],
  },
  {
    pattern: /^#\/treinamentos\/\d+$/,
    moduleName: "treinamentos",
    exportName: "renderTreinamentoFormPage",
    permissions: ["treinamentos:edit"],
    args: (routeKey) => [Number(routeKey.split("/").pop())],
  },
];

