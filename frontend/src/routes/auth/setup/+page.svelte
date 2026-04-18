<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { getSetupValidation } from '$lib/api/auth';
  import { authState } from '$lib/state/auth.svelte';

  let email = $state('');
  let tokenValid = $state<boolean | null>(null);
  let purpose = $state<'setup' | 'reset' | null>(null);
  let password = $state('');
  let confirmPassword = $state('');
  let error = $state<string | null>(null);
  let loading = $state(false);

  $effect(() => {
    const token = $page.url.searchParams.get('token');
    if (!token) {
      tokenValid = false;
      return;
    }
    getSetupValidation(token)
      .then((res) => {
        tokenValid = res.valid;
        if (res.valid) {
          email = res.email;
          purpose = res.purpose;
        }
      })
      .catch(() => {
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
      error = 'Missing token';
      return;
    }

    loading = true;
    try {
      await authState.completeSetup(token, password);
      goto('/chat');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Setup failed';
    } finally {
      loading = false;
    }
  }

  let heading = $derived(purpose === 'reset' ? 'Reset your password' : 'Welcome — set your password');
  let blurb = $derived(
    purpose === 'reset'
      ? "Pick a new password for your account."
      : "Choose a password to activate your account and log in.",
  );
</script>

<div class="flex min-h-full items-center justify-center px-4 py-12">
  <div class="w-full max-w-sm space-y-6">
    {#if tokenValid === null}
      <div class="text-center">
        <p class="text-gray-500">Validating your link...</p>
      </div>
    {:else if !tokenValid}
      <div class="text-center space-y-4">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
          <svg class="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900">Invalid or expired link</h1>
        <p class="text-gray-600">
          This link is no longer valid. It may have expired or already been used.
        </p>
        <a href="/auth/reset" class="inline-block mt-2 text-sm text-primary hover:underline">
          Request a new link
        </a>
      </div>
    {:else}
      <div class="text-center">
        <h1 class="text-2xl font-bold text-gray-900">{heading}</h1>
        <p class="mt-2 text-sm text-gray-600">{blurb}</p>
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
            value={email}
            disabled
            class="mt-1 block w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500"
          />
        </div>
        <div>
          <label for="password" class="block text-sm font-medium text-gray-700">New password</label>
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
          {loading ? 'Saving...' : (purpose === 'reset' ? 'Save new password' : 'Activate account')}
        </button>
      </form>
    {/if}
  </div>
</div>
