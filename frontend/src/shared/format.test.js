import { describe, expect, it } from 'vitest';
import { formatMoney, formatMonth, formatDate, parseMoney } from './format';

describe('financial formatting', () => {
  it('formats integer minor units without floating point drift', () => {
    expect(formatMoney(123450)).toContain('1,234.50');
    expect(formatMoney(123450)).toContain('₹');
    expect(formatMoney(0)).toContain('0.00');
  });

  it('shows a readable month and transaction date', () => {
    expect(formatMonth('2026-10')).toBe('Oct 2026');
    expect(formatDate('2026-10-03T08:00:00Z')).toContain('Oct');
  });

  it('parses typed rupees exactly and rejects fractional paise', () => {
    expect(parseMoney('129.95')).toBe(12995);
    expect(parseMoney('0.001')).toBeNull();
    expect(parseMoney('0')).toBeNull();
    expect(parseMoney('-10')).toBeNull();
  });
});