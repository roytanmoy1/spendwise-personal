import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import BudgetsPage from './BudgetsPage';
import { useGetBudgetsQuery, useSetBudgetMutation } from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({ useGetBudgetsQuery: vi.fn(), useSetBudgetMutation: vi.fn() }));

const saveBudget = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));

beforeEach(() => {
  saveBudget.mockClear();
  useGetBudgetsQuery.mockReturnValue({ data: [{
    id: 'b1', category: 'FOOD', month: '2026-10', limitMinor: 100000, spentMinor: 45000,
  }], isLoading: false });
  useSetBudgetMutation.mockReturnValue([saveBudget, { isLoading: false }]);
});

afterEach(cleanup);

describe('budgets', () => {
  it('shows progress against a monthly category limit', () => {
    render(<BudgetsPage />);
    expect(screen.getByRole('heading', { name: 'Budgets' })).toBeTruthy();
    expect(within(screen.getByRole('region', { name: 'Category limits' })).getByText('Food & drink')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: 'Food & drink budget' }).getAttribute('aria-valuenow')).toBe('45');
  });

  it('saves an exact monthly limit', async () => {
    render(<BudgetsPage />);
    fireEvent.change(screen.getByLabelText('Month'), { target: { value: '2026-10' } });
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'HEALTH' } });
    fireEvent.change(screen.getByLabelText('Limit (INR)'), { target: { value: '1000.00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save budget' }));
    await waitFor(() => expect(saveBudget).toHaveBeenCalledWith({
      category: 'HEALTH', month: '2026-10', limitMinor: 100000,
    }));
  });
});