export const TEXT_SIZE_MIN = 85;
export const TEXT_SIZE_MAX = 150;
export const TEXT_SIZE_STEP = 5;
export const TEXT_SIZE_DEFAULT = 100;
export const TEXT_SIZE_STORAGE_KEY = "tt-text-size";
export const TEXT_SIZE_CHANGE_EVENT = "tt-text-size-change";

/** The same bounded preference drives controls, storage and the CSS multiplier. */
export function normalizeTextSize(value: unknown): number {
  const number = typeof value === "number" ? value : typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value.trim()) ? Number(value) : NaN;
  if (!Number.isFinite(number)) return TEXT_SIZE_DEFAULT;
  return Math.min(TEXT_SIZE_MAX, Math.max(TEXT_SIZE_MIN, Math.round(number / TEXT_SIZE_STEP) * TEXT_SIZE_STEP));
}

/** Executed in the root layout before hydration; never interpolates stored text. */
export const TEXT_SIZE_INIT_SCRIPT = `
(function () {
  var size = ${TEXT_SIZE_DEFAULT};
  try {
    var stored = localStorage.getItem('${TEXT_SIZE_STORAGE_KEY}');
    var number = typeof stored === 'string' && /^-?\\d+(?:\\.\\d+)?$/.test(stored.trim()) ? Number(stored) : NaN;
    if (Number.isFinite(number)) size = Math.min(${TEXT_SIZE_MAX}, Math.max(${TEXT_SIZE_MIN}, Math.round(number / ${TEXT_SIZE_STEP}) * ${TEXT_SIZE_STEP}));
  } catch (_) {}
  document.documentElement.setAttribute('data-text-size', String(size));
  document.documentElement.style.setProperty('--tt-text-scale', String(size / 100));
})();`;
