import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ProfilePage from './ProfilePage';
import { useGetViewerQuery, useUpdateProfileMutation } from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({ useGetViewerQuery: vi.fn(), useUpdateProfileMutation: vi.fn() }));
const updateProfile = vi.fn(() => ({ unwrap: () => Promise.resolve({}) }));

beforeEach(() => {
  updateProfile.mockClear();
  useGetViewerQuery.mockReturnValue({ data: {
    id: 'u1', name: 'Asha Rao', email: 'asha@example.com', persona: 'Client A',
    role: 'EDITOR', status: 'ACTIVE', emailVerified: true,
  }, isLoading: false });
  useUpdateProfileMutation.mockReturnValue([updateProfile, { isLoading: false }]);
});
afterEach(cleanup);

describe('profile', () => {
  it('shows account role and allows updating display name and persona', async () => {
    render(<ProfilePage />);
    expect(screen.getByLabelText('Login email').value).toBe('asha@example.com');
    expect(screen.getByText('Editor')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Asha R.' } });
    fireEvent.change(screen.getByLabelText('Persona / workspace'), { target: { value: 'Research' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith({ name: 'Asha R.', persona: 'Research' }));
  });
});