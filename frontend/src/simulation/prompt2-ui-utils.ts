export const escapeHtml = (value: string): string =>
  value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]!,
  );

export const formatNumber = (value: number, maximumFractionDigits = 2): string =>
  new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);

export const formatPercent = (value: number, maximumFractionDigits = 1): string =>
  `${formatNumber(value * 100, maximumFractionDigits)}%`;

export const cloneValue = <Value>(value: Value): Value => structuredClone(value);

export const normalizeSpace = (value: string): string => value.trim().replace(/\s+/g, ' ');

export const parseFiniteNumber = (value: string): number | null => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const sentenceCase = (value: string): string => {
  const normalized = value.replace(/[_-]+/g, ' ').trim();
  return normalized ? `${normalized[0]!.toUpperCase()}${normalized.slice(1)}` : '';
};
