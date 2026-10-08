import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TransactionsPage from './TransactionsPage';
import {
  useGetTransactionsQuery, useAddTransactionMutation, useDeleteTransactionMutation,
  useUpdateTransactionCategoryMutation, useImportCsvMutation, useLazyExportCsvQuery,
} from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({
  useGetTransactionsQuery: vi.fn(), useAddTransactionMutation: vi.fn(),
  useDeleteTransactionMutation: vi.fn(), useUpdateTransactionCategoryMutation: vi.fn(),
  useImportCsvMutation: vi.fn(), useLazyExportCsvQuery: vi.fn(),
}));

const addTransaction = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));

beforeEach(() => {
  addTransaction.mockClear();
  useGetTransactionsQuery.mockReturnValue({ data: {
    totalCount: 26, hasMore: true, items: [{
      id: 'a1', merchant: 'Cafe Mellow', amountMinor: 12995, category: 'FOOD',
      method: 'UPI', occurredAt: '2026-10-03T08:00:00Z', city: 'Bengaluru', source: 'demo',
    }],
  }, isLoading: false, isFetching: false });
  useAddTransactionMutation.mockReturnValue([addTransaction, { isLoading: false }]);
  useDeleteTransactionMutation.mockReturnValue([vi.fn(), { isLoading: false }]);
  useUpdateTransactionCategoryMutation.mockReturnValue([vi.fn(), { isLoading: false }]);
  useImportCsvMutation.mockReturnValue([vi.fn(), { isLoading: false }]);
  useLazyExportCsvQuery.mockReturnValue([vi.fn(), { isFetching: false }]);
});

afterEach(cleanup);

describe('transactions', () => {
  it('lists a bounded page and requests the next page', async () => {
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Transactions' })).toBeTruthy();
    expect(screen.getByText('Cafe Mellow')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(useGetTransactionsQuery).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 25 })));
  });

  it('adds money using integer minor units', async () => {
    render(<MemoryRouter><TransactionsPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Add transaction' }));
    const dialog = screen.getByRole('dialog', { name: 'Add transaction' });
    fireEvent.change(within(dialog).getByLabelText('Merchant'), { target: { value: 'Apollo Pharmacy' } });
    fireEvent.change(within(dialog).getByLabelText('Amount (INR)'), { target: { value: '129.95' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save transaction' }));
    await waitFor(() => expect(addTransaction).toHaveBeenCalledWith(expect.objectContaining({
      merchant: 'Apollo Pharmacy', amountMinor: 12995, method: 'UPI',
    })));
  });
});