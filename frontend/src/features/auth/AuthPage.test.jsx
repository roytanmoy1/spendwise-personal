import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AuthPage from './AuthPage';
import {
  useLoginMutation, useRegisterMutation,
  useVerifyEmailMutation, useResendVerificationCodeMutation,
} from '../../shared/api/api';

vi.mock('../../shared/api/api', () => ({
  useLoginMutation: vi.fn(), useRegisterMutation: vi.fn(),
  useVerifyEmailMutation: vi.fn(), useResendVerificationCodeMutation: vi.fn(),
}));

let loginResult;
let registerResult;
const login = vi.fn(() => ({ unwrap: () => Promise.resolve(loginResult) }));
const register = vi.fn(() => ({ unwrap: () => Promise.resolve(registerResult) }));
const verifyEmail = vi.fn(() => ({ unwrap: () => Promise.resolve({ verifyEmail: { id: '1' } }) }));
const resendCode = vi.fn(() => ({ unwrap: () => Promise.resolve({ resendVerificationCode: true }) }));

function renderAuth(mode) {
  const initialPath = mode === 'register' ? '/register' : mode === 'verify' ? '/verify-email?email=asha@example.com' : '/login';
  render(<MemoryRouter initialEntries={[initialPath]}><Routes>
    <Route path="/login" element={<AuthPage mode="login" />} />
    <Route path="/register" element={<AuthPage mode="register" />} />
    <Route path="/verify-email" element={<AuthPage mode="verify" />} />
    <Route path="/" element={<div>Workspace loaded</div>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  login.mockClear(); register.mockClear();
  verifyEmail.mockClear(); resendCode.mockClear();
  loginResult = { login: { authenticated: true, requiresVerification: false, viewer: { id: '1' } } };
  registerResult = { register: { authenticated: false, requiresVerification: true, message: 'Check your inbox.' } };
  useLoginMutation.mockReturnValue([login, { isLoading: false }]);
  useRegisterMutation.mockReturnValue([register, { isLoading: false }]);
  useVerifyEmailMutation.mockReturnValue([verifyEmail, { isLoading: false }]);
  useResendVerificationCodeMutation.mockReturnValue([resendCode, { isLoading: false }]);
});
afterEach(cleanup);

describe('authentication', () => {
  it('signs in and returns to the workspace', async () => {
    renderAuth('login');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'asha@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(login).toHaveBeenCalledWith({ email: 'asha@example.com', password: 'long-test-password' }));
    expect(await screen.findByText('Workspace loaded')).toBeTruthy();
  });

  it('does not ask for a workspace when signing in', () => {
    renderAuth('login');
    expect(screen.queryByLabelText('Persona')).toBeNull();
  });

  it('redirects an unknown email to registration with the email prefilled', async () => {
    loginResult = { login: {
      authenticated: false, requiresVerification: false, requiresRegistration: true,
    } };
    renderAuth('login');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeTruthy();
    expect(screen.getByLabelText('Email').value).toBe('new@example.com');
  });

  it('removes demo-only copy and entry points from sign-in', () => {
    renderAuth('login');
    expect(screen.queryByRole('button', { name: 'Explore demo' })).toBeNull();
    expect(screen.queryByText('Synthetic data only')).toBeNull();
    expect(screen.queryByText('DEMO DATA')).toBeNull();
    expect(screen.queryByText('SpendWise · A personal project')).toBeNull();
  });

  it('shows actionable guidance when local email delivery is not configured', async () => {
    login.mockReturnValueOnce({ unwrap: () => Promise.reject(new Error(
      "Email sign-in isn't configured. Configure Resend in the backend environment to enable email verification.",
    )) });
    renderAuth('login');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'local@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/Configure Resend in the backend environment/);
  });

  it('verifies an account that needs email verification before opening its workspace', async () => {
    loginResult = { login: { authenticated: false, requiresVerification: true, message: 'Check your inbox.' } };
    renderAuth('login');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByLabelText('Verification code')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Verification code'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verify email' }));
    await waitFor(() => expect(verifyEmail).toHaveBeenCalledWith({ email: 'new@example.com', code: '123456' }));
    expect(await screen.findByText('Workspace loaded')).toBeTruthy();
  });

  it('explains when email verification will set the submitted password', async () => {
    loginResult = { login: {
      authenticated: false, requiresVerification: true, requiresPasswordSetup: true,
      message: 'Check your inbox.',
    } };
    renderAuth('login');
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'legacy@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'new-long-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Verify and set your password' })).toBeTruthy();
    expect(screen.getByText(/The password you entered will be set after verification\./)).toBeTruthy();
  });

  it('collects name, persona and password and starts OTP verification', async () => {
    renderAuth('register');
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Asha' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'asha@example.com' } });
    fireEvent.change(screen.getByLabelText('Persona'), { target: { value: 'Consulting' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'long-test-password' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(register).toHaveBeenCalledWith({
      name: 'Asha', email: 'asha@example.com', password: 'long-test-password', persona: 'Consulting',
    }));
    expect(await screen.findByLabelText('Verification code')).toBeTruthy();
  });

  it('offers Google sign-in and can resend an OTP', async () => {
    renderAuth('login');
    expect(screen.getByRole('link', { name: /continue with google/i }).getAttribute('href')).toBe('/auth/google');
    cleanup();
    renderAuth('verify');
    fireEvent.click(screen.getByRole('button', { name: 'Resend code' }));
    await waitFor(() => expect(resendCode).toHaveBeenCalledWith('asha@example.com'));
  });
});