const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function parseDate(d: string) {
  const [y, m, day] = d.split("-").map(Number);
  return Date.UTC(y, (m || 1) - 1, day || 1);
}

export function fmtDate(d: string, opts: { year?: boolean } = {}) {
  const t = new Date(parseDate(d));
  const s = `${MONTHS[t.getUTCMonth()]} ${t.getUTCDate()}`;
  return opts.year === false ? s : `${s}, ${t.getUTCFullYear()}`;
}

export function fmtMonthYear(d: string) {
  const t = new Date(parseDate(d));
  return `${MONTHS[t.getUTCMonth()]} ${t.getUTCFullYear()}`;
}

export function monthName(i: number) {
  return MONTHS[i];
}

export function fmtInt(n: number) {
  return Math.round(n).toLocaleString("en-US");
}

export function fmtDb(x: number, digits = 1) {
  const s = x.toFixed(digits);
  return s.startsWith("-") ? `−${s.slice(1)}` : s;
}

export function fmtSigned(x: number, digits = 1) {
  const s = Math.abs(x).toFixed(digits);
  return `${x >= 0 ? "+" : "−"}${s}`;
}

export function daysBetween(a: string, b: string) {
  return Math.round((parseDate(b) - parseDate(a)) / 86400000);
}
