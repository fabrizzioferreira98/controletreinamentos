function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}

export function assertArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`Resposta inesperada em ${label}.`);
  }
  return value;
}
export function adaptTripulantesListPayload(payload) {
  const data = assertObject(payload, "tripulantes.list");
  return {
    items: assertArray(data.items, "tripulantes.items"),
    filters: assertObject(data.filters, "tripulantes.filters"),
    pagination: assertObject(data.pagination, "tripulantes.pagination"),
  };
}

export function adaptTripulantesOptionsPayload(payload) {
  const options = assertObject(payload?.options, "tripulantes.options");
  return {
    status: assertArray(options.status, "tripulantes.options.status"),
    bases: assertArray(options.bases, "tripulantes.options.bases"),
    funcoes: assertArray(options.funcoes, "tripulantes.options.funcoes"),
    categorias: assertArray(options.categorias, "tripulantes.options.categorias"),
  };
}

export function optionsContainBase(options, baseName) {
  const target = String(baseName || "").trim();
  if (!target) return true;
  return options.bases.some((item) => String(item?.nome || "").trim() === target);
}
