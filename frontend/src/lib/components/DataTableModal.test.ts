/**
 * Component tests for `<DataTableModal>`.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import DataTableModal from './DataTableModal.svelte';

const SAMPLE_PROPS = {
  rows: [{ Temperature: 50, Yield: 72.3 }],
  factorColumns: ['Temperature'],
  responseColumns: ['Yield'],
};

describe('<DataTableModal>', () => {
  it('renders nothing when open=false', () => {
    render(DataTableModal, {
      open: false,
      onClose: () => undefined,
      ...SAMPLE_PROPS,
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders the table inside a dialog when open=true', () => {
    render(DataTableModal, {
      open: true,
      onClose: () => undefined,
      title: 'My experiment',
      ...SAMPLE_PROPS,
    });
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText('My experiment')).toBeTruthy();
    expect(screen.getByText('Temperature')).toBeTruthy();
  });

  it('calls onClose on Escape', async () => {
    const onClose = vi.fn();
    render(DataTableModal, { open: true, onClose, ...SAMPLE_PROPS });
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on backdrop click', async () => {
    const onClose = vi.fn();
    render(DataTableModal, { open: true, onClose, ...SAMPLE_PROPS });
    const backdrop = screen.getByLabelText('Close dialog');
    await fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });

  it('does not bind Escape when open=false', async () => {
    const onClose = vi.fn();
    render(DataTableModal, { open: false, onClose, ...SAMPLE_PROPS });
    await fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });
});
