<script>
  import { resolve } from '$app/paths';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import { asInternalPath } from '$lib/utils/paths.js';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { shortDate } from '$lib/v2/format.js';
  /** @type {{data: any}} */
  let { data } = $props();
  const kinds = [
    ['', 'Все типы'],
    ['call', 'Звонки'],
    ['meeting', 'Встречи'],
    ['email', 'Письма'],
    ['invoice', 'Счета'],
    ['quote', 'Предложения'],
    ['note', 'Заметки'],
    ['change', 'Лента изменений'],
    ['audit', 'Аудит'],
    ['record', 'Остальные записи']
  ];
  /** @param {string|null} upstream */
  function paging(upstream) {
    if (!upstream) return '/legacy';
    const params = new SvelteURLSearchParams(data.query);
    const next = new URL(upstream, 'http://local').searchParams;
    params.set('offset', next.get('offset') ?? '0');
    return `/legacy?${params}`;
  }
</script>

<PageHeader title="SuiteCRM history">
  {#snippet sub()}Исторические данные · {data.history.count} записей{/snippet}
</PageHeader>
<div class="v2-scroll">
  <div class="v2-pad history-page">
    <nav aria-label="Разделы истории" class="tabs">
      <a class:active={!data.filesView} href={resolve('/legacy')}>Записи</a><a
        class:active={data.filesView}
        href="{resolve('/legacy')}?view=files">Файлы</a
      >
    </nav>
    <form method="GET" class="filters">
      {#if data.filesView}<input type="hidden" name="view" value="files" />{/if}
      {#if data.query.entity}<input type="hidden" name="entity" value={data.query.entity} /><input
          type="hidden"
          name="id"
          value={data.query.id}
        />{/if}
      <label
        >Поиск<input
          name="q"
          value={data.query.q ?? ''}
          placeholder="Тема, текст, адрес"
          maxlength="500"
        /></label
      >
      {#if !data.filesView}
        <label
          >Тип<select name="kind" value={data.query.kind ?? ''}
            >{#each kinds as [value, label] (value)}<option {value}>{label}</option>{/each}</select
          ></label
        >
        <label
          >Модуль<input
            name="table"
            value={data.query.table ?? ''}
            placeholder="Например, accounts"
          /></label
        >
        <label>С даты<input type="date" name="from" value={data.query.from ?? ''} /></label>
        <label>По дату<input type="date" name="to" value={data.query.to ?? ''} /></label>
        <label class="check"
          ><input
            type="checkbox"
            name="deleted"
            value="all"
            checked={data.query.deleted === 'all'}
          />Включая удалённые</label
        >
      {/if}
      <button class="v2-btn" type="submit">Найти</button>
    </form>
    {#if data.query.entity}<p class="context">
        История карточки <code>{data.query.entity}:{data.query.id}</code> ·
        <a href={resolve('/legacy')}>Все записи</a>
      </p>{/if}
    {#if !data.history.results.length}<p class="empty">По этим условиям записей нет.</p>
    {:else}<div class="table-wrap">
        <table class="v2-table">
          <thead
            ><tr
              ><th>{data.filesView ? 'Файл' : 'Запись'}</th><th
                >{data.filesView ? 'Размер' : 'Модуль'}</th
              ><th>{data.filesView ? 'Скачать' : 'Исходная дата'}</th></tr
            ></thead
          ><tbody>
            {#each data.history.results as record (record.id)}<tr>
                {#if data.filesView}<td>{record.original_name}</td><td>{record.size} байт</td><td
                    ><a
                      href={resolve(asInternalPath(`/api/legacy/files/${record.id}/download`))}
                      data-sveltekit-reload>Скачать</a
                    ></td
                  >
                {:else}<td
                    ><a href={resolve(asInternalPath(`/legacy/${record.id}`))}>{record.title}</a
                    >{#if record.source_deleted}<span class="deleted">Удалено в SuiteCRM</span
                      >{/if}</td
                  ><td>{record.source_table}</td><td
                    >{record.source_created_at
                      ? shortDate(record.source_created_at)
                      : 'Не указано'}</td
                  >{/if}
              </tr>{/each}
          </tbody>
        </table>
      </div>{/if}
    <nav class="pagination" aria-label="Страницы истории">
      {#if data.history.previous}<a
          class="v2-btn"
          href={resolve(asInternalPath(paging(data.history.previous)))}>← Назад</a
        >{/if}
      {#if data.history.next}<a
          class="v2-btn"
          href={resolve(asInternalPath(paging(data.history.next)))}>Далее →</a
        >{/if}
    </nav>
  </div>
</div>

<style>
  .history-page {
    padding-top: 18px;
    padding-bottom: 32px;
  }
  .tabs {
    display: flex;
    gap: 20px;
    border-bottom: 1px solid var(--v2-line);
    padding-bottom: 12px;
    margin-bottom: 20px;
    font-size: 13px;
  }
  .active {
    font-weight: 600;
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: 12px;
    margin-bottom: 20px;
  }
  label {
    display: grid;
    gap: 5px;
    font-size: 11px;
    color: var(--v2-slate);
  }
  input,
  select {
    border: 1px solid var(--v2-line);
    border-radius: 5px;
    background: var(--v2-paper);
    padding: 8px;
    font: inherit;
    color: var(--v2-ink);
    min-width: 0;
  }
  .check {
    display: flex;
    align-items: center;
    padding: 8px 0;
  }
  .table-wrap {
    overflow: auto;
  }
  td {
    max-width: 600px;
    overflow-wrap: anywhere;
  }
  .pagination {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-top: 20px;
  }
  .context,
  .empty {
    font-size: 13px;
    color: var(--v2-slate);
  }
  .deleted {
    display: block;
    font-size: 11px;
    color: var(--v2-rust);
  }
  @media (max-width: 600px) {
    .filters > label {
      flex: 1 1 140px;
    }
    .filters > label:first-child {
      flex-basis: 100%;
    }
    .filters input,
    .filters select {
      width: 100%;
    }
    .filters .check input {
      width: auto;
    }
    .v2-table {
      min-width: 480px;
    }
  }
</style>
