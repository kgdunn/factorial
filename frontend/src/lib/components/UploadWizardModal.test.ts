/**
 * Component tests for `<UploadWizardModal>`.
 *
 * The API client is mocked at the module level so the wizard's view
 * transitions can be exercised without a network call.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';

vi.mock('$lib/api/uploads', () => ({
  uploadDesign: vi.fn(),
  submitUploadAnswers: vi.fn(),
  finalizeUpload: vi.fn(),
}));

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

import {
  finalizeUpload,
  submitUploadAnswers,
  uploadDesign,
} from '$lib/api/uploads';
import UploadWizardModal from './UploadWizardModal.svelte';

const PARSED_PAYLOAD = {
  orientation: 'rows' as const,
  factors: [
    { name: 'Temperature', type: 'continuous' as const, low: 50, high: 80, levels: null, units: null },
  ],
  responses: [{ name: 'Yield', goal: 'maximize' as const, units: null }],
  design_actual: [{ Temperature: 50, Yield: 72 }],
  results_data: [{ Temperature: 50, Yield: 72 }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

function renderOpen() {
  return render(UploadWizardModal, {
    open: true,
    onClose: vi.fn(),
    onComplete: vi.fn(),
  });
}

async function selectFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['x'], 'design.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  await fireEvent.change(input);
}

describe('<UploadWizardModal>', () => {
  it('renders nothing when open=false', () => {
    render(UploadWizardModal, {
      open: false,
      onClose: vi.fn(),
      onComplete: vi.fn(),
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the dropzone in the pick view when first opened', () => {
    renderOpen();
    expect(screen.getByText(/Drop a/i)).toBeTruthy();
  });

  it('transitions pick → confirm when Claude returns a parsed payload', async () => {
    vi.mocked(uploadDesign).mockResolvedValue({
      upload_id: 'abc-123',
      status: 'parsed',
      parsed: PARSED_PAYLOAD,
      questions: null,
      raw_preview: [['Temperature', 'Yield']],
    });

    renderOpen();
    await selectFile();

    await waitFor(() => {
      expect(screen.getByText(/Save as experiment/i)).toBeTruthy();
    });
    expect(uploadDesign).toHaveBeenCalledOnce();
    expect(screen.getByText(/Orientation:/i)).toBeTruthy();
  });

  it('transitions pick → clarify → parsing → confirm with answers', async () => {
    vi.mocked(uploadDesign).mockResolvedValue({
      upload_id: 'abc-123',
      status: 'needs_clarification',
      parsed: null,
      questions: [
        {
          id: 'q1',
          question: 'Is `yield` a factor or an outcome?',
          options: ['Factor', 'Outcome'],
          column_ref: 'yield',
        },
      ],
      raw_preview: [['yield']],
    });
    vi.mocked(submitUploadAnswers).mockResolvedValue({
      upload_id: 'abc-123',
      status: 'parsed',
      parsed: PARSED_PAYLOAD,
      questions: null,
      raw_preview: [['yield']],
    });

    renderOpen();
    await selectFile();

    await waitFor(() => {
      expect(screen.getByText(/Submit answers/i)).toBeTruthy();
    });

    await fireEvent.click(screen.getByText(/Submit answers/i));

    await waitFor(() => {
      expect(screen.getByText(/Save as experiment/i)).toBeTruthy();
    });
    expect(submitUploadAnswers).toHaveBeenCalledWith('abc-123', { q1: 'Factor' });
  });

  it('finalizes and calls onComplete with the new experiment id', async () => {
    const onComplete = vi.fn();
    vi.mocked(uploadDesign).mockResolvedValue({
      upload_id: 'abc-123',
      status: 'parsed',
      parsed: PARSED_PAYLOAD,
      questions: null,
      raw_preview: [['Temperature']],
    });
    vi.mocked(finalizeUpload).mockResolvedValue({
      id: 'exp-999',
      name: 'design',
      status: 'active',
      design_type: 'uploaded',
      n_runs: 1,
      n_factors: 1,
      conversation_id: null,
      created_at: '',
      updated_at: '',
      factors: null,
      design_data: null,
      results_data: null,
      evaluation_data: null,
    });

    render(UploadWizardModal, {
      open: true,
      onClose: vi.fn(),
      onComplete,
    });
    await selectFile();
    await waitFor(() => screen.getByText(/Save as experiment/i));
    await fireEvent.click(screen.getByText(/Save as experiment/i));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith('exp-999');
    });
  });

  it('shows the error view with a Try-again button on failure', async () => {
    vi.mocked(uploadDesign).mockRejectedValue(new Error('Boom'));
    renderOpen();
    await selectFile();
    await waitFor(() => {
      expect(screen.getByText(/Try again/i)).toBeTruthy();
      expect(screen.getByText('Boom')).toBeTruthy();
    });
  });
});
