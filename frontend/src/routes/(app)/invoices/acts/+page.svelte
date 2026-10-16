<script>
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import '$lib/v2/components/billing/billing.css';
  /** @type {{data:any}} */ let { data } = $props();
  const labels = { Draft: 'Чернетка', Issued: 'Виписано', Cancelled: 'Скасовано' };
</script>

<PageHeader title="Акти наданих послуг"
  >{#snippet actions()}<a class="v2-btn" href={resolve('/invoices')}>Рахунки</a><a
      class="v2-btn v2-btn-primary"
      href={resolve('/invoices/acts/new')}>Новий акт</a
    >{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    <section>
      <form method="GET" class="b-grid">
        <label
          ><span>Наша компанія</span><select name="issuer" value={data.filters.issuer ?? ''}
            ><option value="">Усі компанії</option>{#each data.entities ?? [] as entity}<option
                value={entity.id}>{entity.legal_name}</option
              >{/each}</select
          ></label
        >
        <label
          ><span>Статус</span><select name="status" value={data.filters.status ?? ''}
            ><option value="">Усі</option>{#each Object.entries(labels) as [value, label]}<option
                {value}>{label}</option
              >{/each}</select
          ></label
        ><label
          ><span>Від початку періоду</span><input
            type="date"
            name="period_start"
            value={data.filters.period_start ?? ''}
          /></label
        ><label
          ><span>До кінця періоду</span><input
            type="date"
            name="period_end"
            value={data.filters.period_end ?? ''}
          /></label
        >{#if data.filters.account}<input
            type="hidden"
            name="account"
            value={data.filters.account}
          />{/if}{#if data.filters.invoice}<input
            type="hidden"
            name="invoice"
            value={data.filters.invoice}
          />{/if}<button class="v2-btn">Застосувати</button>
      </form>
    </section>
    <section>
      <div class="b-scroll">
        <table>
          <thead
            ><tr><th>Акт</th><th>Рахунок</th><th>Період</th><th>Статус</th><th>Сума, грн</th></tr
            ></thead
          ><tbody
            >{#each data.acts.results as act}<tr
                ><td
                  ><a href={resolve(`/invoices/acts/${act.id}`)}>{act.number || 'Чернетка'}</a>
                  <p class="b-muted">{act.issuer_name}</p></td
                ><td><a href={resolve(`/invoices/${act.invoice_id}`)}>{act.invoice_number}</a></td
                ><td>{act.service_period_start ?? '—'} — {act.service_period_end ?? '—'}</td><td
                  >{labels[act.status] ?? act.status}</td
                ><td>{act.total_amount}</td></tr
              >{:else}<tr><td colspan="5">Актів за цими умовами немає.</td></tr>{/each}</tbody
          >
        </table>
      </div>
      <p class="b-muted" style="margin-top:14px">Знайдено: {data.acts.count}</p>
      <div class="b-actions">
        {#if data.acts.previous}<a
            class="v2-btn"
            href={'?' + new URL(data.acts.previous).searchParams}>Попередня сторінка</a
          >{/if}{#if data.acts.next}<a
            class="v2-btn"
            href={'?' + new URL(data.acts.next).searchParams}>Наступна сторінка</a
          >{/if}
      </div>
    </section>
  </div>
</div>
