const moneyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2,
});
const monthFormatter = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const dateFormatter = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

export function formatMoney(amountMinor) {
  return moneyFormatter.format(amountMinor / 100);
}

export function formatMonth(month) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return 'Unknown month';
  return monthFormatter.format(new Date(`${month}-01T00:00:00Z`));
}

export function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown date' : dateFormatter.format(date);
}

export function parseMoney(value) {
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(String(value).trim());
  if (!match) return null;
  const amountMinor = Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0'));
  return amountMinor > 0 && amountMinor <= 100_000_000_000 ? amountMinor : null;
}