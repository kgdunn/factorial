<script lang="ts">
  import { authState } from '$lib/state/auth.svelte';
  import { reauthReject, reauthResolve, reauthState } from '$lib/state/reauth.svelte';

  let password = $state('');
  let submitting = $state(false);
  let errorMessage = $state<string | null>(null);

  $effect(() => {
    if (!reauthState.isOpen) {
      password = '';
      submitting = false;
      errorMessage = null;
    }
  });

  const email = $derived(authState.user?.email ?? '');

  async function handleSubmit(e: Event) {
    e.preventDefault();
    if (!email || !password || submitting) return;
    submitting = true;
    errorMessage = null;
    try {
      await authState.login(email, password);
      reauthResolve();
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : 'Sign-in failed';
    } finally {
      submitting = false;
    }
  }

  function handleCancel() {
    reauthReject();
  }
</script>

{#if reauthState.isOpen}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="reauth-title"
  >
    <form
      class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
      onsubmit={handleSubmit}
    >
      <h2 id="reauth-title" class="mb-1 text-lg font-semibold text-gray-800">
        Sign in again
      </h2>
      <p class="mb-4 text-sm text-gray-500">
        Your session expired. Re-enter your password to keep going where you left
        off — nothing on this page will be lost.
      </p>

      <label class="mb-3 block">
        <span class="mb-1 block text-xs font-medium text-gray-500">Email</span>
        <input
          type="email"
          value={email}
          disabled
          class="w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700"
        />
      </label>

      <label class="mb-4 block">
        <span class="mb-1 block text-xs font-medium text-gray-500">Password</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="password"
          bind:value={password}
          autocomplete="current-password"
          autofocus
          required
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
        />
      </label>

      {#if errorMessage}
        <p class="mb-3 text-sm text-red-600">{errorMessage}</p>
      {/if}

      <div class="flex justify-end gap-2">
        <button
          type="button"
          onclick={handleCancel}
          class="rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting || !password}
          class="rounded-md bg-ink px-4 py-2 text-sm font-medium text-paper hover:bg-black/90 disabled:opacity-50"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </div>
    </form>
  </div>
{/if}
