<script lang="ts">
  import { goto } from '$app/navigation';
  import { authState } from '$lib/state/auth.svelte';

  let email = $state('');
  let password = $state('');
  let confirmPassword = $state('');
  let displayName = $state('');
  let background = $state('');
  let error = $state<string | null>(null);
  let loading = $state(false);

  const backgrounds = [
    { value: '', label: 'Select your background...' },
    { value: 'chemical_engineer', label: 'Chemical engineer' },
    { value: 'pharmaceutical_scientist', label: 'Pharmaceutical scientist' },
    { value: 'food_scientist', label: 'Food scientist' },
    { value: 'academic_researcher', label: 'Academic researcher' },
    { value: 'quality_engineer', label: 'Quality engineer' },
    { value: 'data_scientist', label: 'Data scientist' },
    { value: 'student', label: 'Student' },
    { value: 'other', label: 'Other' },
  ];

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = null;

    if (password !== confirmPassword) {
      error = 'Passwords do not match';
      return;
    }

    loading = true;
    try {
      await authState.register(
        email,
        password,
        displayName || undefined,
        background || undefined,
      );
      goto('/chat');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Registration failed';
    } finally {
      loading = false;
    }
  }
</script>

<div class="flex min-h-full items-center justify-center px-4 py-12">
  <div class="w-full max-w-sm space-y-6">
    <div class="text-center">
      <h1 class="text-2xl font-bold text-gray-900">Create account</h1>
      <p class="mt-2 text-sm text-gray-600">
        Already have an account?
        <a href="/login" class="text-primary hover:underline">Sign in</a>
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
          bind:value={email}
          required
          autocomplete="email"
          class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
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
        <label for="background" class="block text-sm font-medium text-gray-700">Background</label>
        <select
          id="background"
          bind:value={background}
          class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {#each backgrounds as bg}
            <option value={bg.value}>{bg.label}</option>
          {/each}
        </select>
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
  </div>
</div>
