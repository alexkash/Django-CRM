<script>
  import { resolve } from '$app/paths';
  import { asInternalPath } from '$lib/utils/paths.js';
  import LegacyAdaptations from './LegacyAdaptations.svelte';
  import { shortDate } from '$lib/v2/format.js';
  /** @type {{history: any, model: string, id: string}} */
  let { history, model, id } = $props();
  let href = $derived(`/legacy?entity=${encodeURIComponent(model)}&id=${encodeURIComponent(id)}`);
</script>

<section class="history" aria-label="История SuiteCRM">
  <div class="heading">
    <h2 class="v2-label">SuiteCRM history</h2>
    <a href={resolve(asInternalPath(href))}>Вся история →</a>
  </div>
  {#if history?.error}<p role="alert">{history.error}</p>
  {:else if history?.results?.length}
    <ul>
      {#each history.results as record (record.id)}<li>
          <a href={resolve(asInternalPath(`/legacy/${record.id}`))}>{record.title}</a><span
            >{record.source_table} · {record.source_created_at
              ? shortDate(record.source_created_at)
              : 'Дата не указана'}</span
          ><LegacyAdaptations adaptations={record.adaptations ?? []} />
        </li>{/each}
    </ul>
  {:else}<p>Связанной истории SuiteCRM нет.</p>{/if}
</section>

<style>
  .history {
    margin: 22px 0;
    padding: 16px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    min-width: 0;
  }
  .heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .heading h2 {
    margin: 0;
  }
  .heading a {
    font-size: 12px;
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 12px 0 0;
  }
  li {
    padding: 9px 0;
    border-top: 1px solid var(--v2-line-soft);
    display: grid;
    gap: 4px;
    overflow-wrap: anywhere;
  }
  li > a {
    font-size: 13px;
  }
  span,
  p {
    font-size: 12px;
    color: var(--v2-slate);
  }
</style>
