<script>
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { todayIn } from '$lib/v2/dates.js';
  import { previewUATotals, uaInvoicePayload, addCatalogLine } from '$lib/v2/billing.js';
  import DocumentPartyFields from './DocumentPartyFields.svelte';
  import CustomerBillingFields from './CustomerBillingFields.svelte';
  import ServicePeriodFields from './ServicePeriodFields.svelte';
  import UATotals from './UATotals.svelte';
  import './billing.css';
  /** @type {{data:any,form?:any,initial?:any,action?:string}} */
  let { data, form, initial = null, action = '?format=ua&/create' } = $props();
  let values = $state(
    untrack(() => ({
      ...{
        invoice_title: '',
        issuer_id: '',
        bank_account_id: '',
        account_id: '',
        contact_id: '',
        payer_id: '',
        issue_date: todayIn(data.org?.timezone ?? 'UTC'),
        payment_terms: 'NET_30',
        contract_number: '',
        contract_date: '',
        service_period_start: '',
        service_period_end: '',
        place_of_issue: '',
        order_reference: '',
        tax_rate: '0',
        notes: '',
        terms: '',
        line_items: [
          { name: '', description: '', quantity: '1', unit_price: '0.00', unit: 'послуга' }
        ]
      },
      ...(initial ?? {}),
      ...(form?.values ?? {}),
      draft_parties: {
        customer: { ...((form?.values ?? initial)?.draft_parties?.customer ?? {}) },
        payer: { ...((form?.values ?? initial)?.draft_parties?.payer ?? {}) }
      }
    }))
  );
  let selectedProduct = $state('');
  let busy = $state(false);
  let entity = $derived(data.entities.find((row) => row.id === values.issuer_id));
  let banks = $derived(data.banks_by_entity[values.issuer_id] ?? []);
  let totals = $derived.by(() => {
    try {
      return previewUATotals(values.line_items, values.tax_rate, entity?.vat_status ?? 'NON_PAYER');
    } catch {
      return null;
    }
  });
  let payload = $derived.by(() => {
    try {
      return uaInvoicePayload(values);
    } catch {
      return null;
    }
  });
  $effect(() => {
    if (entity?.vat_status === 'NON_PAYER') values.tax_rate = '0';
  });
  function selectIssuer() {
    values.bank_account_id = '';
    values.tax_rate = String(entity?.default_vat_rate ?? '0');
    values.place_of_issue = entity?.city ?? '';
  }
  function addProduct() {
    const product = data.products.find((row) => row.id === selectedProduct);
    if (product) values.line_items = addCatalogLine(values.line_items, product);
    selectedProduct = '';
  }
</script>

<PageHeader title={initial ? 'Редагування рахунку' : 'Новий рахунок (Україна)'}>
  {#snippet actions()}<a
      class="v2-btn"
      href={resolve(initial ? `/invoices/${initial.id}` : '/invoices')}>Скасувати</a
    >{/snippet}
</PageHeader>
<div class="v2-scroll v2-pad">
  <div class="billing">
    {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{/if}
    {#if !data.entities.some((row) => row.active)}<section>
        <p>Спочатку додайте нашу компанію та її банківський рахунок.</p>
        <a class="v2-btn" href={resolve('/settings/legal-entities')}>Наші компанії</a>
      </section>{/if}
    <form
      method="POST"
      {action}
      use:enhance={() => {
        busy = true;
        return async ({ update }) => {
          await update();
          busy = false;
        };
      }}
    >
      <input type="hidden" name="payload" value={payload ? JSON.stringify(payload) : ''} />
      <section>
        <h2>Сторони документа</h2>
        <DocumentPartyFields
          bind:values
          entities={data.entities}
          {banks}
          accounts={data.accounts}
          contacts={data.contacts}
          onissuerchange={selectIssuer}
        />
        <details>
          <summary>Уточнити реквізити одержувача для цього документа</summary>
          <p class="b-muted">Порожні поля використовують реквізити з картки клієнта.</p>
          <CustomerBillingFields bind:values={values.draft_parties.customer} />
        </details>
        {#if values.payer_id}<details>
            <summary>Уточнити реквізити платника</summary><CustomerBillingFields
              bind:values={values.draft_parties.payer}
            />
          </details>{/if}
      </section>
      <section>
        <h2>Договір і період</h2>
        <div class="b-grid">
          <label class="b-wide"
            ><span>Назва рахунку</span><input bind:value={values.invoice_title} required /></label
          >
          <label
            ><span>Дата рахунку</span><input
              type="date"
              bind:value={values.issue_date}
              required
            /></label
          >
          <label><span>Сплатити до</span><input type="date" bind:value={values.due_date} /></label>
          <label><span>Номер договору</span><input bind:value={values.contract_number} /></label
          ><label
            ><span>Дата договору</span><input
              type="date"
              bind:value={values.contract_date}
            /></label
          >
          <label><span>Місце складання</span><input bind:value={values.place_of_issue} /></label
          ><label
            ><span>Замовлення / підстава</span><input bind:value={values.order_reference} /></label
          >
        </div>
        <div style="margin-top:15px"><ServicePeriodFields bind:values /></div>
      </section>
      <section>
        <h2>Послуги та ціни без ПДВ</h2>
        <div class="b-actions">
          <select aria-label="Продукт з каталогу" bind:value={selectedProduct}
            ><option value="">Оберіть продукт</option>{#each data.products as product}<option
                value={product.id}>{product.name}</option
              >{/each}</select
          ><button class="v2-btn" type="button" onclick={addProduct} disabled={!selectedProduct}
            >Додати продукт</button
          >
        </div>
        <div class="b-scroll">
          <table class="b-lines">
            <thead
              ><tr
                ><th>Найменування</th><th>Од.</th><th>Кількість</th><th>Ціна без ПДВ</th><th
                ></th></tr
              ></thead
            ><tbody
              >{#each values.line_items as line, i}<tr
                  ><td
                    ><input
                      aria-label={`Найменування ${i + 1}`}
                      bind:value={line.name}
                      required
                    /><input
                      aria-label={`Опис ${i + 1}`}
                      bind:value={line.description}
                      placeholder="Опис (необов’язково)"
                    /></td
                  ><td style="width:100px"
                    ><input aria-label={`Одиниця ${i + 1}`} bind:value={line.unit} /></td
                  ><td style="width:120px"
                    ><input
                      aria-label={`Кількість ${i + 1}`}
                      inputmode="decimal"
                      bind:value={line.quantity}
                    /></td
                  ><td style="width:150px"
                    ><input
                      aria-label={`Ціна ${i + 1}`}
                      inputmode="decimal"
                      bind:value={line.unit_price}
                    /></td
                  ><td
                    ><button
                      class="v2-btn"
                      type="button"
                      aria-label={`Видалити позицію ${i + 1}`}
                      onclick={() => values.line_items.splice(i, 1)}>×</button
                    ></td
                  ></tr
                >{/each}</tbody
            >
          </table>
        </div>
        <button
          class="v2-btn"
          type="button"
          style="margin-top:12px"
          onclick={() =>
            values.line_items.push({
              name: '',
              description: '',
              quantity: '1',
              unit_price: '0.00',
              unit: 'послуга'
            })}>Додати послугу</button
        >
        <label style="max-width:180px;margin-top:16px"
          ><span>{entity?.vat_status === 'PAYER' ? 'Ставка ПДВ, %' : 'Без ПДВ'}</span><input
            bind:value={values.tax_rate}
            readonly={entity?.vat_status !== 'PAYER'}
            inputmode="decimal"
          /></label
        >
        {#if totals}<UATotals {totals} status={entity?.vat_status} rate={values.tax_rate} />{/if}
      </section>
      <section>
        <div class="b-grid">
          <label><span>Примітки</span><textarea bind:value={values.notes}></textarea></label><label
            ><span>Умови оплати</span><textarea bind:value={values.terms}></textarea></label
          >
        </div>
      </section>
      <div class="b-actions">
        <button
          class="v2-btn v2-btn-primary"
          disabled={busy ||
            !payload ||
            !values.issuer_id ||
            !values.bank_account_id ||
            !values.account_id ||
            !values.contact_id ||
            !values.invoice_title ||
            !values.line_items.length}>{busy ? 'Збереження…' : 'Зберегти чернетку'}</button
        ><span class="b-muted">Випуск і друк доступні після збереження.</span>
      </div>
    </form>
  </div>
</div>
