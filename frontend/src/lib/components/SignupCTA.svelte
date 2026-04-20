<script lang="ts">
  interface Props {
    token: string;
    variant?: 'hero' | 'footer';
  }

  let { token, variant = 'hero' }: Props = $props();

  let registerHref = $derived(
    `/register?ref=share&token=${encodeURIComponent(token)}`,
  );
</script>

{#if variant === 'hero'}
  <section
    class="relative overflow-hidden rounded-xl bg-gradient-to-br from-primary to-blue-700 px-6 py-8 text-white shadow-lg sm:px-10 sm:py-10"
  >
    <div class="max-w-3xl">
      <h2 class="text-2xl font-bold sm:text-3xl">Run this analysis on your own data</h2>
      <p class="mt-2 text-sm text-white/90 sm:text-base">
        Factorial lets you design, run, and share experiments like this one
        — with an agent walking you through factors, response surfaces,
        and statistical analysis.
      </p>
      <div class="mt-5 flex flex-wrap gap-3">
        <a
          href={registerHref}
          class="rounded-md bg-white px-5 py-2 text-sm font-semibold text-primary hover:bg-gray-100 transition-colors"
        >
          Sign up free
        </a>
        <a
          href="/login"
          class="rounded-md border border-white/40 px-5 py-2 text-sm font-medium text-white hover:bg-white/10 transition-colors"
        >
          Sign in
        </a>
      </div>
    </div>
  </section>
{:else}
  <section class="rounded-lg border border-gray-200 bg-gray-50 px-6 py-6 text-center">
    <h3 class="text-lg font-semibold text-gray-800">Design your own experiments</h3>
    <p class="mt-1 text-sm text-gray-600">
      Create a free account to run analyses like this on your own data.
    </p>
    <div class="mt-4 flex justify-center gap-3">
      <a
        href={registerHref}
        class="rounded-md bg-primary px-5 py-2 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
      >
        Sign up free
      </a>
      <a
        href="/login"
        class="rounded-md border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
      >
        Sign in
      </a>
    </div>
  </section>
{/if}
