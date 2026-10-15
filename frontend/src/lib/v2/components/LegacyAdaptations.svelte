<script>
  /** @type {{adaptations: any[]}} */
  let { adaptations } = $props();
  const labels = /** @type {Record<string,string>} */ ({
    duplicate_name: 'Совпадающее название сохранено с исходным идентификатором',
    duplicate_email: 'Email встречается у нескольких людей; исходный адрес сохранён',
    original_phone_preserved: 'Исходный телефон сохранён без сокращения',
    historical_financial_record: 'Документ сохранён в истории',
    unknown_total: 'Итог не указан в исходной CRM',
    missing_billing_account: 'В исходном документе не указана компания',
    no_certified_complete_line_items: 'Недостаточно данных для рабочего финансового документа'
  });
</script>

{#if adaptations?.length}<aside>
    <h3 class="v2-label">Особенности переноса</h3>
    <ul>
      {#each adaptations as item, i (i)}<li>
          {labels[typeof item === 'string' ? item : item.reason] ??
            (typeof item === 'string'
              ? item
              : item.reason)}{#if typeof item === 'object' && item.original}<div class="original">
              {item.field}: {item.original}
            </div>{/if}
        </li>{/each}
    </ul>
  </aside>{/if}

<style>
  aside {
    padding: 12px 0;
    font-size: 12px;
  }
  h3 {
    margin: 0 0 8px;
  }
  ul {
    padding-left: 16px;
    margin: 0;
  }
  li {
    margin: 6px 0;
    overflow-wrap: anywhere;
  }
  .original {
    white-space: pre-wrap;
    margin-top: 4px;
    color: var(--v2-slate);
  }
</style>
