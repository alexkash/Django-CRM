<script>
  /** @type {{fields: Record<string, any>}} */
  let { fields } = $props();
  /** @param {any} value */
  function display(value) {
    if (value === null || value === undefined || value === '') return 'Не указано';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  }
</script>

<dl class="legacy-fields">
  {#each Object.entries(fields) as [key, value] (key)}
    <div>
      <dt>{key}</dt>
      <dd>{display(value)}</dd>
    </div>
  {/each}
</dl>

<style>
  .legacy-fields {
    margin: 0;
    display: grid;
    gap: 12px;
  }
  .legacy-fields > div {
    display: grid;
    grid-template-columns: minmax(120px, 1fr) minmax(0, 3fr);
    gap: 12px;
    border-bottom: 1px solid var(--v2-line-soft);
    padding: 8px 0;
  }
  dt {
    color: var(--v2-slate);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  dd {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    min-width: 0;
    font-size: 13px;
  }
  @media (max-width: 600px) {
    .legacy-fields > div {
      grid-template-columns: 1fr;
      gap: 4px;
    }
  }
</style>
