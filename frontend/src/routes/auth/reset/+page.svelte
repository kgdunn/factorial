<script lang="ts">
  import { postPasswordResetRequest } from '$lib/api/auth';

  let email = $state('');
  let submitted = $state(false);
  let loading = $state(false);

  async function handleSubmit(e: Event) {
    e.preventDefault();
    loading = true;
    try {
      await postPasswordResetRequest(email);
    } finally {
      loading = false;
      submitted = true;
    }
  }
</script>

<div class="flex min-h-full items-center justify-center px-4 py-12">
  <div class="w-full max-w-sm space-y-6">
    {#if submitted}
      <div class="text-center space-y-4">
        <h1 class="text-2xl font-bold text-gray-900">Check your email</h1>
        <p class="text-gray-600">
          If <strong>{email}</strong> is associated with an account, we've just sent you a link to reset your password.
        </p>
        <a href="/login" class="inline-block mt-2 text-sm text-primary hover:underline">
          Back to sign in
        </a>
      </div>
    {:else}
      <div class="text-center">
        <h1 class="text-2xl font-bold text-gray-900">Reset your password</h1>
        <p class="mt-2 text-sm text-gray-600">
          Enter your email and we'll send you a reset link.
        </p>
      </div>

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
        <button
          type="submit"
          disabled={loading || !email}
          class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? 'Sending...' : 'Send reset link'}
        </button>
        <div class="text-center text-sm text-gray-500">
          <a href="/login" class="text-primary hover:underline">Back to sign in</a>
        </div>
      </form>
    {/if}
  </div>
</div>
