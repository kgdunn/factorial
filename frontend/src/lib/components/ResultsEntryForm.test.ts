/**
 * Component tests for `<ResultsEntryForm>`.
 *
 * Covers the optional per-data-point notes field and the include /
 * exclude dropdown that rides alongside the response value.
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import ResultsEntryForm from './ResultsEntryForm.svelte';

const DESIGN_DATA = {
  factor_names: ['Temperature', 'Pressure'],
  design_actual: [
    { Temperature: 150, Pressure: 1 },
    { Temperature: 200, Pressure: 5 },
  ],
};

describe('<ResultsEntryForm>', () => {
  it('emits a row with notes when the user types into the notes field', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(ResultsEntryForm, {
      designData: DESIGN_DATA,
      resultsData: null,
      onSave,
    });

    const responseInput = screen.getByLabelText('Response for run 1') as HTMLInputElement;
    await fireEvent.input(responseInput, { target: { value: '85.2' } });

    const notesInput = screen.getByLabelText('Notes for run 1') as HTMLInputElement;
    await fireEvent.input(notesInput, { target: { value: 'thermocouple drifted' } });

    await fireEvent.click(screen.getByText('Save Results'));

    expect(onSave).toHaveBeenCalledTimes(1);
    const rows = onSave.mock.calls[0][0] as Record<string, unknown>[];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      run_index: 0,
      Response: 85.2,
      notes: 'thermocouple drifted',
    });
    // included is omitted (default true) to keep the JSON small.
    expect(rows[0].included).toBeUndefined();
  });

  it('emits included:false when a row is toggled to Exclude', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(ResultsEntryForm, {
      designData: DESIGN_DATA,
      resultsData: null,
      onSave,
    });

    const responseInput = screen.getByLabelText('Response for run 2') as HTMLInputElement;
    await fireEvent.input(responseInput, { target: { value: '91' } });

    const includeSelect = screen.getByLabelText('Include or exclude run 2') as HTMLSelectElement;
    await fireEvent.change(includeSelect, { target: { value: 'exclude' } });

    await fireEvent.click(screen.getByText('Save Results'));

    expect(onSave).toHaveBeenCalledTimes(1);
    const rows = onSave.mock.calls[0][0] as Record<string, unknown>[];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      run_index: 1,
      Response: 91,
      included: false,
    });
  });

  it('emits a row that has only a note (no response value entered)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(ResultsEntryForm, {
      designData: DESIGN_DATA,
      resultsData: null,
      onSave,
    });

    const notesInput = screen.getByLabelText('Notes for run 1') as HTMLInputElement;
    await fireEvent.input(notesInput, { target: { value: 'sensor failure, retake' } });

    await fireEvent.click(screen.getByText('Save Results'));

    expect(onSave).toHaveBeenCalledTimes(1);
    const rows = onSave.mock.calls[0][0] as Record<string, unknown>[];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual({
      run_index: 0,
      notes: 'sensor failure, retake',
    });
  });

  it('does not enable Save when no row has any change', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(ResultsEntryForm, {
      designData: DESIGN_DATA,
      resultsData: null,
      onSave,
    });
    const saveBtn = screen.getByText('Save Results') as HTMLButtonElement;
    expect(saveBtn.disabled).toBe(true);
  });

  it('rehydrates notes and included from existing results without hijacking the response name', () => {
    render(ResultsEntryForm, {
      designData: DESIGN_DATA,
      resultsData: [
        { run_index: 0, Yield: 85.2, notes: 'drifted', included: false },
      ],
      onSave: vi.fn(),
    });

    // Response input got the value.
    const responseInput = screen.getByLabelText('Response for run 1') as HTMLInputElement;
    expect(responseInput.value).toBe('85.2');

    // Notes input got the note (NOT the response).
    const notesInput = screen.getByLabelText('Notes for run 1') as HTMLInputElement;
    expect(notesInput.value).toBe('drifted');

    // Include select reflects the persisted exclude flag.
    const includeSelect = screen.getByLabelText('Include or exclude run 1') as HTMLSelectElement;
    expect(includeSelect.value).toBe('exclude');

    // Crucial: the response column-name detector must skip 'notes'/'included'
    // and pick 'Yield'. If it picked 'notes', the response-name input would
    // read 'notes' and re-saving would write the note string into a 'notes'
    // numeric column. Verify by checking the response-name input value.
    const nameInput = screen.getByPlaceholderText('Response name') as HTMLInputElement;
    expect(nameInput.value).toBe('Yield');
  });
});
