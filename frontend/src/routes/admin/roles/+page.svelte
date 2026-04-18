<script lang="ts">
  import { createRole, deleteRole, getRoles, updateRole, type Role } from '$lib/api/roles';

  let roles = $state<Role[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let info = $state<string | null>(null);

  let newName = $state('');
  let newDesc = $state('');

  // Per-row edit state
  let editingId = $state<string | null>(null);
  let editDesc = $state('');

  async function load() {
    loading = true;
    error = null;
    try {
      roles = await getRoles();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load roles';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    load();
  });

  async function handleCreate(e: Event) {
    e.preventDefault();
    error = null;
    info = null;
    try {
      await createRole(newName, newDesc || null);
      newName = '';
      newDesc = '';
      info = 'Role created.';
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Create failed';
    }
  }

  function startEdit(r: Role) {
    editingId = r.id;
    editDesc = r.description ?? '';
  }

  async function saveEdit(r: Role) {
    error = null;
    info = null;
    try {
      await updateRole(r.id, editDesc || null);
      editingId = null;
      info = 'Role updated.';
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Update failed';
    }
  }

  async function handleDelete(r: Role) {
    if (!confirm(`Delete role "${r.name}"?`)) return;
    error = null;
    info = null;
    try {
      await deleteRole(r.id);
      info = 'Role deleted.';
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Delete failed';
    }
  }
</script>

<div class="p-6">
  <div class="mx-auto max-w-3xl space-y-6">
    <div>
      <h2 class="text-lg font-semibold text-gray-900">Roles</h2>
      <p class="mt-1 text-sm text-gray-500">
        Roles identify a user's profession. The slug is lowercase with underscores
        (e.g. <code>chemical_engineer</code>) and is safe to include in the agent system prompt.
        Built-in roles can't be deleted.
      </p>
    </div>

    {#if error}<div class="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>{/if}
    {#if info}<div class="rounded-md bg-green-50 p-3 text-sm text-green-700">{info}</div>{/if}

    <form onsubmit={handleCreate} class="flex flex-wrap items-end gap-3 rounded-md border border-gray-200 bg-white p-3">
      <div class="min-w-[10rem] flex-1">
        <label for="new-role-name" class="block text-xs font-medium text-gray-700">Name (slug)</label>
        <input
          id="new-role-name"
          type="text"
          bind:value={newName}
          placeholder="polymer_scientist"
          maxlength={50}
          required
          class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>
      <div class="min-w-[14rem] flex-[2]">
        <label for="new-role-desc" class="block text-xs font-medium text-gray-700">Description</label>
        <input
          id="new-role-desc"
          type="text"
          bind:value={newDesc}
          maxlength={500}
          class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        />
      </div>
      <button
        type="submit"
        class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90"
      >
        Add role
      </button>
    </form>

    {#if loading}
      <p class="text-sm text-gray-500">Loading...</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 bg-white text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-500">
            <tr>
              <th class="px-3 py-2">Name</th>
              <th class="px-3 py-2">Description</th>
              <th class="px-3 py-2">Built-in</th>
              <th class="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            {#each roles as role}
              <tr>
                <td class="px-3 py-2 font-mono text-xs">{role.name}</td>
                <td class="px-3 py-2">
                  {#if editingId === role.id}
                    <input
                      type="text"
                      bind:value={editDesc}
                      maxlength={500}
                      class="block w-full rounded-md border border-gray-300 px-2 py-1 text-xs"
                    />
                  {:else}
                    <span class="text-gray-700">{role.description || '—'}</span>
                  {/if}
                </td>
                <td class="px-3 py-2 text-xs">{role.is_builtin ? 'yes' : 'no'}</td>
                <td class="px-3 py-2 text-right space-x-2">
                  {#if editingId === role.id}
                    <button
                      onclick={() => saveEdit(role)}
                      class="text-xs text-primary hover:underline"
                    >Save</button>
                    <button
                      onclick={() => (editingId = null)}
                      class="text-xs text-gray-500 hover:underline"
                    >Cancel</button>
                  {:else}
                    <button
                      onclick={() => startEdit(role)}
                      class="text-xs text-primary hover:underline"
                    >Edit</button>
                    {#if !role.is_builtin}
                      <button
                        onclick={() => handleDelete(role)}
                        class="text-xs text-red-600 hover:underline"
                      >Delete</button>
                    {/if}
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</div>
