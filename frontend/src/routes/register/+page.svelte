<script lang="ts">
  import { getRoles, type Role } from '$lib/api/roles';
  import { postSignupRequest } from '$lib/api/signup';

  let email = $state('');
  let useCase = $state('');
  let roleId = $state<string>(''); // '' | '__other' | <role.id>
  let otherLabel = $state('');
  let error = $state<string | null>(null);
  let loading = $state(false);
  let submitted = $state(false);

  let roles = $state<Role[]>([]);
  let rolesLoaded = $state(false);

  const maxChars = 400;
  let charsLeft = $derived(maxChars - useCase.length);

  $effect(() => {
    getRoles()
      .then((rs) => {
        roles = rs;
        rolesLoaded = true;
      })
      .catch(() => {
        // Non-fatal: signup still works without a role
        rolesLoaded = true;
      });
  });

  function buildRequestedRole(): string | null {
    if (!roleId) return null;
    if (roleId === '__other') {
      const trimmed = otherLabel.trim();
      return trimmed ? `other:${trimmed}` : null;
    }
    const picked = roles.find((r) => r.id === roleId);
    return picked ? picked.name : null;
  }

  let canSubmit = $derived(
    !!email &&
      useCase.length >= 10 &&
      !!roleId &&
      (roleId !== '__other' || otherLabel.trim().length > 0),
  );

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = null;
    const rr = buildRequestedRole();
    if (!rr) {
      error =
        roleId === '__other'
          ? 'Please describe your role.'
          : 'Please pick your role.';
      return;
    }
    loading = true;
    try {
      await postSignupRequest(email, useCase, rr);
      submitted = true;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Something went wrong';
    } finally {
      loading = false;
    }
  }

  function displayRoleName(r: Role): string {
    return r.description || r.name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
</script>

<div class="flex min-h-full items-center justify-center px-4 py-12">
  <div class="w-full max-w-md space-y-6">
    {#if submitted}
      <!-- Success confirmation -->
      <div class="text-center space-y-4">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
          <svg class="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900">Request received</h1>
        <p class="text-gray-600">
          Thanks for your interest! We've sent a confirmation to <strong>{email}</strong> with a copy
          of your submission. You'll receive another email once your account is approved.
        </p>
        <a href="/" class="inline-block mt-4 text-sm text-primary hover:underline">
          Back to home
        </a>
      </div>
    {:else}
      <!-- Signup request form -->
      <div class="text-center">
        <h1 class="text-2xl font-bold text-gray-900">Request access</h1>
        <p class="mt-2 text-sm text-gray-600">
          Tell us about yourself and we'll get back to you shortly.
        </p>
        <p class="mt-1 text-sm text-gray-500">
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
          <label for="role" class="block text-sm font-medium text-gray-700">
            Your role <span class="text-red-500">*</span>
          </label>
          <select
            id="role"
            bind:value={roleId}
            required
            disabled={!rolesLoaded}
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="" disabled>— Select your role —</option>
            {#each roles as role}
              <option value={role.id}>{displayRoleName(role)}</option>
            {/each}
            <option value="__other">Other (describe below)</option>
          </select>
          <p class="mt-1 text-xs text-gray-500">
            We use your role to tailor the assistant's explanations and examples.
          </p>

          {#if roleId === '__other'}
            <input
              id="other-role"
              type="text"
              bind:value={otherLabel}
              required
              placeholder="e.g. Polymer scientist working on coatings"
              maxlength={100}
              class="mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <p class="mt-1 text-xs text-gray-500">
              Describe your role in a sentence so the admin can set up the right role for you
              (or contact you to clarify).
            </p>
          {/if}
        </div>

        <div>
          <label for="useCase" class="block text-sm font-medium text-gray-700">
            Why do you want to use Agentic DOE?
          </label>
          <textarea
            id="useCase"
            bind:value={useCase}
            required
            minlength={10}
            maxlength={maxChars}
            rows={5}
            placeholder="E.g. I'm working on process optimization and would like to use DOE methods with AI assistance to..."
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary resize-none"
          ></textarea>
          <p class="mt-1 text-xs text-gray-500 text-right">
            <span class={charsLeft < 50 ? 'text-orange-500 font-medium' : ''}>{charsLeft}</span>
            characters remaining
          </p>
        </div>

        <button
          type="submit"
          disabled={loading || !canSubmit}
          class="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? 'Submitting...' : 'Request access'}
        </button>
      </form>
    {/if}
  </div>
</div>
