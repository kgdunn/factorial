<script lang="ts">
  import { page } from '$app/stores';

  const tabs = [
    { label: 'Signups', href: '/admin/signups' },
    { label: 'Users', href: '/admin/users' },
    { label: 'Roles', href: '/admin/roles' },
    { label: 'Feedback', href: '/admin/feedback' },
  ];

  let { children } = $props();

  function isActive(href: string): boolean {
    return $page.url.pathname === href || $page.url.pathname.startsWith(href + '/');
  }
</script>

<div class="h-full overflow-y-auto">
  <div class="border-b border-gray-200 bg-white">
    <div class="mx-auto max-w-5xl px-6 py-4">
      <h1 class="text-2xl font-bold text-gray-900">Admin</h1>
      <nav class="mt-4 flex gap-1" aria-label="Admin sections">
        {#each tabs as tab}
          <a
            href={tab.href}
            class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors
              {isActive(tab.href)
                ? 'bg-primary text-white'
                : 'text-gray-600 hover:bg-gray-100'}"
          >
            {tab.label}
          </a>
        {/each}
      </nav>
    </div>
  </div>

  {@render children()}
</div>
