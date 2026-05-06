import {
  escapeAttr,
  escapeHtml,
  initialsForName,
} from "../../lib.js";
export function resolveTripulantePhotoUrl(item) {
  const tripulanteId = Number(item?.id || 0);
  if (!tripulanteId) return "";
  const hasConfirmedPhoto = Boolean(item?.possui_foto || item?.foto_storage_ref || item?.photo_url);
  if (!hasConfirmedPhoto) return "";
  return item?.photo_url || `/api/v1/tripulantes/${tripulanteId}/photo`;
}

function renderPhotoImage({ src, name, size = "sm", stateTarget = "" }) {
  const initials = initialsForName(name || "");
  const targetAttr = stateTarget ? ` data-photo-state-target="${escapeAttr(stateTarget)}"` : "";
  return `
    <div class="avatar avatar-${escapeAttr(size)}" data-photo-state="loaded" title="Foto carregada">
      <img
        class="tripulante-photo-img"
        src="${escapeAttr(src)}"
        alt="${escapeAttr(name || "Tripulante")}"
        loading="lazy"
        decoding="async"
        data-photo-fallback="initials"
        data-initials="${escapeAttr(initials)}"${targetAttr}
      >
    </div>
  `;
}

function renderInitialsAvatar(name, size = "sm", state = "empty") {
  const title = state === "unavailable" ? "Foto indisponível" : "Sem foto vinculada";
  return `
    <div class="avatar avatar-${escapeAttr(size)}" data-photo-state="${escapeAttr(state)}" title="${escapeAttr(title)}">
      <span>${escapeHtml(initialsForName(name || ""))}</span>
    </div>
  `;
}

export function renderTripulanteAvatar(item) {
  const photoUrl = resolveTripulantePhotoUrl(item);
  if (photoUrl) return renderPhotoImage({ src: photoUrl, name: item.nome, size: "sm" });
  return renderInitialsAvatar(item.nome, "sm", "empty");
}

export function wireTripulantePhotoFallbacks(root = document) {
  root.querySelectorAll("img[data-photo-fallback='initials']").forEach((image) => {
    if (image.dataset.photoFallbackBound === "true") return;
    image.dataset.photoFallbackBound = "true";
    image.addEventListener("error", () => {
      const wrapper = image.closest(".avatar, .tripulante-photo-preview");
      const stateTarget = image.dataset.photoStateTarget
        ? document.getElementById(image.dataset.photoStateTarget)
        : null;
      if (wrapper) {
        wrapper.dataset.photoState = "unavailable";
        wrapper.title = "Foto indisponível";
        wrapper.innerHTML = `<span>${escapeHtml(image.dataset.initials || "?")}</span>`;
      }
      if (stateTarget) {
        stateTarget.textContent = "Foto indisponível. A referência existe, mas o arquivo não carregou.";
        stateTarget.dataset.kind = "warning";
      }
    }, { once: true });
    image.addEventListener("load", () => {
      const wrapper = image.closest(".avatar, .tripulante-photo-preview");
      const stateTarget = image.dataset.photoStateTarget
        ? document.getElementById(image.dataset.photoStateTarget)
        : null;
      if (wrapper) {
        wrapper.dataset.photoState = "loaded";
        wrapper.title = "Foto carregada";
      }
      if (stateTarget && !stateTarget.dataset.userUploadState) {
        stateTarget.textContent = "Foto carregada com sucesso.";
        stateTarget.dataset.kind = "success";
      }
    }, { once: true });
  });
}

