import { renderTripulantesListPage } from "../tripulantes/list-page.js";

export async function renderRelatorioIndividualPage() {
  return renderTripulantesListPage("report");
}

