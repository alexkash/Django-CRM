<script>
  /** @type {{bodyText?: string, bodyHtml?: string, from?: string, to?: string, cc?: string, bcc?: string}} */
  let { bodyText = '', bodyHtml = '', from = '', to = '', cc = '', bcc = '' } = $props();
</script>

<section aria-label="Историческое письмо" class="message">
  <dl>
    {#each [['От', from], ['Кому', to], ['CC', cc], ['BCC', bcc]] as [label, value] (label)}
      {#if value}<div>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>{/if}
    {/each}
  </dl>
  {#if bodyText}<pre>{bodyText}</pre>{:else}<p>Текстовая часть не указана.</p>{/if}
  {#if bodyHtml}<details>
      <summary>Исходный HTML письма</summary>
      <pre>{bodyHtml}</pre>
    </details>{/if}
</section>

<style>
  .message {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    margin: 16px 0;
  }
  dl {
    margin: 0 0 12px;
  }
  dl > div {
    display: flex;
    gap: 12px;
    font-size: 12px;
    margin: 5px 0;
  }
  dt {
    color: var(--v2-slate);
    min-width: 40px;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  pre {
    font: inherit;
    font-size: 13px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    line-height: 1.6;
    margin: 12px 0;
  }
  summary {
    cursor: pointer;
    color: var(--v2-slate);
    font-size: 12px;
  }
  p {
    font-size: 13px;
  }
</style>
