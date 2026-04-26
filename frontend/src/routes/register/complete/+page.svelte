<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { getInviteValidation } from '$lib/api/signup';
  import { authState } from '$lib/state/auth.svelte';

  let inviteEmail = $state('');
  let tokenValid = $state<boolean | null>(null);
  let password = $state('');
  let confirmPassword = $state('');
  let displayName = $state('');
  let error = $state<string | null>(null);
  let loading = $state(false);

  // Validate the invite token on mount
  $effect(() => {
    const token = $page.url.searchParams.get('token');
    if (!token) {
      tokenValid = false;
      return;
    }
    getInviteValidation(token).then((res) => {
      tokenValid = res.valid;
      if (res.valid) inviteEmail = res.email;
    }).catch(() => {
      tokenValid = false;
    });
  });

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = null;

    if (password !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }

    const token = $page.url.searchParams.get('token');
    if (!token) {
      error = 'Missing invite token';
      return;
    }

    loading = true;
    try {
      await authState.registerWithInvite(token, password, displayName || undefined);
      goto('/chat');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Registration failed';
    } finally {
      loading = false;
    }
  }
</script>

<div class="h-full overflow-y-auto">
  <div class="flex min-h-full items-center justify-center px-4 py-12">
    <div class="w-full max-w-sm space-y-6">
    {#if tokenValid === null}
      <div class="text-center">
        <p class="text-gray-500">Validating your invite...</p>
      </div>
    {:else if !tokenValid}
      <div class="text-center space-y-4">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
          <svg class="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900">Invalid or expired invite</h1>
        <p class="text-gray-600">
          This invite link is no longer valid. It may have expired or already been used.
        </p>
        <a href="/register" class="inline-block mt-2 text-sm text-primary hover:underline">
          Request a new invite
        </a>
      </div>
    {:else}
      <div class="text-center">
        <h1 class="text-2xl font-bold text-gray-900">Complete your account</h1>
        <p class="mt-2 text-sm text-gray-600">
          Set your password to finish setting up your account.
        </p>
      </div>

      {#if error}
        <div class="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
      {/if}

      <form onsubmit={handleSubmit} class="space-y-4">
        <div>
          <label for="email" class="block text-sm font-medium text-gray-700">Email</label>
          <input
            id="email"
            type="email"
            value={inviteEmail}
            disabled
            class="mt-1 block w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500"
          />
        </div>
        <div>
          <label for="displayName" class="block text-sm font-medium text-gray-700">Display name</label>
          <input
            id="displayName"
            type="text"
            bind:value={displayName}
            autocomplete="name"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label for="password" class="block text-sm font-medium text-gray-700">Password</label>
          <input
            id="password"
            type="password"
            bind:value={password}
            required
            minlength={8}
            autocomplete="new-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label for="confirmPassword" class="block text-sm font-medium text-gray-700">Confirm password</label>
          <input
            id="confirmPassword"
            type="password"
            bind:value={confirmPassword}
            required
            minlength={8}
            autocomplete="new-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>
    {/if}
    </div>
  </div>
</div>
