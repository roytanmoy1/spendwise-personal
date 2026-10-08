import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AdminPage from './AdminPage';
import {
  useGetViewerQuery, useGetPendingUsersQuery, useGetManagedUsersQuery, useGetAdminNotificationsQuery,
  useAssignRoleMutation, useCreateUserMutation, useRemoveUserMutation,
  useMarkAdminNotificationReadMutation,
} from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({
  useGetViewerQuery: vi.fn(), useGetPendingUsersQuery: vi.fn(), useGetManagedUsersQuery: vi.fn(), useGetAdminNotificationsQuery: vi.fn(),
  useAssignRoleMutation: vi.fn(), useCreateUserMutation: vi.fn(), useRemoveUserMutation: vi.fn(),
  useMarkAdminNotificationReadMutation: vi.fn(),
}));
const assignRole = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));
const createUser = vi.fn(() => ({ unwrap: () => Promise.resolve({ createUser: { requiresVerification: true } }) }));
const removeUser = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));
const markRead = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  useGetViewerQuery.mockReturnValue({ data: { id: 'owner', role: 'SUPERADMIN', name: 'Owner' } });
  useGetPendingUsersQuery.mockReturnValue({ data: [{
    id: 'u1', name: 'Asha', email: 'asha@example.com', persona: 'Research',
    role: 'VIEWER', status: 'PENDING_REVIEW', emailVerified: true, createdAt: '2026-10-04T00:00:00Z',
  }], isLoading: false });
  useGetManagedUsersQuery.mockReturnValue({ data: [{
    id: 'u2', name: 'Invited', email: 'invited@example.com', persona: 'Client B',
    role: 'VIEWER', status: 'EMAIL_PENDING', emailVerified: false, createdAt: '2026-10-04T00:00:00Z',
  }], isLoading: false });
  useGetAdminNotificationsQuery.mockReturnValue({ data: [{
    id: 'n1', applicantEmail: 'asha@example.com', event: 'access_requested', createdAt: '2026-10-04T00:00:00Z', read: false,
  }], isLoading: false });
  useAssignRoleMutation.mockReturnValue([assignRole, { isLoading: false }]);
  useCreateUserMutation.mockReturnValue([createUser, { isLoading: false }]);
  useRemoveUserMutation.mockReturnValue([removeUser, { isLoading: false }]);
  useMarkAdminNotificationReadMutation.mockReturnValue([markRead, { isLoading: false }]);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('admin access management', () => {
  it('assigns a role to a verified pending user', async () => {
    render(<AdminPage />);
    expect(screen.getByText('asha@example.com')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Role for asha@example.com'), { target: { value: 'EDITOR' } });
    await waitFor(() => expect(assignRole).toHaveBeenCalledWith({ userId: 'u1', role: 'EDITOR' }));
  });

  it('superadmin can create and remove user accounts', async () => {
    render(<AdminPage />);
    fireEvent.change(screen.getByLabelText('New user name'), { target: { value: 'Mina' } });
    fireEvent.change(screen.getByLabelText('New user email'), { target: { value: 'mina@example.com' } });
    fireEvent.change(screen.getByLabelText('New user persona'), { target: { value: 'Client B' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add user' }));
    await waitFor(() => expect(createUser).toHaveBeenCalledWith({ name: 'Mina', email: 'mina@example.com', persona: 'Client B' }));
    expect(screen.getByLabelText('Role for invited@example.com').disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Remove invited@example.com' }));
    await waitFor(() => expect(removeUser).toHaveBeenCalledWith('u2'));
  });

  it('lets an administrator mark applicant notifications read', async () => {
    useGetViewerQuery.mockReturnValue({ data: { id: 'admin', role: 'ADMIN', name: 'Admin' } });
    render(<AdminPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Mark notification read' }));
    await waitFor(() => expect(markRead).toHaveBeenCalledWith('n1'));
    expect(screen.queryByRole('button', { name: 'Add user' })).toBeNull();
  });
});