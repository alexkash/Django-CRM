<script>
  import { resolve } from '$app/paths';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import UATotals from '$lib/v2/components/billing/UATotals.svelte';
  import '$lib/v2/components/billing/billing.css';
  /** @type {{data:any,form?:any}} */ let { data, form } = $props();
  let act = $derived(data.act);
  let busy = $state(false);
  const submit = () => {
    busy = true;
    return async ({ update }) => {
      await update();
      busy = false;
    };
  };
  const labels = { Draft: 'Чернетка', Issued: 'Виписано', Cancelled: 'Скасовано' };
</script>

<PageHeader title={`Акт ${act.number || 'без номера'}`}
  >{#snippet sub()}{labels[act.status]} · {act.issue_date}{/snippet}{#snippet actions()}<a
      class="v2-btn"
      href={resolve('/invoices/acts')}>Усі акти</a
    >{#if act.status === 'Draft'}<a class="v2-btn" href={resolve(`/invoices/acts/${act.id}/edit`)}
        >Редагувати</a
      >
      <form method="POST" action="?/issue" use:enhance={submit}>
        <button class="v2-btn v2-btn-primary" disabled={busy}>Виписати акт</button>
      </form>{/if}{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{/if}
    <section>
      <h2>Період і підстава</h2>
      <p><a href={resolve(`/invoices/${act.invoice_id}`)}>Рахунок {act.invoice_number}</a></p>
      <p>
        Період послуг: {act.service_period_start ?? 'Не вказано'} — {act.service_period_end ??
          'Не вказано'}
      </p>
      <div class="b-actions">
        <a
          class="v2-btn"
          href={resolve(`/invoices/acts/${act.id}/pdf`) + '?variant=clean'}
          target="_blank"
          rel="noopener">PDF без сканів</a
        ><a
          class="v2-btn"
          href={resolve(`/invoices/acts/${act.id}/pdf`) + '?variant=stamped'}
          target="_blank"
          rel="noopener">PDF з підписом і печаткою</a
        >
      </div>
    </section>
    <section>
      <h2>Послуги</h2>
      <div class="b-scroll">
        <table>
          <thead
            ><tr
              ><th>Найменування</th><th>Од.</th><th>Кількість</th><th>Без ПДВ</th><th>ПДВ</th><th
                >Всього</th
              ></tr
            ></thead
          ><tbody
            >{#each act.lines as line}<tr
                ><td>{line.name}</td><td>{line.unit}</td><td>{line.quantity}</td><td
                  >{line.net_amount}</td
                ><td>{line.vat_amount}</td><td>{line.total_amount}</td></tr
              >{/each}</tbody
          >
        </table>
      </div>
      <UATotals totals={act} status={act.vat_status} rate={act.vat_rate ?? ''} />
    </section>
    {#if act.status === 'Issued'}<section>
        <details>
          <summary>Скасувати акт</summary>
          <form method="POST" action="?/cancel" use:enhance={submit}>
            <label
              ><span>Причина скасування</span><textarea name="reason" required></textarea></label
            ><button class="v2-btn" style="margin-top:12px" disabled={busy}
              >Скасувати акт і звільнити залишок</button
            >
          </form>
        </details>
      </section>{:else if act.status === 'Cancelled'}<section>
        <p>Скасовано: {act.cancellation_reason}</p>
      </section>{:else}<form method="POST" action="?/delete" use:enhance={submit}>
        <button class="v2-btn" disabled={busy}>Видалити чернетку</button>
      </form>{/if}
  </div>
</div>
