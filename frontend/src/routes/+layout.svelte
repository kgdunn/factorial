<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<div class="flex h-screen flex-col">
  <!-- Navigation bar -->
  <nav class="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
    <a href="/" class="text-lg font-bold text-gray-800">
      Agentic <span class="text-primary">DOE</span>
    </a>
    <div class="flex items-center gap-6">
      <a
        href="/"
        class="text-sm text-gray-600 hover:text-primary transition-colors"
      >
        Home
      </a>
      <a
        href="/chat"
        class="text-sm text-gray-600 hover:text-primary transition-colors"
      >
        Chat
      </a>
    </div>
  </nav>

  <!-- Page content -->
  <main class="flex-1 overflow-hidden">
    {@render children()}
  </main>
</div>
