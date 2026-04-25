<script lang="ts">
  /**
   * Reusable, optionally-editable view of an experiment's run table.
   *
   * Replaces the previous minimal `DesignMatrix.svelte`. Used inline on
   * the experiment detail page and inside `<DataTableModal>`.
   *
   * Conventions:
   * - Factor columns get a paper-tinted background.
   * - Response columns get a blue tinted background so the user can
   *   see at a glance what was classified as an outcome.
   * - Editable mode renders an inline `<input>` on click; commits on
   *   blur or Enter, discards on Escape.
   */

  interface Props {
    rows: Record<string, unknown>[];
    factorColumns: string[];
    responseColumns?: string[];
    editable?: boolean;
    onCellEdit?: (rowIdx: number, col: string, value: string) => void;
    highlightRunIndex?: number | null;
  }

  let {
    rows,
    factorColumns,
    responseColumns = [],
    editable = false,
    onCellEdit,
    highlightRunIndex = null,
  }: Props = $props();

  let editing = $state<{ row: number; col: string } | null>(null);
  let draft = $state('');

  const allColumns = $derived(() => {
    if (rows.length === 0) return [...factorColumns, ...responseColumns];
    const fromData = Object.keys(rows[0]);
    const known = new Set([...factorColumns, ...responseColumns]);
    const extras = fromData.filter((c) => !known.has(c));
    return [...factorColumns, ...responseColumns, ...extras];
  });

  function isFactor(col: string): boolean {
    return factorColumns.includes(col);
  }

  function isResponse(col: string): boolean {
    return responseColumns.includes(col);
  }

  function startEdit(rowIdx: number, col: string, current: unknown) {
    if (!editable) return;
    editing = { row: rowIdx, col };
    draft = current === null || current === undefined ? '' : String(current);
  }

  function commitEdit() {
    if (!editing) return;
    onCellEdit?.(editing.row, editing.col, draft);
    editing = null;
  }

  function cancelEdit() {
    editing = null;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitEdit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelEdit();
    }
  }

  function format(value: unknown): string {
    if (value === null || value === undefined || value === '') return '—';
    return String(value);
  }
</script>

<div class="overflow-x-auto rounded-md border border-gray-200">
  {#if rows.length === 0}
    <p class="p-4 text-sm text-gray-400">No data yet.</p>
  {:else}
    <table class="w-full text-sm">
      <thead class="sticky top-0 z-10 bg-gray-50">
        <tr>
          <th class="border-b border-gray-200 px-3 py-2 text-left text-xs font-medium uppercase text-gray-500">
            Run
          </th>
          {#each allColumns() as col (col)}
            <th
              class="border-b border-gray-200 px-3 py-2 text-left text-xs font-medium uppercase {isFactor(col) ? 'text-gray-700' : isResponse(col) ? 'text-blue-700' : 'text-gray-500'}"
            >
              {col}
              {#if isResponse(col)}
                <span class="ml-1 rounded bg-blue-100 px-1 py-0.5 text-[10px] uppercase text-blue-700">out</span>
              {/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as row, rowIdx (rowIdx)}
          <tr class={highlightRunIndex === rowIdx ? 'bg-yellow-50' : rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
            <td class="border-b border-gray-100 px-3 py-1.5 text-xs font-medium text-gray-500">
              {rowIdx + 1}
            </td>
            {#each allColumns() as col (col)}
              <td
                class="border-b border-gray-100 px-3 py-1.5 font-mono text-gray-700 {isFactor(col) ? 'bg-paper-2/40' : isResponse(col) ? 'bg-blue-50/40' : ''} {editable ? 'cursor-text' : ''}"
                onclick={() => startEdit(rowIdx, col, row[col])}
                role={editable ? 'button' : undefined}
                tabindex={editable ? 0 : undefined}
                onkeydown={editable
                  ? (e: KeyboardEvent) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        startEdit(rowIdx, col, row[col]);
                      }
                    }
                  : undefined}
              >
                {#if editing && editing.row === rowIdx && editing.col === col}
                  <!-- svelte-ignore a11y_autofocus -->
                  <input
                    class="w-full rounded border border-blue-400 bg-white px-1 py-0.5 font-mono text-gray-800 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    bind:value={draft}
                    onblur={commitEdit}
                    onkeydown={handleKeydown}
                    autofocus
                  />
                {:else}
                  {format(row[col])}
                {/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
