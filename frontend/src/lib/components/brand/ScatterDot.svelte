<script lang="ts">
  interface Props {
    size?: number | string;
    color?: string;
    accent?: string;
    class?: string;
  }

  let {
    size = 12,
    color = 'var(--color-ink)',
    accent = 'var(--color-clay)',
    class: klass = '',
  }: Props = $props();
</script>

<svg width={size} height={size} viewBox="0 0 24 24" class={klass} aria-hidden="true">
  <circle cx="6" cy="15" r="1.7" fill={color} />
  <circle cx="11" cy="9" r="1.7" fill={color} />
  <circle cx="17" cy="13" r="1.7" fill={color} />
  <circle cx="13" cy="18" r="1.7" fill={accent} />
</svg>
