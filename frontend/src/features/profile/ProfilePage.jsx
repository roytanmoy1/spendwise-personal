import { useEffect, useState } from 'react';
import VerifiedUserRoundedIcon from '@mui/icons-material/VerifiedUserRounded';
import { useGetViewerQuery, useUpdateProfileMutation } from '../../shared/api/api';
import { ErrorState, PageSkeleton } from '../../shared/ui/AsyncState';
import './profile.css';

const ROLE_LABELS = { VIEWER: 'Viewer', EDITOR: 'Editor', ADMIN: 'Admin', SUPERADMIN: 'Superadmin' };
const STATUS_LABELS = { EMAIL_PENDING: 'Verify email', PENDING_REVIEW: 'Awaiting role', ACTIVE: 'Active', SUSPENDED: 'Suspended' };

export default function ProfilePage() {
  const { data: viewer, isLoading, isError, refetch } = useGetViewerQuery();
  const [updateProfile, { isLoading: saving }] = useUpdateProfileMutation();
  const [name, setName] = useState('');
  const [persona, setPersona] = useState('');
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    if (viewer) {
      setName(viewer.name);
      setPersona(viewer.persona || 'Personal');
    }
  }, [viewer]);

  async function handleSubmit(event) {
    event.preventDefault();
    setNotice(null);
    try {
      await updateProfile({ name: name.trim(), persona: persona.trim() }).unwrap();
      setNotice({ kind: 'success', text: 'Profile saved.' });
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'Profile could not be saved.' });
    }
  }

  if (isLoading) return <PageSkeleton label="Loading profile" />;
  if (isError || !viewer) return <ErrorState message="Your profile could not be loaded." onRetry={refetch} />;

  return <div className="page profile-page">
    <header className="page-heading">
      <div><span className="eyebrow">ACCOUNT & IDENTITY</span><h1>Profile</h1>
        <p>Manage the identity attached to this email workspace.</p></div>
    </header>
    <div className="profile-layout">
      <section className="data-panel profile-editor" aria-labelledby="profile-details-heading">
        <div className="section-heading"><div><span className="eyebrow">PERSONAL DETAILS</span>
          <h2 id="profile-details-heading">Workspace profile</h2></div></div>
        <form className="profile-form" onSubmit={handleSubmit}>
          <label htmlFor="profile-name">Display name</label>
          <input id="profile-name" required minLength={1} maxLength={80} value={name}
            onChange={(event) => setName(event.target.value)} />
          <label htmlFor="profile-email">Login email</label>
          <input id="profile-email" type="email" value={viewer.email} readOnly aria-describedby="email-help" />
          <small id="email-help" className="field-help">Email changes require a new verification flow.</small>
          <label htmlFor="profile-persona">Persona / workspace</label>
          <input id="profile-persona" required minLength={1} maxLength={80} value={persona}
            onChange={(event) => setPersona(event.target.value)} />
          {notice && <p className={`notice notice-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>{notice.text}</p>}
          <button className="button button-primary" type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save profile'}
          </button>
        </form>
      </section>
      <aside className="data-panel profile-access" aria-labelledby="access-heading">
        <div className="profile-access-icon"><VerifiedUserRoundedIcon fontSize="small" /></div>
        <span className="eyebrow">ACCESS</span><h2 id="access-heading">Your permissions</h2>
        <dl className="access-list">
          <div><dt>Role</dt><dd>{ROLE_LABELS[viewer.role] || viewer.role}</dd></div>
          <div><dt>Status</dt><dd>{STATUS_LABELS[viewer.status] || viewer.status}</dd></div>
          <div><dt>Email verified</dt><dd>{viewer.emailVerified ? 'Yes' : 'No'}</dd></div>
        </dl>
        {viewer.status === 'PENDING_REVIEW' && <p className="access-pending">Your account can view spending data. An administrator must assign a role before you can make changes.</p>}
      </aside>
    </div>
  </div>;
}