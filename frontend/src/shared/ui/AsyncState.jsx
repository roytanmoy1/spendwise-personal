import ReplayRoundedIcon from '@mui/icons-material/ReplayRounded';

export function PageSkeleton({ label = 'Loading dashboard' }) {
  return (
    <div className="page page-skeleton" role="status" aria-label={label}>
      <span className="skeleton skeleton-heading" aria-hidden="true" />
      <div className="metric-grid" aria-hidden="true">
        <span className="skeleton skeleton-metric" />
        <span className="skeleton skeleton-metric" />
        <span className="skeleton skeleton-metric" />
      </div>
      <span className="skeleton skeleton-chart" aria-hidden="true" />
    </div>
  );
}

export function ErrorState({ message = 'This view could not be loaded.', onRetry }) {
  return (
    <div className="page-state" role="alert">
      <h2>Something went wrong</h2>
      <p>{message}</p>
      {onRetry && <button className="button button-primary" type="button" onClick={onRetry}>
        <ReplayRoundedIcon fontSize="small" /> Retry
      </button>}
    </div>
  );
}

export function EmptyState({ title, detail, action }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      {detail && <p>{detail}</p>}
      {action}
    </div>
  );
}