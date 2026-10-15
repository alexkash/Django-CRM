<script>
  import { resolve } from '$app/paths';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import UATotals from './UATotals.svelte';
  import { hasRemainingServices } from '$lib/v2/billing.js';
  import './billing.css';
  /** @type {{invoice:any,acts?:any[],form?:any}} */ let { invoice, acts = [], form } = $props();
  let busy = $state(false);
  const labels = {
    Draft: 'Чернетка',
    Sent: 'Виписано',
    Paid: 'Сплачено',
    Partially_Paid: 'Частково сплачено',
    Overdue: 'Прострочено',
    Cancelled: 'Скасовано'
  };
  const money = (value) =>
    new Intl.NumberFormat('uk-UA', { style: 'currency', currency: 'UAH' }).format(
      Number(value ?? 0)
    );
  const submit = () => {
    busy = true;
    return async ({ update }) => {
      await update();
      busy = false;
    };
  };
  let remaining = $derived(hasRemainingServices(invoice));
</script>

<PageHeader title={invoice.issued_at ? invoice.invoice_number : 'Чернетка рахунку'}
  >{#snippet sub()}{labels[invoice.status] ?? invoice.status} · {invoice.issuer_name ||
      invoice.issuer?.legal_name}{/snippet}{#snippet actions()}
    <a class="v2-btn" href={resolve('/invoices')}>Рахунки</a>
    {#if invoice.status === 'Draft'}<a class="v2-btn" href={resolve(`/invoices/${invoice.id}/edit`)}
        >Редагувати</a
      >
      <form method="POST" action="?/issue" use:enhance={submit}>
        <button class="v2-btn v2-btn-primary" disabled={busy}>Виписати рахунок</button>
      </form>{/if}
    <form method="POST" action="?/duplicate" use:enhance={submit}>
      <button class="v2-btn" disabled={busy}>Створити на основі</button>
    </form>
  {/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{/if}
    <section>
      <div class="b-stats">
        <div>
          <span class="b-muted">Оплачено</span><strong>{money(invoice.amount_paid)}</strong>
        </div>
        <div>
          <span class="b-muted">Закрито актами</span><strong
            >{money(invoice.closure?.closed_total)}</strong
          >
        </div>
        <div>
          <span class="b-muted">Залишилось закрити</span><strong
            >{money(invoice.closure?.remaining_total)}</strong
          >
        </div>
      </div>
    </section>
    <section>
      <h2>{invoice.invoice_title}</h2>
      <div class="b-grid">
        <div>
          <strong>Виконавець</strong>
          <p>{invoice.parties?.seller?.legal_name || invoice.issuer?.legal_name}</p>
          <p>{invoice.parties?.bank?.iban || invoice.bank_account?.iban}</p>
        </div>
        <div>
          <strong>Одержувач</strong>
          <p>{invoice.parties?.customer?.legal_name || invoice.account_name}</p>
          {#if invoice.parties?.payer}<p class="b-muted">
              Платник: {invoice.parties.payer.legal_name}
            </p>{/if}
        </div>
      </div>
      <p style="margin-top:15px">
        Дата: {invoice.issue_date} · Сплатити до: {invoice.due_date || 'Не вказано'}
      </p>
      <p>
        Договір: {invoice.contract_number || 'Не вказано'}
        {invoice.contract_date ? `від ${invoice.contract_date}` : ''}
      </p>
      <p>
        Період послуг: {invoice.service_period_start || 'Не вказано'} — {invoice.service_period_end ||
          'Не вказано'}
      </p>
      <div class="b-actions">
        <a
          class="v2-btn"
          href={resolve(`/invoices/${invoice.id}/pdf`) + '?variant=clean'}
          target="_blank"
          rel="noopener">PDF без сканів</a
        ><a
          class="v2-btn"
          href={resolve(`/invoices/${invoice.id}/pdf`) + '?variant=stamped'}
          target="_blank"
          rel="noopener">PDF з підписом і печаткою</a
        >
      </div>
    </section>
    <section>
      <div class="b-scroll">
        <table>
          <thead
            ><tr
              ><th>Послуга</th><th>Од.</th><th>Кількість</th><th>Ціна без ПДВ</th><th
                >Сума без ПДВ</th
              ></tr
            ></thead
          ><tbody
            >{#each invoice.line_items as line}<tr
                ><td>{line.name || line.description}</td><td>{line.unit}</td><td>{line.quantity}</td
                ><td>{line.unit_price}</td><td>{line.net_amount}</td></tr
              >{/each}</tbody
          >
        </table>
      </div>
      <UATotals totals={invoice} status={invoice.vat_status} rate={invoice.tax_rate} />
    </section>
    <section>
      <h2>Акти до рахунку</h2>
      <div class="b-actions">
        {#if invoice.issued_at && invoice.status !== 'Cancelled' && remaining}<a
            class="v2-btn v2-btn-primary"
            href={resolve('/invoices/acts/new') + `?invoice=${invoice.id}`}
            >Створити частковий акт</a
          >{/if}<a class="v2-btn" href={resolve('/invoices/acts') + `?invoice=${invoice.id}`}
          >Усі акти рахунку</a
        >
      </div>
      <table>
        <thead><tr><th>Акт</th><th>Період</th><th>Статус</th><th>Сума</th></tr></thead><tbody
          >{#each acts as act}<tr
              ><td><a href={resolve(`/invoices/acts/${act.id}`)}>{act.number || 'Чернетка'}</a></td
              ><td>{act.service_period_start || '—'} — {act.service_period_end || '—'}</td><td
                >{{ Draft: 'Чернетка', Issued: 'Виписано', Cancelled: 'Скасовано' }[act.status]}</td
              ><td>{money(act.total_amount)}</td></tr
            >{:else}<tr><td colspan="4">Актів ще немає.</td></tr>{/each}</tbody
        >
      </table>
    </section>
    {#if invoice.issued_at && invoice.status !== 'Cancelled' && Number(invoice.amount_due) > 0}<section
      >
        <h2>Облік оплати</h2>
        <p class="b-muted">Залишилось сплатити: {money(invoice.amount_due)}</p>
        <form method="POST" action="?/markPaid" use:enhance={submit}>
          <div class="b-grid">
            <label
              ><span>Сума оплати (порожньо — весь борг)</span><input
                name="amount"
                inputmode="decimal"
              /></label
            ><label><span>Номер платежу</span><input name="reference_number" /></label>
          </div>
          <button class="v2-btn" style="margin-top:12px" disabled={busy}>Записати оплату</button>
        </form>
      </section>{/if}
    {#if !['Paid', 'Cancelled'].includes(invoice.status)}<section>
        <details>
          <summary>Скасувати рахунок</summary>
          <form method="POST" action="?/cancel" use:enhance={submit}>
            <button class="v2-btn" disabled={busy}>Скасувати рахунок</button>
          </form>
        </details>
      </section>{/if}
  </div>
</div>
