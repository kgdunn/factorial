<script lang="ts">
  export type IconName =
    | 'home'
    | 'folder'
    | 'chat'
    | 'table'
    | 'chart'
    | 'cube'
    | 'contour'
    | 'gear'
    | 'plus'
    | 'arrow'
    | 'check'
    | 'close'
    | 'dots'
    | 'search'
    | 'sparkle'
    | 'download'
    | 'back'
    | 'forward';

  interface Props {
    name: IconName;
    size?: number;
    color?: string;
    class?: string;
  }

  let { name, size = 18, color = 'currentColor', class: klass = '' }: Props = $props();
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 20 20"
  style="color: {color};"
  class={klass}
  aria-hidden="true"
>
  {#if name === 'home'}
    <path
      d="M3 10 L10 3 L17 10 M5 9 V17 H15 V9"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linejoin="round"
    />
  {:else if name === 'folder'}
    <path
      d="M3 6 H8 L10 4 H17 V16 H3 Z"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linejoin="round"
    />
  {:else if name === 'chat'}
    <path
      d="M3 5 H17 V13 H10 L6 16 V13 H3 Z"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linejoin="round"
    />
  {:else if name === 'table'}
    <path
      d="M3 5 H17 V15 H3 Z M3 9 H17 M9 5 V15"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
    />
  {:else if name === 'chart'}
    <path
      d="M3 17 V3 M3 17 H17 M6 13 L9 9 L12 11 L16 6"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linejoin="round"
    />
  {:else if name === 'cube'}
    <path
      d="M10 3 L17 7 V13 L10 17 L3 13 V7 Z M10 3 V10 M3 7 L10 10 L17 7"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linejoin="round"
    />
  {:else if name === 'contour'}
    <g fill="none" stroke="currentColor" stroke-width="1.4">
      <ellipse cx="10" cy="10" rx="6" ry="4" />
      <ellipse cx="10" cy="10" rx="3" ry="2" />
      <circle cx="10" cy="10" r="0.8" fill="currentColor" />
    </g>
  {:else if name === 'gear'}
    <g fill="none" stroke="currentColor" stroke-width="1.4">
      <circle cx="10" cy="10" r="2.4" />
      <path
        d="M10 3.5 V5.5 M10 14.5 V16.5 M3.5 10 H5.5 M14.5 10 H16.5 M5.4 5.4 L6.8 6.8 M13.2 13.2 L14.6 14.6 M5.4 14.6 L6.8 13.2 M13.2 6.8 L14.6 5.4"
      />
    </g>
  {:else if name === 'plus'}
    <path
      d="M10 4 V16 M4 10 H16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
    />
  {:else if name === 'arrow'}
    <path
      d="M4 10 H16 M12 6 L16 10 L12 14"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  {:else if name === 'check'}
    <path
      d="M4 10 L8 14 L16 5"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  {:else if name === 'close'}
    <path
      d="M5 5 L15 15 M15 5 L5 15"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
    />
  {:else if name === 'dots'}
    <g fill="currentColor">
      <circle cx="5" cy="10" r="1.3" />
      <circle cx="10" cy="10" r="1.3" />
      <circle cx="15" cy="10" r="1.3" />
    </g>
  {:else if name === 'search'}
    <g fill="none" stroke="currentColor" stroke-width="1.4">
      <circle cx="9" cy="9" r="4.5" />
      <path d="M12.5 12.5 L16 16" stroke-linecap="round" />
    </g>
  {:else if name === 'sparkle'}
    <path
      d="M10 3 L11.5 8.5 L17 10 L11.5 11.5 L10 17 L8.5 11.5 L3 10 L8.5 8.5 Z"
      fill="currentColor"
    />
  {:else if name === 'download'}
    <path
      d="M10 3 V13 M6 9 L10 13 L14 9 M4 16 H16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.4"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  {:else if name === 'back'}
    <path
      d="M13 4 L6 10 L13 16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  {:else if name === 'forward'}
    <path
      d="M7 4 L14 10 L7 16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.6"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  {/if}
</svg>
