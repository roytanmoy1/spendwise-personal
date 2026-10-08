import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import ShowChartRoundedIcon from '@mui/icons-material/ShowChartRounded';
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded';
import { useLoginMutation, useRegisterMutation, useResendVerificationCodeMutation, useVerifyEmailMutation } from '../../shared/api/api';
import './auth.css';

const OAUTH_ERRORS = {
  google: 'Google sign-in could not be completed. Try again or use email.',
  google_email: 'Google could not confirm this email address. Use email verification instead.',
  email: 'Email delivery is unavailable. Contact the administrator.',
  google_not_configured: 'Google sign-in is not configured for this deployment.',
};

export default function AuthPage({ mode = 'login' }) {
  const isRegister = mode === 'register';
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(mode === 'verify' ? 'verify' : 'credentials');
  const [name, setName] = useState('');
  const [email, setEmail] = useState(() => searchParams.get('email') || '');
  const [persona, setPersona] = useState('Personal');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [passwordSetupRequired, setPasswordSetupRequired] = useState(false);
  const [error, setError] = useState(() => OAUTH_ERRORS[searchParams.get('error')] || '');
  const [notice, setNotice] = useState('');
  const [login, loginState] = useLoginMutation();
  const [register, registerState] = useRegisterMutation();
  const [verifyEmail, verifyState] = useVerifyEmailMutation();
  const [resendCode, resendState] = useResendVerificationCodeMutation();
  const navigate = useNavigate();

  async function handleCredentials(event) {
    event.preventDefault();
    setError('');
    setNotice('');
    try {
      const variables = { email: email.trim(), password };
      const result = isRegister
        ? await register({ ...variables, name: name.trim(), persona: persona.trim() || 'Personal' }).unwrap()
        : await login(variables).unwrap();
      const outcome = result[isRegister ? 'register' : 'login'];
      if (outcome?.requiresRegistration) {
        navigate(`/register?email=${encodeURIComponent(email.trim())}`, { replace: true });
      } else if (outcome?.authenticated) {
        navigate('/', { replace: true });
      } else if (outcome?.requiresVerification) {
        setNotice(outcome.message || 'Check your inbox for a verification code.');
        setPasswordSetupRequired(Boolean(outcome.requiresPasswordSetup));
        setStep('verify');
      } else {
        setError('Your account could not be opened.');
      }
    } catch (requestError) {
      setError(requestError.message || 'Your account could not be opened.');
    }
  }

  async function handleVerify(event) {
    event.preventDefault();
    setError('');
    try {
      await verifyEmail({ email: email.trim(), code: code.trim() }).unwrap();
      navigate('/', { replace: true });
    } catch (requestError) {
      setError(requestError.message || 'That code could not be verified.');
    }
  }

  async function handleResend() {
    setError('');
    setNotice('');
    try {
      await resendCode(email.trim()).unwrap();
      setNotice('If this account needs verification, a new code was sent.');
    } catch (requestError) {
      setError(requestError.message || 'A new code could not be sent.');
    }
  }

  const working = loginState.isLoading || registerState.isLoading || verifyState.isLoading || resendState.isLoading;
  return <div className="auth-screen">
    <div className="auth-main">
      <Link to="/" className="auth-brand"><span className="brand-symbol"><ShowChartRoundedIcon fontSize="small" /></span>
        <span>spendwise</span></Link>
      <div className="auth-form-area">
        <span className="eyebrow">PERSONAL FINANCE</span>
        <h1>{step === 'verify'
          ? passwordSetupRequired ? 'Verify and set your password' : 'Verify your email'
          : isRegister ? 'Create your account' : 'Welcome back'}</h1>
        <p>{step === 'verify'
          ? `${passwordSetupRequired ? 'Enter the code sent to' : 'Enter the six-digit code sent to'} ${email || 'your email'}.${passwordSetupRequired ? ' The password you entered will be set after verification.' : ''}`
          : isRegister ? 'Start with a clearer view of your spending.' : 'Sign in to your workspace.'}</p>

        {step === 'credentials' ? <form onSubmit={handleCredentials} className="auth-form">
          {isRegister && <><label htmlFor="auth-name">Name</label>
            <input id="auth-name" type="text" required minLength={1} maxLength={80} autoComplete="name"
              value={name} onChange={(event) => setName(event.target.value)} /></>}
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" required maxLength={254} autoComplete="email"
            value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
          {isRegister && <>
            <label htmlFor="auth-persona">Persona / workspace</label>
            <input id="auth-persona" aria-label="Persona" type="text" maxLength={80} value={persona}
              onChange={(event) => setPersona(event.target.value)} placeholder="Personal, Client A..." />
          </>}
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" required minLength={12} maxLength={128}
            autoComplete={isRegister ? 'new-password' : 'current-password'} value={password}
            onChange={(event) => setPassword(event.target.value)} />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button button-primary auth-submit" disabled={working}>
            {working ? 'One moment...' : isRegister ? 'Create account' : 'Sign in'} <ArrowForwardRoundedIcon fontSize="small" />
          </button>
        </form> : <form onSubmit={handleVerify} className="auth-form">
          <label htmlFor="auth-email-verify">Email</label>
          <input id="auth-email-verify" type="email" required maxLength={254} autoComplete="email"
            value={email} onChange={(event) => setEmail(event.target.value)} />
          <label htmlFor="auth-code">Verification code</label>
          <input id="auth-code" type="text" inputMode="numeric" autoComplete="one-time-code"
            required minLength={6} maxLength={6} pattern="[0-9]{6}" value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} />
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="button button-primary auth-submit" disabled={working || code.length !== 6}>
            {verifyState.isLoading ? 'Verifying...' : 'Verify email'} <ArrowForwardRoundedIcon fontSize="small" />
          </button>
          <button type="button" className="text-link auth-resend" disabled={working} onClick={handleResend}>
            {resendState.isLoading ? 'Sending...' : 'Resend code'}
          </button>
          <Link className="text-link auth-back" to="/login">Back to sign in</Link>
        </form>}

        {step === 'credentials' && <>
          <div className="auth-alt">
            <span>{isRegister ? 'Already have an account?' : 'New to SpendWise?'}</span>
            <Link className="text-link" to={isRegister ? '/login' : '/register'}>
              {isRegister ? 'Sign in' : 'Create an account'}</Link>
          </div>
          <a className="button auth-google-button" href="/auth/google">Continue with Google</a>
        </>}
      </div>
    </div>
    <aside className="auth-preview" aria-label="Sample spending snapshot">
      <div className="preview-top"><span className="eyebrow">SAMPLE WORKSPACE</span></div>
      <div className="preview-content"><span className="eyebrow">OCTOBER SNAPSHOT</span><strong>₹24,680.00</strong>
        <div className="preview-graph" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
        <div className="preview-line"><span>Groceries</span><strong>₹8,450.00</strong></div>
        <div className="preview-line"><span>Food & drink</span><strong>₹5,120.00</strong></div>
        <div className="preview-line"><span>Transport</span><strong>₹3,950.00</strong></div>
      </div>
    </aside>
  </div>;
}
