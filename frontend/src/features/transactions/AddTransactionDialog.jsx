import { useState } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import { useAddTransactionMutation } from '../../shared/api/api';
import { CATEGORIES, METHODS } from '../../shared/constants';
import { parseMoney } from '../../shared/format';

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function AddTransactionDialog({ open, onClose }) {
  const [merchant, setMerchant] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('UPI');
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');
  const [occurredAt, setOccurredAt] = useState(localDateTime);
  const [error, setError] = useState('');
  const [addTransaction, { isLoading }] = useAddTransactionMutation();

  async function handleSubmit(event) {
    event.preventDefault();
    const amountMinor = parseMoney(amount);
    if (!amountMinor) {
      setError('Enter an amount with no more than two decimal places.');
      return;
    }
    try {
      await addTransaction({
        merchant: merchant.trim(), amountMinor, method, occurredAt: new Date(occurredAt).toISOString(),
        ...(category ? { category } : {}), ...(city.trim() ? { city: city.trim() } : {}),
      }).unwrap();
      setMerchant('');
      setAmount('');
      setError('');
      onClose();
    } catch (requestError) {
      setError(requestError.message || 'Transaction could not be saved.');
    }
  }

  return <Dialog open={open} onClose={onClose} aria-labelledby="add-transaction-title" fullWidth maxWidth="sm">
    <DialogTitle id="add-transaction-title">Add transaction</DialogTitle>
    <form onSubmit={handleSubmit}>
      <DialogContent className="dialog-fields">
        <label htmlFor="transaction-merchant">Merchant</label>
        <input id="transaction-merchant" required minLength={2} maxLength={100}
          value={merchant} onChange={(event) => setMerchant(event.target.value)} placeholder="e.g. Apollo Pharmacy" />
        <div className="form-pair">
          <div><label htmlFor="transaction-amount">Amount (INR)</label>
            <input id="transaction-amount" required inputMode="decimal" type="text" value={amount}
              onChange={(event) => setAmount(event.target.value)} placeholder="0.00" /></div>
          <div><label htmlFor="transaction-date">Date and time</label>
            <input id="transaction-date" type="datetime-local" required value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)} /></div>
        </div>
        <div className="form-pair">
          <div><label htmlFor="transaction-method">Payment method</label>
            <select id="transaction-method" value={method} onChange={(event) => setMethod(event.target.value)}>
              {Object.entries(METHODS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></div>
          <div><label htmlFor="transaction-category">Category</label>
            <select id="transaction-category" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">Auto categorize</option>
              {Object.entries(CATEGORIES).map(([value, info]) => <option key={value} value={value}>{info.label}</option>)}
            </select></div>
        </div>
        <label htmlFor="transaction-city">City (optional)</label>
        <input id="transaction-city" value={city} maxLength={80} onChange={(event) => setCity(event.target.value)} placeholder="Bengaluru" />
        {error && <p role="alert" className="form-error">{error}</p>}
      </DialogContent>
      <DialogActions className="dialog-actions">
        <button type="button" className="button" onClick={onClose}>Cancel</button>
        <button type="submit" className="button button-primary" disabled={isLoading}>{isLoading ? 'Saving...' : 'Save transaction'}</button>
      </DialogActions>
    </form>
  </Dialog>;
}