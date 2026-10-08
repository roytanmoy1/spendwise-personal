import { lazy, Suspense, useState } from 'react';
import { BrowserRouter, Link, NavLink, Navigate, Outlet, Route, Routes, useNavigate } from 'react-router-dom';
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded';
import ReceiptLongRoundedIcon from '@mui/icons-material/ReceiptLongRounded';
import DonutLargeRoundedIcon from '@mui/icons-material/DonutLargeRounded';
import ShowChartRoundedIcon from '@mui/icons-material/ShowChartRounded';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import PersonOutlineRoundedIcon from '@mui/icons-material/PersonOutlineRounded';
import AdminPanelSettingsRoundedIcon from '@mui/icons-material/AdminPanelSettingsRounded';
import { useGetViewerQuery, useLogoutMutation } from '../shared/api/api';
import { ErrorState, PageSkeleton } from '../shared/ui/AsyncState';
import ErrorBoundary from '../shared/ui/ErrorBoundary';

const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'));
const TransactionsPage = lazy(() => import('../features/transactions/TransactionsPage'));
const BudgetsPage = lazy(() => import('../features/budgets/BudgetsPage'));
const AuthPage = lazy(() => import('../features/auth/AuthPage'));
const ProfilePage = lazy(() => import('../features/profile/ProfilePage'));
const AdminPage = lazy(() => import('../features/admin/AdminPage'));

const navigation = [
  { to: '/', label: 'Overview', icon: DashboardRoundedIcon, end: true },
  { to: '/transactions', label: 'Transactions', icon: ReceiptLongRoundedIcon },
  { to: '/budgets', label: 'Budgets', icon: DonutLargeRoundedIcon },
  { to: '/profile', label: 'Profile', icon: PersonOutlineRoundedIcon },
];

function Workspace() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { data: viewer, error, isLoading, refetch } = useGetViewerQuery();
  const [logout, logoutState] = useLogoutMutation();
  const navigate = useNavigate();
  const workspaceNavigation = viewer && ['ADMIN', 'SUPERADMIN'].includes(viewer.role)
    ? [...navigation, { to: '/admin', label: 'User access', icon: AdminPanelSettingsRoundedIcon }]
    : navigation;

  async function handleLogout() {
    try {
      await logout().unwrap();
      navigate('/login');
    } catch {
      refetch();
    }
  }

  if (isLoading) {
    return <PageSkeleton label="Loading dashboard" />;
  }
  if (error?.status && error.status !== 401) {
    return <ErrorState message="We could not reach the spending service." onRetry={refetch} />;
  }
  if (!viewer) return <Navigate to="/login" replace />;

  return (
    <div className="app-shell">
      {menuOpen && <button className="nav-scrim" type="button" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`} aria-label="Main navigation">
        <div className="brand-row">
          <Link to="/" className="brand" onClick={() => setMenuOpen(false)}>
            <span className="brand-symbol"><ShowChartRoundedIcon fontSize="small" /></span>
            <span>spendwise<small>PERSONAL FINANCE</small></span>
          </Link>
          <button className="icon-button mobile-close" type="button" aria-label="Close menu" onClick={() => setMenuOpen(false)}>
            <CloseRoundedIcon fontSize="small" />
          </button>
        </div>
        <div className="nav-section-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Views">
          {workspaceNavigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`}>
              <Icon fontSize="small" aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note"><span className="privacy-indicator" />{viewer.persona || 'Personal workspace'}</div>
          <button className="nav-link nav-logout" type="button" onClick={handleLogout} disabled={logoutState.isLoading}>
            <LogoutRoundedIcon fontSize="small" aria-hidden="true" /><span>Sign out</span>
          </button>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" type="button" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
              <MenuRoundedIcon fontSize="small" />
            </button>
            <span className="topbar-label">SPENDWISE / YOUR WORKSPACE</span>
          </div>
          <div className="topbar-right"><span className="topbar-user">{viewer.persona || 'Personal'} · {viewer.name}</span>
            <span className="user-avatar" aria-hidden="true">{viewer.name.charAt(0).toUpperCase()}</span>
          </div>
        </header>
        {viewer.status === 'PENDING_REVIEW' && <div className="pending-access-note" role="status">
          <strong>View-only access</strong><span>An admin has been notified. Editing will be enabled after a role is assigned.</span>
        </div>}
        <main id="main-content" className="workspace-content">
          <Suspense fallback={<PageSkeleton label="Loading dashboard" />}><Outlet context={{ viewer }} /></Suspense>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return <BrowserRouter>
    <ErrorBoundary>
    <Routes>
      <Route path="/login" element={<Suspense fallback={<PageSkeleton label="Loading sign in" />}><AuthPage mode="login" /></Suspense>} />
      <Route path="/register" element={<Suspense fallback={<PageSkeleton label="Loading registration" />}><AuthPage mode="register" /></Suspense>} />
      <Route path="/verify-email" element={<Suspense fallback={<PageSkeleton label="Loading verification" />}><AuthPage mode="verify" /></Suspense>} />
      <Route element={<Workspace />}>
        <Route path="/" element={<DashboardRoute />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/budgets" element={<BudgetsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </ErrorBoundary>
  </BrowserRouter>;
}

function DashboardRoute() {
  const viewer = useGetViewerQuery().data;
  return <DashboardPage viewer={viewer} />;
}