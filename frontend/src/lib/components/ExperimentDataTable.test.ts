/**
 * Component tests for `<ExperimentDataTable>`.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import ExperimentDataTable from './ExperimentDataTable.svelte';

describe('<ExperimentDataTable>', () => {
  it('renders factor and response columns with the right tinting', () => {
    render(ExperimentDataTable, {
      rows: [{ Temperature: 50, Yield: 72.3 }],
      factorColumns: ['Temperature'],
      responseColumns: ['Yield'],
    });

    const yieldHeader = screen.getByText('Yield');
    expect(yieldHeader).toBeTruthy();
    expect(screen.getByText('out')).toBeTruthy();
    expect(screen.getByText('Temperature')).toBeTruthy();
  });

  it('shows the empty-state when rows is empty', () => {
    render(ExperimentDataTable, {
      rows: [],
      factorColumns: ['Temperature'],
    });
    expect(screen.getByText(/no data/i)).toBeTruthy();
  });

  it('renders em-dash for null cells', () => {
    render(ExperimentDataTable, {
      rows: [{ Temperature: null, Yield: undefined }],
      factorColumns: ['Temperature'],
      responseColumns: ['Yield'],
    });
    // Two em-dashes — one for each null/undefined cell.
    expect(screen.getAllByText('—').length).toBe(2);
  });

  it('calls onCellEdit when a cell is edited', async () => {
    const onCellEdit = vi.fn();
    render(ExperimentDataTable, {
      rows: [{ Temperature: 50 }],
      factorColumns: ['Temperature'],
      editable: true,
      onCellEdit,
    });

    const cell = screen.getByText('50');
    await fireEvent.click(cell);
    const input = (await screen.findByDisplayValue('50')) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: '75' } });
    await fireEvent.blur(input);

    expect(onCellEdit).toHaveBeenCalledWith(0, 'Temperature', '75');
  });

  it('does not enter edit mode when editable=false', async () => {
    render(ExperimentDataTable, {
      rows: [{ Temperature: 50 }],
      factorColumns: ['Temperature'],
      editable: false,
    });
    const cell = screen.getByText('50');
    await fireEvent.click(cell);
    expect(screen.queryByDisplayValue('50')).toBeNull();
  });
});
