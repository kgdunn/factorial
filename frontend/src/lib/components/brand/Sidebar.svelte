<script lang="ts">
  import Wordmark from './Wordmark.svelte';
  import Icon, { type IconName } from './Icon.svelte';

  export interface ProjectMeta {
    name: string;
    meta?: string;
  }

  export interface NavItem {
    id: string;
    label: string;
    icon: IconName;
    href?: string;
    projectScoped?: boolean;
  }

  interface Props {
    current: string;
    project?: ProjectMeta | null;
    user?: { initials: string; name: string; meta?: string };
    onnavigate?: (id: string) => void;
  }

  let { current, project = null, user, onnavigate }: Props = $props();

  const GROUPS: Array<{ kind: 'group'; items: NavItem[] } | { kind: 'divider' }> = [
    {
      kind: 'group',
      items: [{ id: 'projects', label: 'Projects', icon: 'folder' }],
    },
    { kind: 'divider' },
    {
      kind: 'group',
      items: [
        { id: 'chat', label: 'Agent', icon: 'chat', projectScoped: true },
        { id: 'runsheet', label: 'Run-sheet', icon: 'table', projectScoped: true },
        { id: 'entry', label: 'Enter results', icon: 'plus', projectScoped: true },
      ],
    },
    { kind: 'divider' },
    {
      kind: 'group',
      items: [
        { id: 'effects', label: 'Effects', icon: 'chart', projectScoped: true },
        { id: 'contour', label: 'Contour', icon: 'contour', projectScoped: true },
        { id: 'surface', label: '3D surface', icon: 'cube', projectScoped: true },
      ],
    },
    { kind: 'divider' },
    {
      kind: 'group',
      items: [{ id: 'settings', label: 'Settings', icon: 'gear' }],
    },
  ];

  function handleClick(item: NavItem) {
    if (item.projectScoped && !project) return;
    onnavigate?.(item.id);
  }
</script>

<aside
  class="flex w-[232px] shrink-0 flex-col border-r border-rule bg-paper-2"
>
  <div class="border-b border-rule px-[22px] pb-4 pt-[22px]">
    <Wordmark size={22} onclick={() => onnavigate?.('projects')} />
  </div>

  {#if project}
    <div class="border-b border-rule px-[22px] pb-3 pt-4">
      <div class="mb-1.5 font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
        project
      </div>
      <div class="font-serif italic text-[20px] leading-[1.15] text-ink">{project.name}</div>
      {#if project.meta}
        <div class="mt-1.5 font-mono text-[10px] text-ink-faint">{project.meta}</div>
      {/if}
    </div>
  {/if}

  <nav class="flex-1 overflow-auto px-3 py-3.5">
    {#each GROUPS as group, gi (gi)}
      {#if group.kind === 'divider'}
        <div class="my-2.5 mx-2.5 h-px bg-rule"></div>
      {:else}
        {#each group.items as item (item.id)}
          {@const active = current === item.id}
          {@const dim = item.projectScoped && !project}
          <button
            type="button"
            onclick={() => handleClick(item)}
            disabled={dim}
            class="mb-0.5 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left font-sans text-[13.5px] transition-colors
                   {active ? 'bg-clay-tint text-clay-ink font-medium' : 'text-ink'}
                   {dim ? 'cursor-not-allowed opacity-50 text-ink-faint' : 'cursor-pointer hover:bg-paper-3'}"
          >
            <Icon name={item.icon} size={16} />
            <span class="flex-1">{item.label}</span>
            {#if active}
              <span class="h-1 w-1 rounded-full bg-clay"></span>
            {/if}
          </button>
        {/each}
      {/if}
    {/each}
  </nav>

  {#if user}
    <div class="flex items-center gap-2.5 border-t border-rule px-[22px] py-4">
      <div
        class="flex h-7 w-7 items-center justify-center rounded-full bg-ink font-mono text-[11px] text-paper"
      >
        {user.initials}
      </div>
      <div class="leading-tight">
        <div class="font-sans text-xs text-ink">{user.name}</div>
        {#if user.meta}
          <div class="font-mono text-[10px] text-ink-faint">{user.meta}</div>
        {/if}
      </div>
    </div>
  {/if}
</aside>
