export const routeModuleLoaders = {
  financeiro: () => import("../pages-financeiro.20260430-142420.7067d73b0967.js"),
  tripulantes: () => import("../pages-dashboard-tripulantes.20260430-142420.4e4cdf26f269.js"),
  treinamentos: () => import("../pages-treinamentos-relatorios.20260430-142420.bece1ed47cde.js"),
};

export const staticRouteDefinitions = {
  "#/dashboard": {
    moduleName: "tripulantes",
    exportName: "renderDashboardPage",
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
  "#/financeiro/bonificacoes": {
    moduleName: "financeiro",
    exportName: "renderFinanceiroBonificacoesPage",
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

