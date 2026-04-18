<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon, { type IconName } from './Icon.svelte';

  type Variant = 'primary' | 'clay' | 'ghost' | 'chip';
  type Size = 'sm' | 'md';

  interface Props {
    children: Snippet;
    variant?: Variant;
    size?: Size;
    icon?: IconName;
    type?: 'button' | 'submit' | 'reset';
    disabled?: boolean;
    href?: string;
    onclick?: (event: MouseEvent) => void;
    class?: string;
  }

  let {
    children,
    variant = 'ghost',
    size = 'md',
    icon,
    type = 'button',
    disabled = false,
    href,
    onclick,
    class: klass = '',
  }: Props = $props();

  const VARIANTS: Record<Variant, string> = {
    primary: 'bg-ink text-paper border-transparent hover:bg-black/90',
    clay: 'bg-clay text-white border-transparent hover:bg-clay-ink',
    ghost: 'bg-transparent text-ink border-rule hover:bg-paper-2',
    chip: 'bg-paper-2 text-ink border-rule-soft hover:bg-paper-3',
  };

  const SIZES: Record<Size, string> = {
    sm: 'text-xs px-3 py-1.5 gap-1.5',
    md: 'text-[13px] px-4 py-2 gap-2',
  };

  const BASE =
    'inline-flex items-center rounded-full border font-sans font-medium whitespace-nowrap transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';

  const iconSize = $derived(size === 'sm' ? 12 : 14);
  const classes = $derived(`${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${klass}`);
</script>

{#if href}
  <a {href} class={classes} aria-disabled={disabled}>
    {#if icon}
      <Icon name={icon} size={iconSize} />
    {/if}
    {@render children()}
  </a>
{:else}
  <button {type} {onclick} {disabled} class={classes}>
    {#if icon}
      <Icon name={icon} size={iconSize} />
    {/if}
    {@render children()}
  </button>
{/if}
