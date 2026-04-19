<script lang="ts">
  import { getRoles, type Role } from '$lib/api/roles';
  import {
    getAdminSignups,
    postApproveSignup,
    postRejectSignup,
    type SignupApproveBody,
  } from '$lib/api/signup';
  import type { SignupDetail } from '$lib/api/signup';

  let signups = $state<SignupDetail[]>([]);
  let roles = $state<Role[]>([]);
  let total = $state(0);
  let currentPage = $state(1);
  let statusFilter = $state<string | undefined>(undefined);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let actionMessage = $state<string | null>(null);

  // Per-card approval state — keyed by signup id.
  // Mode is 'existing' (pick an existing role) or 'new' (create one).
  let approveMode = $state<Record<string, 'existing' | 'new'>>({});
  let approveRoleId = $state<Record<string, string>>({});
  let approveNewName = $state<Record<string, string>>({});
  let approveNewDesc = $state<Record<string, string>>({});

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
      // Prefill approval controls from the applicant's requested_role.
      for (const s of signups) {
        if (s.id in approveMode) continue;
        if (s.role) {
          approveMode[s.id] = 'existing';
          approveRoleId[s.id] = s.role.id;
          continue;
        }
        if (s.requested_role?.toLowerCase().startsWith('other:')) {
          approveMode[s.id] = 'new';
          approveNewName[s.id] = '';
          approveNewDesc[s.id] = s.requested_role.slice('other:'.length).trim();
        } else if (s.requested_role) {
          const match = roles.find((r) => r.name === s.requested_role);
          approveMode[s.id] = 'existing';
          if (match) approveRoleId[s.id] = match.id;
        } else {
          approveMode[s.id] = 'existing';
        }
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load signups';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    getRoles().then((rs) => (roles = rs)).catch(() => { roles = []; });
  });

  $effect(() => {
    void statusFilter;
    void currentPage;
    loadSignups();
  });

  function buildApproveBody(id: string): SignupApproveBody | null {
    const mode = approveMode[id] ?? 'existing';
    if (mode === 'existing') {
      const rid = approveRoleId[id];
      return rid ? { role_id: rid } : null;
    }
    const name = (approveNewName[id] || '').trim();
    if (!name) return null;
    return { new_role: { name, description: approveNewDesc[id]?.trim() || null } };
  }

  function canApprove(id: string): boolean {
    return buildApproveBody(id) !== null;
  }

  async function handleApprove(id: string) {
    actionMessage = null;
    error = null;
    const body = buildApproveBody(id);
    if (!body) {
      error = 'Pick an existing role or give a name for a new one before approving.';
      return;
    }
    try {
      await postApproveSignup(id, body);
      actionMessage = 'Approved — invite email sent.';
      await loadSignups();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Approve failed';
    }
  }

  async function handleReject(id: string) {
    actionMessage = null;
    error = null;
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

<div class="p-6">
  <div class="mx-auto max-w-5xl space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-gray-900">Signup requests</h2>
      <p class="mt-1 text-sm text-gray-500">Review requests, assign a role, and send the invite.</p>
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

    {#if error}
      <div class="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
    {/if}
    {#if actionMessage}
      <div class="rounded-md bg-green-50 p-3 text-sm text-green-700">{actionMessage}</div>
    {/if}

    {#if loading}
      <p class="text-gray-500 text-sm">Loading...</p>
    {:else if signups.length === 0}
      <p class="text-gray-500 text-sm">No signup requests found.</p>
    {:else}
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
                  {#if signup.role}
                    <span class="inline-flex rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {signup.role.name}
                    </span>
                  {/if}
                </div>
                <p class="mt-2 text-sm text-gray-600 whitespace-pre-wrap">{signup.use_case}</p>
                {#if signup.requested_role}
                  <p class="mt-2 text-xs text-gray-500">
                    Applicant picked: <code class="text-gray-700">{signup.requested_role}</code>
                  </p>
                {/if}
                {#if signup.admin_note}
                  <p class="mt-2 text-xs text-gray-400">Note: {signup.admin_note}</p>
                {/if}
                <p class="mt-2 text-xs {signup.accepted_disclaimers ? 'text-green-700' : 'text-red-600'}">
                  {#if signup.accepted_disclaimers}
                    ✓ Disclaimer accepted{signup.disclaimers_accepted_at
                      ? ` on ${formatDate(signup.disclaimers_accepted_at)}`
                      : ''}
                  {:else}
                    ✗ Disclaimer not accepted
                  {/if}
                </p>
                <p class="mt-2 text-xs text-gray-400">{formatDate(signup.created_at)}</p>
              </div>

              {#if signup.status === 'pending'}
                <div class="flex shrink-0 gap-2">
                  <button
                    onclick={() => handleApprove(signup.id)}
                    disabled={!canApprove(signup.id)}
                    title={canApprove(signup.id) ? '' : 'Pick a role below before approving'}
                    class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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

            {#if signup.status === 'pending'}
              <div class="mt-3 border-t border-gray-100 pt-3 space-y-2">
                <p class="text-xs font-medium text-gray-700">Role (required)</p>
                <div class="flex items-center gap-3 text-xs">
                  <label class="inline-flex items-center gap-1">
                    <input type="radio" name="mode-{signup.id}" value="existing" bind:group={approveMode[signup.id]} />
                    <span>Assign existing role</span>
                  </label>
                  <label class="inline-flex items-center gap-1">
                    <input type="radio" name="mode-{signup.id}" value="new" bind:group={approveMode[signup.id]} />
                    <span>Create new role</span>
                  </label>
                </div>

                {#if approveMode[signup.id] === 'existing'}
                  <select
                    bind:value={approveRoleId[signup.id]}
                    class="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                  >
                    <option value="">— Pick a role —</option>
                    {#each roles as role}
                      <option value={role.id}>{role.name}{role.is_builtin ? '' : ' (custom)'}</option>
                    {/each}
                  </select>
                {/if}

                {#if approveMode[signup.id] === 'new'}
                  <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <input
                      type="text"
                      bind:value={approveNewName[signup.id]}
                      placeholder="new_role_slug (e.g. polymer_scientist)"
                      maxlength={50}
                      class="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                    />
                    <input
                      type="text"
                      bind:value={approveNewDesc[signup.id]}
                      placeholder="Description (optional)"
                      maxlength={500}
                      class="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                    />
                  </div>
                {/if}
              </div>
            {/if}

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
