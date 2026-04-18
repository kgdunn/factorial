<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import ChatWindow from '$lib/components/ChatWindow.svelte';
  import TopBar from '$lib/components/brand/TopBar.svelte';
  import Btn from '$lib/components/brand/Btn.svelte';
  import { chatState } from '$lib/state/chat.svelte';

  $effect(() => {
    const convId = $page.url.searchParams.get('conversation_id');
    if (convId) {
      chatState.loadConversation(convId);
    }
  });
</script>

<svelte:head>
  <title>Plan with the agent | factori.al</title>
</svelte:head>

<div class="flex h-full flex-col bg-paper">
  <TopBar breadcrumb="new experiment · draft" title={title} actions={actions} />

  {#snippet title()}
    Plan with the <em class="text-clay-ink">agent</em>.
  {/snippet}

  {#snippet actions()}
    <Btn variant="ghost" icon="download" size="sm">Transcript</Btn>
    <Btn variant="primary" onclick={() => goto('/experiments')}>Continue to experiments</Btn>
  {/snippet}

  <div class="flex-1 min-h-0">
    <ChatWindow />
  </div>
</div>
