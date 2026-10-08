import { useState } from 'react';
import NotificationsActiveRoundedIcon from '@mui/icons-material/NotificationsActiveRounded';
import PersonAddAltRoundedIcon from '@mui/icons-material/PersonAddAltRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import { useGetAdminNotificationsQuery, useGetManagedUsersQuery, useGetPendingUsersQuery,
  useGetViewerQuery, useAssignRoleMutation, useCreateUserMutation,
  useMarkAdminNotificationReadMutation, useRemoveUserMutation } from '../../shared/api/api';
import { EmptyState, ErrorState, PageSkeleton } from '../../shared/ui/AsyncState';
import './admin.css';

const ROLE_LABELS = { VIEWER: 'Viewer', EDITOR: 'Editor', ADMIN: 'Admin', SUPERADMIN: 'Superadmin' };
const STATUS_LABELS = { EMAIL_PENDING: 'Email pending', PENDING_REVIEW: 'Needs review', ACTIVE: 'Active', SUSPENDED: 'Suspended' };

export default function AdminPage() {
  const { data: viewer, isLoading: viewerLoading } = useGetViewerQuery();
  const isSuperadmin = viewer?.role === 'SUPERADMIN';
  const pendingQuery = useGetPendingUsersQuery();
  const notificationsQuery = useGetAdminNotificationsQuery();
  const usersQuery = useGetManagedUsersQuery(undefined, { skip: !isSuperadmin });
  const [assignRole, assignState] = useAssignRoleMutation();
  const [createUser, createState] = useCreateUserMutation();
  const [removeUser] = useRemoveUserMutation();
  const [markRead] = useMarkAdminNotificationReadMutation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [persona, setPersona] = useState('Work');
  const [notice, setNotice] = useState(null);

  async function changeRole(user, role) {
    setNotice(null);
    try {
      await assignRole({ userId: user.id, role }).unwrap();
      setNotice({ kind: 'success', text: `Role updated for ${user.email}.` });
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'Role could not be updated.' });
    }
  }

  async function handleCreate(event) {
    event.preventDefault();
    setNotice(null);
    try {
      const result = await createUser({ name: name.trim(), email: email.trim(), persona: persona.trim() || 'Work' }).unwrap();
      setName(''); setEmail('');
      setNotice({ kind: 'success', text: result.createUser.message || 'Verification instructions sent.' });
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'User could not be invited.' });
    }
  }

  async function handleRemove(user) {
    if (!window.confirm(`Permanently remove ${user.email} and their workspace data?`)) return;
    try {
      await removeUser(user.id).unwrap();
      setNotice({ kind: 'success', text: `${user.email} was removed.` });
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'User could not be removed.' });
    }
  }

  async function handleRead(notification) {
    try {
      await markRead(notification.id).unwrap();
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'Notification could not be updated.' });
    }
  }

  if (viewerLoading || pendingQuery.isLoading || notificationsQuery.isLoading || (isSuperadmin && usersQuery.isLoading)) {
    return <PageSkeleton label="Loading user access" />;
  }
  if (!viewer || !['ADMIN', 'SUPERADMIN'].includes(viewer.role)) {
    return <ErrorState message="Administrator access is required." />;
  }
  if (pendingQuery.isError || notificationsQuery.isError || (isSuperadmin && usersQuery.isError)) {
    return <ErrorState message="User access data could not be loaded." onRetry={() => {
      pendingQuery.refetch(); notificationsQuery.refetch(); if (isSuperadmin) usersQuery.refetch();
    }} />;
  }

  const pendingUsers = pendingQuery.data || [];
  const notifications = notificationsQuery.data || [];
  const managedAccounts = (usersQuery.data || []).filter((user) => user.status !== 'PENDING_REVIEW');
  const assignableRoles = isSuperadmin ? ['VIEWER', 'EDITOR', 'ADMIN'] : ['VIEWER', 'EDITOR'];

  return <div className="page admin-page">
    <header className="page-heading"><div><span className="eyebrow">IDENTITY & PERMISSIONS</span><h1>User access</h1>
      <p>Review verified requests and manage workspace roles.</p></div>
      <span className="admin-role-label">{ROLE_LABELS[viewer.role]}</span></header>
    {notice && <div className={`notice notice-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      {notice.text}<button type="button" aria-label="Dismiss notification" onClick={() => setNotice(null)}>×</button></div>}

    <section className="data-panel admin-section" aria-labelledby="requests-heading">
      <div className="section-heading"><div><span className="eyebrow">VERIFIED EMAILS</span><h2 id="requests-heading">Access requests</h2></div>
        <span className="item-count">{pendingUsers.length} pending</span></div>
      {pendingUsers.length ? <div className="admin-user-list">{pendingUsers.map((user) => <article className="admin-user-row" key={user.id}>
        <div className="admin-user-identity"><span className="user-avatar">{user.name.charAt(0).toUpperCase()}</span>
          <div><strong>{user.name}</strong><small>{user.email} · {user.persona}</small></div></div>
        <label className="sr-only" htmlFor={`role-${user.id}`}>Role for {user.email}</label>
        <select id={`role-${user.id}`} aria-label={`Role for ${user.email}`} defaultValue={user.role}
          disabled={assignState.isLoading} onChange={(event) => changeRole(user, event.target.value)}>
          {assignableRoles.map((role) => <option value={role} key={role}>{ROLE_LABELS[role]}</option>)}
        </select>
        <span className="admin-status">{STATUS_LABELS[user.status]}</span>
        {isSuperadmin && <button className="icon-button admin-remove" type="button" aria-label={`Remove ${user.email}`}
          onClick={() => handleRemove(user)}><DeleteOutlineRoundedIcon fontSize="small" /></button>}
      </article>)}</div> : <EmptyState title="No access requests" detail="Verified new accounts will appear here." />}
    </section>

    <section className="data-panel admin-section" aria-labelledby="notifications-heading">
      <div className="section-heading"><div><span className="eyebrow">ACTIVITY</span><h2 id="notifications-heading">Admin notifications</h2></div>
        <NotificationsActiveRoundedIcon fontSize="small" aria-hidden="true" /></div>
      {notifications.length ? <ul className="admin-notifications">{notifications.map((notification) => <li key={notification.id}>
        <div><strong>{notification.applicantEmail}</strong><small>{notification.event === 'access_requested' ? 'Verified email is waiting for a role.' : notification.event}</small></div>
        {!notification.read && <button className="text-link" type="button" aria-label="Mark notification read" onClick={() => handleRead(notification)}>Mark read</button>}
      </li>)}</ul> : <EmptyState title="You're all caught up" />}
    </section>

    {isSuperadmin && <>
      <section className="data-panel admin-section" aria-labelledby="active-users-heading">
        <div className="section-heading"><div><span className="eyebrow">ACTIVE ACCOUNTS</span><h2 id="active-users-heading">Managed users</h2></div>
          <span className="item-count">{managedAccounts.length} accounts</span></div>
          {managedAccounts.length ? <div className="admin-user-list">{managedAccounts.map((user) => <article className="admin-user-row" key={user.id}>
          <div className="admin-user-identity"><span className="user-avatar">{user.name.charAt(0).toUpperCase()}</span>
            <div><strong>{user.name}</strong><small>{user.email} · {user.persona}</small></div></div>
          <label className="sr-only" htmlFor={`managed-role-${user.id}`}>Role for {user.email}</label>
          <select id={`managed-role-${user.id}`} aria-label={`Role for ${user.email}`} value={user.role}
            disabled={!user.emailVerified} onChange={(event) => changeRole(user, event.target.value)}>
            {assignableRoles.map((role) => <option value={role} key={role}>{ROLE_LABELS[role]}</option>)}
          </select>
          <span className="admin-status">{STATUS_LABELS[user.status]}</span>
          <button className="icon-button admin-remove" type="button" aria-label={`Remove ${user.email}`}
            onClick={() => handleRemove(user)}><DeleteOutlineRoundedIcon fontSize="small" /></button>
        </article>)}</div> : <EmptyState title="No active users yet" />}
      </section>

      <section className="data-panel admin-section" aria-labelledby="invite-heading">
        <div className="section-heading"><div><span className="eyebrow">SUPERADMIN</span><h2 id="invite-heading">Add a user</h2></div>
          <PersonAddAltRoundedIcon fontSize="small" aria-hidden="true" /></div>
        <form className="invite-form" onSubmit={handleCreate}>
          <div><label htmlFor="new-user-name">Name</label><input id="new-user-name" aria-label="New user name" required maxLength={80} value={name} onChange={(event) => setName(event.target.value)} /></div>
          <div><label htmlFor="new-user-email">Email</label><input id="new-user-email" aria-label="New user email" type="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} /></div>
          <div><label htmlFor="new-user-persona">Persona</label><input id="new-user-persona" aria-label="New user persona" maxLength={80} value={persona} onChange={(event) => setPersona(event.target.value)} /></div>
          <button className="button button-primary" type="submit" disabled={createState.isLoading}>
            {createState.isLoading ? 'Sending...' : 'Add user'}
          </button>
        </form>
      </section>
    </>}
  </div>;
}