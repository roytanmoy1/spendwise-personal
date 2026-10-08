import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DashboardPage from './DashboardPage';
import { useGetOverviewQuery, useGetTransactionsQuery, useGetBudgetsQuery } from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({
  useGetOverviewQuery: vi.fn(), useGetTransactionsQuery: vi.fn(), useGetBudgetsQuery: vi.fn(),
}));
vi.mock('react-chartjs-2', () => ({ Line: () => <div data-testid="trend-chart" /> }));

const overview = {
  thisMonthMinor: 123450, lastMonthMinor: 90000, totalSpentMinor: 213450,
  transactionCount: 12,
  byCategory: [{ category: 'FOOD', amountMinor: 80000 }, { category: 'GROCERIES', amountMinor: 43450 }],
  byMethod: [{ method: 'UPI', amountMinor: 123450 }],
  byCity: [{ city: 'Bengaluru', amountMinor: 123450 }],
  monthly: [{ month: '2026-09', amountMinor: 90000 }, { month: '2026-10', amountMinor: 123450 }],
};

function renderDashboard() {
  return render(<MemoryRouter><DashboardPage viewer={{ name: 'Asha' }} /></MemoryRouter>);
}

beforeEach(() => {
  useGetOverviewQuery.mockReturnValue({ data: overview, isLoading: false, isError: false });
  useGetTransactionsQuery.mockReturnValue({ data: { items: [{
    id: '1', merchant: 'Cafe Mellow', amountMinor: 38500, category: 'FOOD',
    occurredAt: '2026-10-03T08:00:00Z', method: 'UPI',
  }] }, isLoading: false });
  useGetBudgetsQuery.mockReturnValue({ data: [], isLoading: false });
});

describe('dashboard', () => {
  it('renders real totals, category insights and recent transactions', () => {
    renderDashboard();
    expect(screen.getByRole('heading', { name: /overview/i })).toBeTruthy();
    expect(within(screen.getByRole('region', { name: 'Spending at a glance' })).getByText(/1,234.50/)).toBeTruthy();
    expect(screen.getByText('Cafe Mellow')).toBeTruthy();
    expect(screen.getByText('Bengaluru')).toBeTruthy();
    expect(screen.getByTestId('trend-chart')).toBeTruthy();
  });

  it('shows a skeleton while data loads', () => {
    useGetOverviewQuery.mockReturnValue({ isLoading: true });
    renderDashboard();
    expect(screen.getByRole('status', { name: 'Loading dashboard' })).toBeTruthy();
  });

  it('allows retrying a failed summary request', () => {
    const refetch = vi.fn();
    useGetOverviewQuery.mockReturnValue({ isError: true, error: { message: 'Offline' }, refetch });
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledOnce();
  });
});