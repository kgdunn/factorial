<script lang="ts">
  import {
    getAdminSignups,
    postApproveSignup,
    postRejectSignup,
  } from '$lib/api/signup';
  import type { SignupDetail } from '$lib/api/signup';

  let signups = $state<SignupDetail[]>([]);
  let total = $state(0);
  let currentPage = $state(1);
  let statusFilter = $state<string | undefined>(undefined);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let actionMessage = $state<string | null>(null);

  // Rejection note state
  let rejectingId = $state<string | null>(null);
  let rejectNote = $state('');

  const pageSize = 50;
  let totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

  async function loadSignups() {
    loading = true;
    error = null;
    try {
      const res = await getAdminSignups(statusFilter, currentPage, pageSize);
      signups = res.signups;
      total = res.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load signups';
    } finally {
      loading = false;
    }
  }

  // Reload when filter or page changes
  $effect(() => {
    void statusFilter;
    void currentPage;
    loadSignups();
  });

  async function handleApprove(id: string) {
    actionMessage = null;
    try {
      await postApproveSignup(id);
      actionMessage = 'Approved — invite email sent.';
      await loadSignups();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Approve failed';
    }
  }

  async function handleReject(id: string) {
    actionMessage = null;
    try {
      await postRejectSignup(id, rejectNote || undefined);
      rejectingId = null;
      rejectNote = '';
      actionMessage = 'Signup rejected.';
      await loadSignups();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Reject failed';
    }
  }

  function setFilter(f: string | undefined) {
    statusFilter = f;
    currentPage = 1;
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    registered: 'bg-blue-100 text-blue-800',
  };
</script>

<div class="h-full overflow-y-auto p-6">
  <div class="mx-auto max-w-5xl space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-gray-900">Signup requests</h1>
      <p class="mt-1 text-sm text-gray-500">Review and manage access requests.</p>
    </div>

    <!-- Status filter tabs -->
    <div class="flex gap-2">
      {#each [
        { label: 'All', value: undefined },
        { label: 'Pending', value: 'pending' },
        { label: 'Approved', value: 'approved' },
        { label: 'Rejected', value: 'rejected' },
        { label: 'Registered', value: 'registered' },
      ] as tab}
        <button
          onclick={() => setFilter(tab.value)}
          class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors
                 {statusFilter === tab.value
                   ? 'bg-primary text-white'
                   : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}"
        >
          {tab.label}
        </button>
      {/each}
    </div>

    <!-- Messages -->
    {#if error}
      <div class="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
    {/if}
    {#if actionMessage}
      <div class="rounded-md bg-green-50 p-3 text-sm text-green-700">{actionMessage}</div>
    {/if}

    <!-- Loading -->
    {#if loading}
      <p class="text-gray-500 text-sm">Loading...</p>
    {:else if signups.length === 0}
      <p class="text-gray-500 text-sm">No signup requests found.</p>
    {:else}
      <!-- Signup cards -->
      <div class="space-y-4">
        {#each signups as signup}
          <div class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-3">
                  <span class="font-medium text-gray-900">{signup.email}</span>
                  <span class="inline-flex rounded-full px-2 py-0.5 text-xs font-medium {statusColors[signup.status] || 'bg-gray-100 text-gray-600'}">
                    {signup.status}
                  </span>
                </div>
                <p class="mt-2 text-sm text-gray-600 whitespace-pre-wrap">{signup.use_case}</p>
                {#if signup.admin_note}
                  <p class="mt-2 text-xs text-gray-400">Note: {signup.admin_note}</p>
                {/if}
                <p class="mt-2 text-xs text-gray-400">{formatDate(signup.created_at)}</p>
              </div>

              {#if signup.status === 'pending'}
                <div class="flex shrink-0 gap-2">
                  <button
                    onclick={() => handleApprove(signup.id)}
                    class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 transition-colors"
                  >
                    Approve
                  </button>
                  <button
                    onclick={() => { rejectingId = rejectingId === signup.id ? null : signup.id; rejectNote = ''; }}
                    class="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              {/if}
            </div>

            {#if rejectingId === signup.id}
              <div class="mt-3 flex items-end gap-2 border-t border-gray-100 pt-3">
                <input
                  type="text"
                  bind:value={rejectNote}
                  placeholder="Optional note (reason for rejection)"
                  class="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  onclick={() => handleReject(signup.id)}
                  class="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
                >
                  Confirm reject
                </button>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <!-- Pagination -->
      {#if totalPages > 1}
        <div class="flex items-center justify-between pt-4">
          <p class="text-sm text-gray-500">{total} total requests</p>
          <div class="flex gap-2">
            <button
              onclick={() => currentPage = Math.max(1, currentPage - 1)}
              disabled={currentPage <= 1}
              class="rounded-md border border-gray-300 px-3 py-1 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span class="px-2 py-1 text-sm text-gray-600">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onclick={() => currentPage = Math.min(totalPages, currentPage + 1)}
              disabled={currentPage >= totalPages}
              class="rounded-md border border-gray-300 px-3 py-1 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>
