import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip,
} from 'chart.js';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import ArrowForwardRoundedIcon from '@mui/icons-material/ArrowForwardRounded';
import AccountBalanceWalletRoundedIcon from '@mui/icons-material/AccountBalanceWalletRounded';
import ReceiptLongRoundedIcon from '@mui/icons-material/ReceiptLongRounded';
import TrendingUpRoundedIcon from '@mui/icons-material/TrendingUpRounded';
import { useGetOverviewQuery, useGetTransactionsQuery, useGetBudgetsQuery } from '../../shared/api/api';
import { CATEGORIES, METHODS } from '../../shared/constants';
import { formatDate, formatMoney, formatMonth } from '../../shared/format';
import { EmptyState, ErrorState, PageSkeleton } from '../../shared/ui/AsyncState';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 480 },
  plugins: { legend: { display: false }, tooltip: {
    callbacks: { label: (context) => formatMoney(context.parsed.y) },
  } },
  scales: {
    x: { grid: { display: false }, border: { display: false }, ticks: { color: '#708079', font: { family: 'Manrope' } } },
    y: { grid: { color: '#e7eeea' }, border: { display: false, dash: [4, 4] },
      ticks: { color: '#708079', callback: (value) => formatMoney(value), maxTicksLimit: 5 } },
  },
};

const TrendChart = memo(function TrendChart({ months }) {
  const data = useMemo(() => ({
    labels: months.map(({ month }) => formatMonth(month)),
    datasets: [{
      data: months.map(({ amountMinor }) => amountMinor),
      borderColor: '#23785f', backgroundColor: 'rgba(46, 135, 102, 0.12)',
      fill: true, tension: 0.35, pointBackgroundColor: '#23785f', pointRadius: 3, borderWidth: 2.5,
    }],
  }), [months]);

  return <div className="chart-frame" role="img" aria-label="Monthly spending trend">
    <Line options={chartOptions} data={data} />
  </div>;
});

function Metric({ title, value, note, icon: Icon }) {
  return <div className="metric">
    <div className="metric-top"><span>{title}</span><Icon fontSize="small" aria-hidden="true" /></div>
    <strong>{value}</strong>
    <small>{note}</small>
  </div>;
}

export default function DashboardPage({ viewer }) {
  const overviewQuery = useGetOverviewQuery();
  const recentQuery = useGetTransactionsQuery({ limit: 5, offset: 0 });
  const budgetQuery = useGetBudgetsQuery(new Date().toISOString().slice(0, 7));

  if (overviewQuery.isLoading) return <PageSkeleton label="Loading dashboard" />;
  if (overviewQuery.isError) return <ErrorState message="Your spending summary is unavailable." onRetry={overviewQuery.refetch} />;

  const overview = overviewQuery.data;
  const recent = recentQuery.data?.items || [];
  const budgets = budgetQuery.data || [];
  const previous = overview.lastMonthMinor;
  const change = previous ? Math.round(((overview.thisMonthMinor - previous) / previous) * 100) : null;

  return (
    <div className="page dashboard-page">
      <header className="page-heading">
        <div>
          <div className="eyebrow">SPENDING INTELLIGENCE / {formatMonth(new Date().toISOString().slice(0, 7)).toUpperCase()}</div>
          <h1>Overview</h1>
          <p>Welcome back, {viewer?.name?.split(' ')[0] || 'there'}.</p>
        </div>
        <Link className="button button-primary" to="/transactions?new=1"><AddRoundedIcon fontSize="small" /> New transaction</Link>
      </header>

      <section className="metric-grid" aria-label="Spending at a glance">
        <Metric title="Spent this month" value={formatMoney(overview.thisMonthMinor)}
          note={change === null ? 'No prior month' : `${change > 0 ? '+' : ''}${change}% from last month`}
          icon={AccountBalanceWalletRoundedIcon} />
        <Metric title="Previous month" value={formatMoney(previous)}
          note="The month before this one" icon={TrendingUpRoundedIcon} />
        <Metric title="All-time spend" value={formatMoney(overview.totalSpentMinor)}
          note={`${overview.transactionCount} transactions`} icon={ReceiptLongRoundedIcon} />
      </section>

      <div className="insights-grid">
        <section className="data-panel trend-panel" aria-labelledby="trend-heading">
          <div className="section-heading"><div><span className="eyebrow">TIME SERIES</span><h2 id="trend-heading">Spending over time</h2></div></div>
          {overview.monthly.length ? <TrendChart months={overview.monthly} />
            : <EmptyState title="No transactions yet" detail="Your trend will appear here." />}
        </section>
        <section className="data-panel category-panel" aria-labelledby="category-heading">
          <div className="section-heading"><div><span className="eyebrow">THIS MONTH</span><h2 id="category-heading">Where it went</h2></div></div>
          {overview.byCategory.length ? <div className="category-list">
            {overview.byCategory.map(({ category, amountMinor }) => (
              <div className="category-row" key={category}>
                <div className="category-row-label"><span className="category-dot" style={{ backgroundColor: CATEGORIES[category]?.color }} />
                  <span>{CATEGORIES[category]?.label || category}</span><strong>{formatMoney(amountMinor)}</strong></div>
                <div className="progress-track"><span style={{ width: `${Math.min(100, (amountMinor / Math.max(overview.thisMonthMinor, 1)) * 100)}%`,
                  backgroundColor: CATEGORIES[category]?.color }} /></div>
              </div>
            ))}
          </div> : <EmptyState title="No spending this month" />}
        </section>
      </div>

      <div className="insights-grid bottom-grid">
        <section className="data-panel" aria-labelledby="recent-heading">
          <div className="section-heading"><div><span className="eyebrow">LATEST ACTIVITY</span><h2 id="recent-heading">Recent transactions</h2></div>
            <Link className="text-link" to="/transactions">See all <ArrowForwardRoundedIcon fontSize="small" /></Link></div>
          {recentQuery.isLoading ? <div className="skeleton skeleton-list" role="status" aria-label="Loading recent transactions" />
            : recentQuery.isError ? <ErrorState onRetry={recentQuery.refetch} />
              : recent.length ? <ul className="recent-list">{recent.map((transaction) => (
                <li key={transaction.id}>
                  <span className="merchant-mark" style={{ '--mark-color': CATEGORIES[transaction.category]?.color }}>
                    {transaction.merchant.charAt(0).toUpperCase()}</span>
                  <div className="recent-detail"><strong>{transaction.merchant}</strong><small>{formatDate(transaction.occurredAt)} · {METHODS[transaction.method]}</small></div>
                  <span className="recent-amount">-{formatMoney(transaction.amountMinor)}</span>
                </li>
              ))}</ul> : <EmptyState title="No transactions yet" />}
        </section>
        <section className="data-panel side-summary" aria-labelledby="budget-heading">
          <div className="section-heading"><div><span className="eyebrow">STAY ON TRACK</span><h2 id="budget-heading">Budgets</h2></div>
            <Link className="text-link" to="/budgets">Manage <ArrowForwardRoundedIcon fontSize="small" /></Link></div>
          {budgetQuery.isLoading ? <div className="skeleton skeleton-list" role="status" aria-label="Loading budgets" />
            : budgets.length ? <div className="budget-preview">{budgets.slice(0, 3).map((budget) => (
              <div key={budget.id} className="budget-preview-row"><div><strong>{CATEGORIES[budget.category]?.label}</strong>
                <small>{formatMoney(budget.spentMinor)} of {formatMoney(budget.limitMinor)}</small></div>
                <div className="progress-track"><span style={{ width: `${Math.min(100, budget.spentMinor / budget.limitMinor * 100)}%` }} /></div></div>
            ))}</div> : <EmptyState title="No budgets set" action={<Link to="/budgets" className="text-link">Set a budget</Link>} />}
          <div className="method-breakdown"><span className="eyebrow">PAYMENT MIX</span>
            {overview.byMethod.map(({ method, amountMinor }) => <div key={method} className="method-row"><span>{METHODS[method]}</span>
              <strong>{formatMoney(amountMinor)}</strong></div>)}
          </div>
          <div className="city-breakdown"><span className="eyebrow">SPENDING BY CITY</span>
            {overview.byCity?.length ? overview.byCity.map(({ city, amountMinor }) => <div key={city} className="method-row">
              <span>{city}</span><strong>{formatMoney(amountMinor)}</strong></div>)
              : <small className="muted-note">No city data this month</small>}
          </div>
        </section>
      </div>
    </div>
  );
}