import { Component } from 'react';
import ReplayRoundedIcon from '@mui/icons-material/ReplayRounded';

export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <div className="page-state" role="alert">
        <h2>This view could not be displayed</h2>
        <p>Reload the page to try again.</p>
        <button className="button button-primary" type="button" onClick={() => window.location.reload()}>
          <ReplayRoundedIcon fontSize="small" /> Reload
        </button>
      </div>;
    }
    return this.props.children;
  }
}