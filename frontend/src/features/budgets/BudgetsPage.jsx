import { useState } from 'react';
import SavingsRoundedIcon from '@mui/icons-material/SavingsRounded';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import { useGetBudgetsQuery, useSetBudgetMutation } from '../../shared/api/api';
import { CATEGORIES } from '../../shared/constants';
import { formatMoney, formatMonth, parseMoney } from '../../shared/format';
import { EmptyState, ErrorState, PageSkeleton } from '../../shared/ui/AsyncState';
import './budgets.css';

export default function BudgetsPage() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [category, setCategory] = useState('FOOD');
  const [amount, setAmount] = useState('');
  const [notice, setNotice] = useState(null);
  const { data: budgets = [], isLoading, isError, refetch } = useGetBudgetsQuery(month);
  const [setBudget, { isLoading: saving }] = useSetBudgetMutation();

  async function handleSubmit(event) {
    event.preventDefault();
    const limitMinor = parseMoney(amount);
    if (!limitMinor) {
      setNotice({ kind: 'error', message: 'Enter a positive amount with at most two decimal places.' });
      return;
    }
    try {
      await setBudget({ category, month, limitMinor }).unwrap();
      setAmount('');
      setNotice({ kind: 'success', message: 'Budget saved.' });
    } catch (error) {
      setNotice({ kind: 'error', message: error.message || 'Budget could not be saved.' });
    }
  }

  if (isLoading) return <PageSkeleton label="Loading budgets" />;
  if (isError) return <ErrorState message="Budgets could not be loaded." onRetry={refetch} />;

  const allocated = budgets.reduce((sum, budget) => sum + budget.limitMinor, 0);
  const spent = budgets.reduce((sum, budget) => sum + budget.spentMinor, 0);

  return <div className="page budgets-page">
    <header className="page-heading">
      <div><span className="eyebrow">CATEGORY PLANNING</span><h1>Budgets</h1>
        <p>{formatMonth(month)}</p></div>
      <div className="month-picker"><label htmlFor="budget-month">Month</label>
        <input id="budget-month" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></div>
    </header>

    <div className="budget-rollup" aria-label="Total monthly budget progress">
      <span className="rollup-icon"><SavingsRoundedIcon fontSize="small" /></span>
      <div><span className="eyebrow">TOTAL ALLOCATED</span><strong>{formatMoney(allocated)}</strong></div>
      <div><span className="eyebrow">SPENT SO FAR</span><strong>{formatMoney(spent)}</strong></div>
      <div><span className="eyebrow">REMAINING</span><strong>{formatMoney(Math.max(allocated - spent, 0))}</strong></div>
    </div>

    {notice && <div className={`notice notice-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      {notice.message}<button type="button" aria-label="Dismiss notification" onClick={() => setNotice(null)}>×</button></div>}

    <div className="budget-workspace">
      <section className="data-panel budget-list-panel" aria-labelledby="budget-list-heading">
        <div className="section-heading"><div><span className="eyebrow">{formatMonth(month).toUpperCase()}</span>
          <h2 id="budget-list-heading">Category limits</h2></div><span className="item-count">{budgets.length} active</span></div>
        {budgets.length ? <div className="budget-list">{budgets.map((budget) => {
          const info = CATEGORIES[budget.category] || CATEGORIES.OTHER;
          const percent = Math.round(budget.spentMinor / budget.limitMinor * 100);
          return <div className="budget-item" key={budget.id}>
            <div className="budget-item-top"><span className="budget-category"><span className="category-dot" style={{ background: info.color }} />
              {info.label}</span><span className={`budget-percent ${percent > 100 ? 'over-limit' : ''}`}>
                {percent}%</span></div>
            <div className="progress-track budget-progress" role="progressbar" aria-label={`${info.label} budget`}
              aria-valuenow={Math.min(percent, 100)} aria-valuemin={0} aria-valuemax={100}>
              <span style={{ width: `${Math.min(percent, 100)}%`, backgroundColor: percent > 100 ? '#cb654e' : info.color }} /></div>
            <div className="budget-item-bottom"><span>{formatMoney(budget.spentMinor)} spent</span><span>{formatMoney(budget.limitMinor)} limit</span></div>
          </div>;
        })}</div> : <EmptyState title="No budgets for this month" detail="Your category limits will appear here." />}
      </section>

      <section className="data-panel budget-editor" aria-labelledby="budget-editor-heading">
        <div className="section-heading"><div><span className="eyebrow">MONTHLY PLAN</span>
          <h2 id="budget-editor-heading">Set a limit</h2></div><AddRoundedIcon fontSize="small" aria-hidden="true" /></div>
        <form className="budget-form" onSubmit={handleSubmit}>
          <label htmlFor="budget-category">Category</label>
          <select id="budget-category" value={category} onChange={(event) => setCategory(event.target.value)}>
            {Object.entries(CATEGORIES).map(([value, info]) => <option key={value} value={value}>{info.label}</option>)}
          </select>
          <label htmlFor="budget-amount">Limit (INR)</label>
          <input id="budget-amount" required type="text" inputMode="decimal" placeholder="0.00"
            value={amount} onChange={(event) => setAmount(event.target.value)} />
          <button className="button button-primary" type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save budget'}</button>
        </form>
      </section>
    </div>
  </div>;
}