/**
 * Experiments state management using Svelte 5 runes (class-based pattern).
 *
 * Usage in components:
 *   import { experimentsState } from '$lib/state/experiments.svelte';
 *   experimentsState.experiments   // reactive
 *   experimentsState.loadExperiments()
 */

import {
  fetchExperiments,
  fetchExperiment,
  updateExperiment,
  deleteExperiment,
  submitResults,
  evaluateExperiment,
  type EvaluateRequestPayload,
} from '$lib/api/experiments';
import type {
  ExperimentCreatedEvent,
  ExperimentDetail,
  ExperimentStatus,
  ExperimentSummary,
} from '$lib/types';

class ExperimentsState {
  experiments = $state<ExperimentSummary[]>([]);
  currentExperiment = $state<ExperimentDetail | null>(null);
  total = $state(0);
  page = $state(1);
  pageSize = $state(20);
  statusFilter = $state<ExperimentStatus | null>(null);
  isLoading = $state(false);
  error = $state<string | null>(null);

  /** Notification from chat SSE when an experiment is auto-created. */
  lastCreated = $state<ExperimentCreatedEvent | null>(null);

  /** Load the experiments list with current filter/pagination. */
  async loadExperiments(): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      const resp = await fetchExperiments({
        status: this.statusFilter ?? undefined,
        page: this.page,
        page_size: this.pageSize,
      });
      this.experiments = resp.experiments;
      this.total = resp.total;
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to load experiments';
    } finally {
      this.isLoading = false;
    }
  }

  /** Load a single experiment by ID. */
  async loadExperiment(id: string): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      this.currentExperiment = await fetchExperiment(id);
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to load experiment';
      this.currentExperiment = null;
    } finally {
      this.isLoading = false;
    }
  }

  /** Update experiment name and/or status. */
  async update(id: string, data: { name?: string; status?: string }): Promise<void> {
    this.error = null;
    try {
      this.currentExperiment = await updateExperiment(id, data);
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to update experiment';
    }
  }

  /** Delete an experiment. */
  async remove(id: string): Promise<void> {
    this.error = null;
    try {
      await deleteExperiment(id);
      this.experiments = this.experiments.filter((e) => e.id !== id);
      this.total = Math.max(0, this.total - 1);
      if (this.currentExperiment?.id === id) {
        this.currentExperiment = null;
      }
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to delete experiment';
    }
  }

  /** Re-run evaluate_design for an experiment with a tweaked sigma / alpha. */
  async reEvaluate(id: string, payload: EvaluateRequestPayload = {}): Promise<void> {
    this.error = null;
    try {
      const updated = await evaluateExperiment(id, payload);
      if (this.currentExperiment && this.currentExperiment.id === id) {
        this.currentExperiment = updated;
      }
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to re-evaluate experiment';
    }
  }

  /** Add or update results for an experiment. */
  async addResults(id: string, results: Record<string, unknown>[]): Promise<void> {
    this.error = null;
    try {
      const resp = await submitResults(id, results);
      if (this.currentExperiment && this.currentExperiment.id === id) {
        this.currentExperiment.results_data = resp.results_data;
      }
    } catch (err: unknown) {
      this.error = err instanceof Error ? err.message : 'Failed to save results';
    }
  }

  /** Called from chat SSE when an experiment is auto-created. */
  notifyCreated(data: ExperimentCreatedEvent): void {
    this.lastCreated = data;
  }

  /** Dismiss the experiment-created notification. */
  dismissNotification(): void {
    this.lastCreated = null;
  }

  /** Set the status filter and reload. */
  async setFilter(status: ExperimentStatus | null): Promise<void> {
    this.statusFilter = status;
    this.page = 1;
    await this.loadExperiments();
  }

  /** Go to a specific page and reload. */
  async goToPage(page: number): Promise<void> {
    this.page = page;
    await this.loadExperiments();
  }
}

export const experimentsState = new ExperimentsState();
