<script>
  import { resolve } from '$app/paths';
  import { asInternalPath } from '$lib/utils/paths.js';
  import { pageHref } from '$lib/v2/pagination.js';
  /** @type {{pagination:any,url:URL,pageTotals?:boolean}} */
  let { pagination: p, url, pageTotals = false } = $props();
</script>

{#if p}
  <nav aria-label="Pagination" class="list-pagination">
    <div class="summary">
      <span>Showing <b>{p.start}–{p.end}</b> of <b>{p.count}</b></span>
      {#if pageTotals && p.count > p.shown}<small>Additional totals describe this page.</small>{/if}
    </div>
    <div class="controls">
      {#if p.previous !== null}<a
          class="v2-btn"
          rel="prev"
          href={resolve(asInternalPath(pageHref(url, p.previous, p.limit)))}>Previous</a
        >{:else}<span class="v2-btn disabled" aria-disabled="true">Previous</span>{/if}
      <span class="page-number"
        >{#if p.offset > 0 && p.offset >= p.count}Page unavailable{:else}Page {p.current} of {p.pages}{/if}</span
      >
      {#if p.next !== null}<a
          class="v2-btn"
          rel="next"
          href={resolve(asInternalPath(pageHref(url, p.next, p.limit)))}>Next</a
        >{:else}<span class="v2-btn disabled" aria-disabled="true">Next</span>{/if}
    </div>
  </nav>
{/if}

<style>
  .list-pagination {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 24px 24px;
    color: var(--v2-slate);
    font-size: 12px;
  }
  .summary {
    display: grid;
    gap: 4px;
  }
  .summary b {
    font-variant-numeric: tabular-nums;
  }
  .summary small {
    font-size: 11px;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .page-number {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .disabled {
    opacity: 0.45;
    cursor: default;
  }
  /* Keep controls clear of the shell's fixed New deal button. */
  @media (max-width: 768px) {
    .list-pagination {
      padding-right: 78px;
    }
  }
  @media (max-width: 600px) {
    .list-pagination {
      padding: 14px 78px 24px 16px;
    }
    .controls {
      width: 100%;
      justify-content: space-between;
      gap: 8px;
    }
  }
</style>
