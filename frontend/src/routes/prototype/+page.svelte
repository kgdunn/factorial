<script lang="ts">
  const src = '/prototypes/in-app-prototype.html';
</script>

<svelte:head>
  <title>factori.al — In-App Prototype</title>
</svelte:head>

<div class="flex h-full flex-col">
  <div
    class="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-2 text-xs text-gray-500"
  >
    <span>
      factori.al · in-app prototype
      <span class="mx-2 text-gray-300">·</span>
      reference design
    </span>
    <div class="flex items-center gap-4">
      <a href={src} target="_blank" rel="noopener" class="hover:text-gray-800">Open in new tab</a>
      <a href="/experiments" class="hover:text-gray-800">Back to app</a>
    </div>
  </div>
  <iframe
    title="factori.al in-app prototype"
    {src}
    class="min-h-0 w-full flex-1 border-0"
  ></iframe>
</div>
