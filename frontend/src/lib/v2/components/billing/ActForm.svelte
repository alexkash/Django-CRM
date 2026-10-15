<script>
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import { todayIn } from '$lib/v2/dates.js';
  import { actPayload } from '$lib/v2/billing.js';
  import ServicePeriodFields from './ServicePeriodFields.svelte';
  import ActLinesEditor from './ActLinesEditor.svelte';
  import './billing.css';
  /** @type {{data:any,form?:any,initial?:any}} */
  let { data, form, initial = null } = $props();
  let values = $state(
    untrack(() => ({
      invoice_id: data.invoice.id,
      issue_date: initial?.issue_date ?? todayIn(data.org?.timezone ?? 'UTC'),
      service_period_start:
        initial?.service_period_start ?? data.invoice.service_period_start ?? '',
      service_period_end: initial?.service_period_end ?? data.invoice.service_period_end ?? ''
    }))
  );
  let quantities = $state(
    untrack(() =>
      Object.fromEntries((initial?.lines ?? []).map((line) => [line.source_line_id, line.quantity]))
    )
  );
  let busy = $state(false);
  let lines = $derived(
    (data.invoice.closure?.lines ?? []).filter(
      (line) => Number(line.remaining_quantity) > 0 || quantities[line.source_line_id]
    )
  );
  let payload = $derived.by(() => {
    try {
      return actPayload({
        ...values,
        lines: Object.entries(quantities)
          .filter(([, q]) => String(q ?? '').trim())
          .map(([source_line_id, quantity]) => ({ source_line_id, quantity }))
      });
    } catch {
      return null;
    }
  });
</script>

<div class="billing">
  {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{/if}
  <form
    method="POST"
    action="?/save"
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
      <h2>Рахунок {data.invoice.invoice_number}</h2>
      <p>{data.invoice.issuer?.legal_name}</p>
      <label style="max-width:250px;margin:15px 0"
        ><span>Дата акта</span><input type="date" bind:value={values.issue_date} required /></label
      ><ServicePeriodFields bind:values />
    </section>
    <section>
      <h2>Частина послуг для закриття</h2>
      <p class="b-muted" style="margin-bottom:15px">
        Задайте кількість для потрібних позицій. Порожні поля не включаються в акт.
      </p>
      <ActLinesEditor {lines} bind:quantities />
    </section>
    <button class="v2-btn v2-btn-primary" disabled={busy || !payload?.lines.length}
      >{busy ? 'Збереження…' : 'Зберегти чернетку акта'}</button
    >
  </form>
</div>
