import { useDeferredValue, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import AddRoundedIcon from '@mui/icons-material/AddRounded';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import UploadFileRoundedIcon from '@mui/icons-material/UploadFileRounded';
import FileDownloadRoundedIcon from '@mui/icons-material/FileDownloadRounded';
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded';
import ChevronLeftRoundedIcon from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRoundedIcon from '@mui/icons-material/ChevronRightRounded';
import {
  useGetTransactionsQuery, useUpdateTransactionCategoryMutation, useDeleteTransactionMutation,
  useImportCsvMutation, useLazyExportCsvQuery,
} from '../../shared/api/api';
import { CATEGORIES, METHODS } from '../../shared/constants';
import { formatDate, formatMoney } from '../../shared/format';
import { EmptyState, ErrorState, PageSkeleton } from '../../shared/ui/AsyncState';
import AddTransactionDialog from './AddTransactionDialog';
import './transactions.css';

const PAGE_SIZE = 25;

export default function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [category, setCategory] = useState('');
  const [method, setMethod] = useState('');
  const [month, setMonth] = useState('');
  const [page, setPage] = useState(0);
  const [notice, setNotice] = useState(null);
  const fileInput = useRef(null);
  const [correctCategory] = useUpdateTransactionCategoryMutation();
  const [deleteTransaction] = useDeleteTransactionMutation();
  const [importCsv, { isLoading: importing }] = useImportCsvMutation();
  const [exportCsv, { isFetching: exporting }] = useLazyExportCsvQuery();
  const filter = useMemo(() => ({
    ...(deferredSearch.trim() ? { merchant: deferredSearch.trim() } : {}),
    ...(category ? { category } : {}), ...(method ? { method } : {}), ...(month ? { month } : {}),
  }), [deferredSearch, category, method, month]);
  const { data, isLoading, isFetching, isError, refetch } = useGetTransactionsQuery({
    limit: PAGE_SIZE, offset: page * PAGE_SIZE, filter,
  });
  const isDialogOpen = searchParams.get('new') === '1';

  function changeFilter(setter, value) {
    setter(value);
    setPage(0);
  }

  async function changeCategory(transaction, nextCategory) {
    try {
      await correctCategory({ id: transaction.id, category: nextCategory }).unwrap();
      setNotice({ kind: 'success', message: 'Category updated.' });
    } catch (error) {
      setNotice({ kind: 'error', message: error.message || 'Category could not be updated.' });
    }
  }

  async function removeTransaction(transaction) {
    if (!window.confirm(`Delete the transaction from ${transaction.merchant}?`)) return;
    try {
      await deleteTransaction(transaction.id).unwrap();
      setNotice({ kind: 'success', message: 'Transaction deleted.' });
    } catch (error) {
      setNotice({ kind: 'error', message: error.message || 'Transaction could not be deleted.' });
    }
  }

  async function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 131072) throw new Error('CSV must be 128 KB or smaller.');
      const result = await importCsv(await file.text()).unwrap();
      setPage(0);
      setNotice({ kind: 'success', message: `${result.importCsv.imported} transactions imported.` });
    } catch (error) {
      setNotice({ kind: 'error', message: error.message || 'CSV could not be imported.' });
    } finally {
      event.target.value = '';
    }
  }

  async function handleExport() {
    try {
      const csvText = await exportCsv().unwrap();
      const url = URL.createObjectURL(new Blob([csvText], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'spendwise-transactions.csv';
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setNotice({ kind: 'error', message: error.message || 'Export could not be generated.' });
    }
  }

  if (isLoading) return <PageSkeleton label="Loading transactions" />;
  if (isError) return <ErrorState message="Transactions could not be loaded." onRetry={refetch} />;

  const transactions = data?.items || [];
  return <div className="page transactions-page">
    <header className="page-heading">
      <div><span className="eyebrow">YOUR ACTIVITY</span><h1>Transactions</h1>
        <p>{data?.totalCount || 0} transactions in your account</p></div>
      <button type="button" className="button button-primary" onClick={() => setSearchParams({ new: '1' })}>
        <AddRoundedIcon fontSize="small" /> Add transaction
      </button>
    </header>

    <div className="transaction-toolbar">
      <label className="search-field" htmlFor="merchant-search"><SearchRoundedIcon fontSize="small" />
        <input id="merchant-search" aria-label="Search merchants" value={search} placeholder="Search merchants"
          onChange={(event) => changeFilter(setSearch, event.target.value)} /></label>
      <select aria-label="Filter by category" value={category} onChange={(event) => changeFilter(setCategory, event.target.value)}>
        <option value="">All categories</option>
        {Object.entries(CATEGORIES).map(([value, info]) => <option key={value} value={value}>{info.label}</option>)}
      </select>
      <select aria-label="Filter by payment method" value={method} onChange={(event) => changeFilter(setMethod, event.target.value)}>
        <option value="">All methods</option>
        {Object.entries(METHODS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input aria-label="Filter by month" type="month" value={month} onChange={(event) => changeFilter(setMonth, event.target.value)} />
      <div className="toolbar-actions">
        <input ref={fileInput} hidden type="file" accept=".csv,text/csv" onChange={handleFile} />
        <button type="button" className="button" disabled={importing} onClick={() => fileInput.current?.click()}>
          <UploadFileRoundedIcon fontSize="small" /> {importing ? 'Importing...' : 'Import CSV'}</button>
        <button type="button" className="button" disabled={exporting} onClick={handleExport}>
          <FileDownloadRoundedIcon fontSize="small" /> {exporting ? 'Exporting...' : 'Export CSV'}</button>
      </div>
    </div>

    {notice && <div className={`notice notice-${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      {notice.message}<button type="button" aria-label="Dismiss notification" onClick={() => setNotice(null)}>×</button></div>}

    <section className="data-panel transaction-panel" aria-label="Transaction history">
      <div className="transaction-panel-header"><div><strong>All transactions</strong>
        {isFetching && <small role="status">Updating...</small>}</div>
        <span>{data?.totalCount || 0} results</span></div>
      {transactions.length ? <div className="table-scroll"><table className="transactions-table">
        <thead><tr><th scope="col">Merchant</th><th scope="col">Date</th><th scope="col">Category</th>
          <th scope="col">Method</th><th scope="col">City</th><th scope="col" className="amount-cell">Amount</th>
          <th scope="col" aria-label="Actions" /></tr></thead>
        <tbody>{transactions.map((transaction) => <tr key={transaction.id}>
          <td><span className="merchant-cell"><span className="merchant-mark" style={{ '--mark-color': CATEGORIES[transaction.category]?.color }}>
            {transaction.merchant.charAt(0).toUpperCase()}</span><span><strong>{transaction.merchant}</strong>
              <small>{transaction.source === 'demo' ? 'Sample' : 'Expense'}</small></span></span></td>
          <td>{formatDate(transaction.occurredAt)}</td>
          <td><select className="category-select" aria-label={`Category for ${transaction.merchant}`}
            value={transaction.category} onChange={(event) => changeCategory(transaction, event.target.value)}>
            {Object.entries(CATEGORIES).map(([value, info]) => <option key={value} value={value}>{info.label}</option>)}
          </select></td>
          <td>{METHODS[transaction.method] || transaction.method}</td>
          <td>{transaction.city || '—'}</td>
          <td className="amount-cell">-{formatMoney(transaction.amountMinor)}</td>
          <td><button className="icon-button delete-button" type="button" aria-label={`Delete ${transaction.merchant}`}
            title="Delete transaction" onClick={() => removeTransaction(transaction)}><DeleteOutlineRoundedIcon fontSize="small" /></button></td>
        </tr>)}</tbody>
      </table></div> : <EmptyState title="No transactions found" detail="Try a different filter or add a transaction."
        action={<button type="button" className="text-link" onClick={() => { changeFilter(setSearch, ''); setCategory(''); setMethod(''); setMonth(''); }}>Clear filters</button>} />}
      <footer className="pagination"><span>{data?.totalCount ? page * PAGE_SIZE + 1 : 0}–{Math.min((page + 1) * PAGE_SIZE, data?.totalCount || 0)} of {data?.totalCount || 0}</span>
        <div><button className="icon-button" type="button" aria-label="Previous page" disabled={page === 0} onClick={() => setPage(page - 1)}>
          <ChevronLeftRoundedIcon fontSize="small" /></button>
          <button className="icon-button" type="button" aria-label="Next page" disabled={!data?.hasMore} onClick={() => setPage(page + 1)}>
            <ChevronRightRoundedIcon fontSize="small" /></button></div></footer>
    </section>

    <AddTransactionDialog open={isDialogOpen} onClose={() => setSearchParams({}, { replace: true })} />
  </div>;
}