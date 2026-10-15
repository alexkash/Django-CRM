<script>
  import { resolve } from '$app/paths';
  import { asInternalPath } from '$lib/utils/paths.js';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import LegacyAdaptations from '$lib/v2/components/LegacyAdaptations.svelte';
  import LegacyFields from '$lib/v2/components/LegacyFields.svelte';
  import LegacyMessage from '$lib/v2/components/LegacyMessage.svelte';
  /** @type {{data: any}} */
  let { data } = $props();
  let record = $derived(data.record);
  let body = $derived(
    record.source_table === 'emails_text'
      ? record.fields
      : record.content?.find((/** @type {any} */ part) => part.source_table === 'emails_text')
          ?.fields
  );
  const routes = /** @type {Record<string,string>} */ ({
    'accounts.Account': 'accounts',
    'contacts.Contact': 'contacts',
    'leads.Lead': 'leads',
    'opportunity.Opportunity': 'pipeline',
    'tasks.Task': 'tasks',
    'common.Product': 'settings/products'
  });
</script>

<PageHeader title={record.title} record>
  {#snippet crumb()}<a href={resolve('/legacy')}>SuiteCRM history</a>{/snippet}
  {#snippet sub()}{record.source_table} · {record.source_id}{/snippet}
</PageHeader>
<div class="v2-scroll">
  <article class="v2-pad record">
    <p class="provenance">
      Исходная дата: {record.source_created_at ?? 'Не указано'} · Изменено: {record.source_updated_at ??
        'Не указано'}{record.source_deleted ? ' · Удалено в SuiteCRM' : ''}
    </p>
    {#if record.native?.length}<nav aria-label="Карточки CRM" class="native">
        {#each record.native as ref (`${ref.target_model}:${ref.target_id}:${ref.role}`)}{#if routes[ref.target_model]}<a
              class="v2-btn"
              href={resolve(asInternalPath(`/${routes[ref.target_model]}/${ref.target_id}`))}
              >Открыть карточку CRM →</a
            >{/if}{/each}
      </nav>{/if}
    <LegacyAdaptations adaptations={record.adaptations ?? []} />
    {#if record.kind === 'invoice' || record.kind === 'quote'}<div class="financial">
        <span>Исходный итог</span><strong>{record.fields.total_amount ?? 'Не указано'}</strong>
        <p>Исторический документ SuiteCRM.</p>
      </div>{/if}
    {#if body}<LegacyMessage
        bodyText={body.description ?? ''}
        bodyHtml={body.description_html ?? ''}
        from={body.from_addr ?? ''}
        to={body.to_addrs ?? ''}
        cc={body.cc_addrs ?? ''}
        bcc={body.bcc_addrs ?? ''}
      />{/if}
    <details open>
      <summary>Все исходные поля</summary><LegacyFields fields={record.fields} />
    </details>
    {#each record.content ?? [] as part, i (i)}{#if part.source_table !== 'emails_text'}<details>
          <summary>{part.source_table}</summary><LegacyFields fields={part.fields} />
        </details>{/if}{/each}
    {#if record.links?.length}<section>
        <h2 class="v2-label">Исходные связи</h2>
        <ul>
          {#each record.links as link (link.id)}<li>
              <a href={resolve(asInternalPath(`/legacy/${link.id}`))}>{link.title}</a>
              <small>{link.source_table}</small>
            </li>{/each}
        </ul>
      </section>{/if}
    {#if record.files?.length}<section>
        <h2 class="v2-label">Файлы</h2>
        <ul>
          {#each record.files as file (file.id)}<li>
              <a
                href={resolve(asInternalPath(`/api/legacy/files/${file.id}/download`))}
                data-sveltekit-reload>{file.original_name}</a
              > <small>{file.size} байт</small>
            </li>{/each}
        </ul>
      </section>{/if}
  </article>
</div>

<style>
  .record {
    padding-top: 18px;
    padding-bottom: 36px;
    max-width: 1100px;
  }
  .provenance {
    font-size: 12px;
    color: var(--v2-slate);
    overflow-wrap: anywhere;
  }
  .native {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: 16px 0;
  }
  .financial {
    padding: 16px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    margin: 16px 0;
    font-size: 13px;
  }
  .financial > span {
    display: block;
    color: var(--v2-slate);
    font-size: 12px;
  }
  .financial strong {
    display: block;
    font-size: 22px;
    margin: 6px 0;
  }
  .financial p {
    color: var(--v2-slate);
    margin: 0;
  }
  details,
  section {
    margin: 20px 0;
  }
  summary {
    cursor: pointer;
    font-size: 13px;
    margin-bottom: 14px;
    font-weight: 500;
  }
  ul {
    padding-left: 18px;
    font-size: 13px;
  }
  li {
    margin: 8px 0;
    overflow-wrap: anywhere;
  }
  small {
    font-size: 11px;
    color: var(--v2-slate);
  }
</style>
