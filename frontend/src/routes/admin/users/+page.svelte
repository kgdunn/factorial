<script lang="ts">
  import {
    getAdminUsers,
    patchAdminUser,
    postResetUserPassword,
    postTopUpBalance,
    type AdminUser,
  } from '$lib/api/adminUsers';
  import { getRoles, type Role } from '$lib/api/roles';
  import { authState } from '$lib/state/auth.svelte';

  let users = $state<AdminUser[]>([]);
  let roles = $state<Role[]>([]);
  let total = $state(0);
  let page = $state(1);
  let pageSize = 50;
  let search = $state('');
  let adminsOnly = $state(false);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let info = $state<string | null>(null);
  let resetUrl = $state<{ email: string; url: string } | null>(null);
  let expandedId = $state<string | null>(null);

  // Per-user top-up form state, keyed by user id.
  let topUpUsd = $state<Record<string, string>>({});
  let topUpTokens = $state<Record<string, string>>({});
  let topUpBusy = $state<Record<string, boolean>>({});

  let currentUserId = $derived(authState.user?.id ?? null);

  async function loadUsers() {
    loading = true;
    error = null;
    try {
      const res = await getAdminUsers({ page, pageSize, search: search || undefined, adminsOnly });
      users = res.users;
      total = res.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load users';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    getRoles().then((rs) => (roles = rs)).catch(() => { roles = []; });
  });

  $effect(() => {
    void page;
    void adminsOnly;
    loadUsers();
  });

  let searchDebounce: ReturnType<typeof setTimeout> | undefined;
  function onSearchInput() {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      page = 1;
      loadUsers();
    }, 300);
  }

  function mergeUpdate(id: string, patch: Partial<AdminUser>) {
    users = users.map((x) => (x.id === id ? { ...x, ...patch } : x));
  }

  async function toggleAdmin(u: AdminUser) {
    error = null;
    info = null;
    try {
      const updated = await patchAdminUser(u.id, { is_admin: !u.is_admin });
      mergeUpdate(u.id, updated);
      info = `${u.email} is now ${updated.is_admin ? 'an admin' : 'a regular user'}.`;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Update failed';
    }
  }

  async function toggleActive(u: AdminUser) {
    error = null;
    info = null;
    try {
      const updated = await patchAdminUser(u.id, { is_active: !u.is_active });
      mergeUpdate(u.id, updated);
      info = `${u.email} is now ${updated.is_active ? 'active' : 'deactivated'}.`;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Update failed';
    }
  }

  async function changeRole(u: AdminUser, value: string) {
    error = null;
    info = null;
    try {
      const updated = await patchAdminUser(u.id, value === '' ? { clear_role: true } : { role_id: value });
      mergeUpdate(u.id, updated);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Update failed';
    }
  }

  async function issueReset(u: AdminUser) {
    error = null;
    info = null;
    resetUrl = null;
    try {
      const res = await postResetUserPassword(u.id);
      resetUrl = { email: u.email, url: res.url };
      info = `Reset link issued for ${u.email} (also emailed if SMTP is configured).`;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Reset failed';
    }
  }

  async function submitTopUp(u: AdminUser) {
    error = null;
    info = null;
    const usd = (topUpUsd[u.id] ?? '').trim();
    const tokensStr = (topUpTokens[u.id] ?? '').trim();
    const tokens = tokensStr === '' ? 0 : Number(tokensStr);
    if ((usd === '' || usd === '0') && (!tokens || tokens <= 0)) {
      error = 'Enter a dollar amount or a token count to credit.';
      return;
    }
    topUpBusy[u.id] = true;
    try {
      const res = await postTopUpBalance(u.id, {
        usd: usd === '' ? '0' : usd,
        tokens: Number.isFinite(tokens) ? tokens : 0,
      });
      mergeUpdate(u.id, { balance_usd: res.balance_usd, balance_tokens: res.balance_tokens });
      info = `Topped up ${u.email}. New balance: $${res.balance_usd} / ${res.balance_tokens.toLocaleString()} tokens.`;
      topUpUsd[u.id] = '';
      topUpTokens[u.id] = '';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Top-up failed';
    } finally {
      topUpBusy[u.id] = false;
    }
  }

  function toggleExpand(id: string) {
    expandedId = expandedId === id ? null : id;
  }

  let totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

  function formatDate(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function formatDateTime(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
  }

  function formatRelative(iso: string | null): string {
    if (!iso) return 'never';
    const ms = Date.now() - new Date(iso).getTime();
    const mins = Math.round(ms / 60_000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return `${days}d ago`;
    const months = Math.round(days / 30);
    if (months < 12) return `${months}mo ago`;
    return `${Math.round(months / 12)}y ago`;
  }

  function formatCost(value: string | null): string {
    if (value === null || value === undefined) return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `$${n.toFixed(2)}`;
  }

  function formatTokens(n: number | null): string {
    if (n === null || n === undefined) return '—';
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return String(n);
  }

  function countryFlag(iso: string | null): string {
    if (!iso || iso.length !== 2) return '';
    const codePoints = [...iso.toUpperCase()].map((c) => 0x1f1e6 - 65 + c.charCodeAt(0));
    return String.fromCodePoint(...codePoints);
  }
</script>

<div class="p-6">
  <div class="mx-auto max-w-7xl space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Users</h2>
        <p class="mt-1 text-sm text-gray-500">
          Activity, spend, balances, and lifecycle state. Expand a row for details or to top up balance.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <input
          type="search"
          bind:value={search}
          oninput={onSearchInput}
          placeholder="Search email or name..."
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        />
        <label class="inline-flex items-center gap-1 text-sm text-gray-700">
          <input type="checkbox" bind:checked={adminsOnly} />
          Admins only
        </label>
      </div>
    </div>

    {#if error}
      <div class="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
    {/if}
    {#if info}
      <div class="rounded-md bg-green-50 p-3 text-sm text-green-700">{info}</div>
    {/if}
    {#if resetUrl}
      <div class="rounded-md bg-blue-50 p-3 text-xs text-blue-800 break-all">
        Reset link for <strong>{resetUrl.email}</strong>:
        <a class="underline" href={resetUrl.url}>{resetUrl.url}</a>
      </div>
    {/if}

    {#if loading}
      <p class="text-gray-500 text-sm">Loading...</p>
    {:else if users.length === 0}
      <p class="text-gray-500 text-sm">No users found.</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 bg-white text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
            <tr>
              <th class="px-3 py-2">Email</th>
              <th class="px-3 py-2">Role</th>
              <th class="px-3 py-2">Admin</th>
              <th class="px-3 py-2">Active</th>
              <th class="px-3 py-2">Geo</th>
              <th class="px-3 py-2">Last login</th>
              <th class="px-3 py-2 text-right">Spend</th>
              <th class="px-3 py-2 text-right">Balance</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            {#each users as u (u.id)}
              <tr class={u.is_active ? '' : 'bg-gray-50 text-gray-400'}>
                <td class="px-3 py-2 font-medium text-gray-900">
                  <div class="flex flex-col">
                    <span class="font-mono text-xs">{u.email}</span>
                    {#if u.display_name}
                      <span class="text-xs text-gray-500">{u.display_name}</span>
                    {/if}
                  </div>
                </td>
                <td class="px-3 py-2">
                  <select
                    value={u.role?.id ?? ''}
                    onchange={(e) => changeRole(u, (e.currentTarget as HTMLSelectElement).value)}
                    class="rounded-md border border-gray-300 px-2 py-1 text-xs"
                  >
                    <option value="">— none —</option>
                    {#each roles as role}
                      <option value={role.id}>{role.name}</option>
                    {/each}
                  </select>
                </td>
                <td class="px-3 py-2">
                  <button
                    onclick={() => toggleAdmin(u)}
                    disabled={u.id === currentUserId}
                    title={u.id === currentUserId ? "You can't demote yourself" : ''}
                    class="rounded px-2 py-0.5 text-xs font-medium
                      {u.is_admin ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-600'}
                      {u.id === currentUserId ? 'opacity-50 cursor-not-allowed' : 'hover:bg-indigo-200'}"
                  >
                    {u.is_admin ? 'admin' : 'user'}
                  </button>
                </td>
                <td class="px-3 py-2">
                  <button
                    onclick={() => toggleActive(u)}
                    class="rounded px-2 py-0.5 text-xs font-medium
                      {u.is_active ? 'bg-green-100 text-green-800 hover:bg-green-200' : 'bg-red-100 text-red-800 hover:bg-red-200'}"
                  >
                    {u.is_active ? 'active' : 'disabled'}
                  </button>
                </td>
                <td class="px-3 py-2 text-xs text-gray-600" title={u.timezone ?? ''}>
                  {#if u.country}
                    <span class="mr-1">{countryFlag(u.country)}</span>{u.country}
                  {:else}
                    <span class="text-gray-400">—</span>
                  {/if}
                </td>
                <td class="px-3 py-2 text-xs text-gray-500" title={formatDateTime(u.last_login_at)}>
                  {formatRelative(u.last_login_at)}
                </td>
                <td class="px-3 py-2 text-right text-xs text-gray-700">
                  {formatCost(u.total_markup_cost_usd)}
                </td>
                <td class="px-3 py-2 text-right text-xs text-gray-700">
                  {formatCost(u.balance_usd)}
                </td>
                <td class="px-3 py-2 text-right">
                  <button
                    onclick={() => toggleExpand(u.id)}
                    class="text-xs text-primary hover:underline"
                    aria-expanded={expandedId === u.id}
                  >
                    {expandedId === u.id ? 'Hide' : 'Details'}
                  </button>
                </td>
              </tr>

              {#if expandedId === u.id}
                <tr class="bg-gray-50/60">
                  <td colspan="9" class="px-6 py-4">
                    <div class="grid grid-cols-2 gap-6 md:grid-cols-4">
                      <dl class="space-y-1 text-xs">
                        <dt class="font-medium text-gray-500 uppercase">Joined</dt>
                        <dd class="text-gray-900">{formatDate(u.created_at)}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Signup status</dt>
                        <dd class="text-gray-900">
                          {u.signup_status ?? '—'}
                          {#if u.disclaimers_accepted}
                            <span class="ml-1 rounded bg-green-100 px-1 text-[10px] text-green-800">disclaimers ✓</span>
                          {/if}
                        </dd>
                      </dl>

                      <dl class="space-y-1 text-xs">
                        <dt class="font-medium text-gray-500 uppercase">Last login</dt>
                        <dd class="text-gray-900">{formatDateTime(u.last_login_at)}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Last activity</dt>
                        <dd class="text-gray-900">{formatDateTime(u.last_conversation_at)}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">IP / Timezone</dt>
                        <dd class="font-mono text-[11px] text-gray-700">
                          {u.last_login_ip ?? '—'} · {u.timezone ?? '—'}
                        </dd>
                      </dl>

                      <dl class="space-y-1 text-xs">
                        <dt class="font-medium text-gray-500 uppercase">Spend</dt>
                        <dd class="text-gray-900">
                          {formatCost(u.total_markup_cost_usd)} billed ·
                          {formatCost(u.total_cost_usd)} raw
                        </dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Tokens used</dt>
                        <dd class="text-gray-900">{formatTokens(u.total_tokens)}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Conversations</dt>
                        <dd class="text-gray-900">{u.conversation_count}</dd>
                      </dl>

                      <dl class="space-y-1 text-xs">
                        <dt class="font-medium text-gray-500 uppercase">Feedback sent</dt>
                        <dd class="text-gray-900">{u.feedback_count}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Open experiments</dt>
                        <dd class="text-gray-900">{u.open_experiments}</dd>
                        <dt class="mt-2 font-medium text-gray-500 uppercase">Avg runs / experiment</dt>
                        <dd class="text-gray-900">
                          {u.avg_runs_per_experiment === null
                            ? '—'
                            : u.avg_runs_per_experiment.toFixed(1)}
                        </dd>
                      </dl>
                    </div>

                    <div class="mt-5 flex flex-wrap items-end gap-3 border-t border-gray-200 pt-4">
                      <div>
                        <div class="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                          Top up balance
                        </div>
                        <div class="text-xs text-gray-500">
                          Current: {formatCost(u.balance_usd)} · {formatTokens(u.balance_tokens)} tokens
                        </div>
                      </div>
                      <label class="flex flex-col text-xs">
                        <span class="text-gray-500">Add $USD</span>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          placeholder="0.00"
                          bind:value={topUpUsd[u.id]}
                          class="w-28 rounded-md border border-gray-300 px-2 py-1 text-xs"
                        />
                      </label>
                      <label class="flex flex-col text-xs">
                        <span class="text-gray-500">Add tokens</span>
                        <input
                          type="number"
                          min="0"
                          step="1000"
                          placeholder="0"
                          bind:value={topUpTokens[u.id]}
                          class="w-32 rounded-md border border-gray-300 px-2 py-1 text-xs"
                        />
                      </label>
                      <button
                        onclick={() => submitTopUp(u)}
                        disabled={topUpBusy[u.id]}
                        class="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary/90 disabled:opacity-50"
                      >
                        {topUpBusy[u.id] ? 'Applying...' : 'Apply top-up'}
                      </button>
                      <button
                        onclick={() => issueReset(u)}
                        class="ml-auto text-xs text-primary hover:underline"
                      >
                        Reset password
                      </button>
                    </div>
                  </td>
                </tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>

      {#if totalPages > 1}
        <div class="flex items-center justify-between pt-4">
          <p class="text-sm text-gray-500">{total} total users</p>
          <div class="flex gap-2">
            <button
              onclick={() => (page = Math.max(1, page - 1))}
              disabled={page <= 1}
              class="rounded-md border border-gray-300 px-3 py-1 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <span class="px-2 py-1 text-sm text-gray-600">Page {page} of {totalPages}</span>
            <button
              onclick={() => (page = Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
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
