import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import ErrorBoundary from './ErrorBoundary';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('unexpected view errors', () => {
  it('shows a recovery action instead of an empty screen', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    function BrokenView() { throw new Error('Unexpected view error'); }

    render(<ErrorBoundary><BrokenView /></ErrorBoundary>);

    expect(screen.getByRole('alert').textContent).toContain('This view could not be displayed');
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy();
  });
});