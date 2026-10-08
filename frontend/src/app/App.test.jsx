import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import App from './App';
import { useGetViewerQuery, useLogoutMutation } from '../shared/api/api';

vi.mock('../shared/api/api', () => ({
  useGetViewerQuery: vi.fn(), useLogoutMutation: vi.fn(),
}));
vi.mock('../features/dashboard/DashboardPage', () => ({ default: () => <div>Dashboard view</div> }));
vi.mock('../features/transactions/TransactionsPage', () => ({ default: () => <div>Transactions view</div> }));
vi.mock('../features/budgets/BudgetsPage', () => ({ default: () => <div>Budgets view</div> }));
vi.mock('../features/auth/AuthPage', () => ({ default: () => <div>Authentication view</div> }));

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  useGetViewerQuery.mockReturnValue({ data: { id: '1', name: 'Asha', email: 'asha@example.com' }, isLoading: false });
  useLogoutMutation.mockReturnValue([vi.fn(), { isLoading: false }]);
});

describe('application shell', () => {
  it('navigates between the financial views without a page refresh', async () => {
    render(<App />);
    expect(await screen.findByText('Dashboard view')).toBeTruthy();
    fireEvent.click(screen.getByRole('link', { name: 'Transactions' }));
    expect(await screen.findByText('Transactions view')).toBeTruthy();
  });

  it('redirects a guest to sign in rather than opening a demo session', async () => {
    useGetViewerQuery.mockReturnValue({ isError: true, error: { status: 401 }, isLoading: false });
    render(<App />);
    expect(await screen.findByText('Authentication view')).toBeTruthy();
  });
});