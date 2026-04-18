<script lang="ts">
  import {
    getAdminUsers,
    patchAdminUser,
    postResetUserPassword,
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

  async function toggleAdmin(u: AdminUser) {
    error = null;
    info = null;
    try {
      const updated = await patchAdminUser(u.id, { is_admin: !u.is_admin });
      users = users.map((x) => (x.id === u.id ? updated : x));
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
      users = users.map((x) => (x.id === u.id ? updated : x));
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
      users = users.map((x) => (x.id === u.id ? updated : x));
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

  let totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }
</script>

<div class="p-6">
  <div class="mx-auto max-w-5xl space-y-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Users</h2>
        <p class="mt-1 text-sm text-gray-500">Toggle admin, change role, deactivate, or issue a password reset.</p>
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
              <th class="px-3 py-2">Name</th>
              <th class="px-3 py-2">Role</th>
              <th class="px-3 py-2">Admin</th>
              <th class="px-3 py-2">Active</th>
              <th class="px-3 py-2">Joined</th>
              <th class="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            {#each users as u}
              <tr class={u.is_active ? '' : 'bg-gray-50 text-gray-400'}>
                <td class="px-3 py-2 font-medium text-gray-900">{u.email}</td>
                <td class="px-3 py-2">{u.display_name || ''}</td>
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
                <td class="px-3 py-2 text-xs text-gray-500">{formatDate(u.created_at)}</td>
                <td class="px-3 py-2 text-right">
                  <button
                    onclick={() => issueReset(u)}
                    class="text-xs text-primary hover:underline"
                  >
                    Reset password
                  </button>
                </td>
              </tr>
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
