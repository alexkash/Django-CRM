<script>
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import ActForm from '$lib/v2/components/billing/ActForm.svelte';
  import '$lib/v2/components/billing/billing.css';
  /** @type {{data:any,form?:any}} */ let { data, form } = $props();
</script>

<PageHeader title="Новий акт"
  >{#snippet actions()}<a class="v2-btn" href={resolve('/invoices/acts')}>До списку актів</a
    >{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  {#if data.invoice}<ActForm {data} {form} />{:else}<div class="billing">
      <section>
        <h2>Оберіть виписаний український рахунок</h2>
        <form method="GET">
          <label
            ><span>Рахунок</span><select name="invoice" required
              >{#each data.invoices as invoice}<option value={invoice.id}
                  >{invoice.issuer_name || invoice.issuer?.legal_name} · {invoice.invoice_number} · {invoice
                    .account.name}</option
                >{/each}</select
            ></label
          ><button
            class="v2-btn v2-btn-primary"
            style="margin-top:15px"
            disabled={!data.invoices.length}>Перейти до акта</button
          >
        </form>
        {#if !data.invoices.length}<p class="b-muted" style="margin-top:15px">
            Немає виписаних українських рахунків із залишком послуг для закриття.
          </p>{/if}
      </section>
    </div>{/if}
</div>
