<script>
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import LegalEntityFields from '$lib/v2/components/billing/LegalEntityFields.svelte';
  /** @type {{data:any,form?:any}} */ let { form } = $props();
  let values = $state(
    untrack(() => ({
      entity_type: 'FOP',
      legal_name: '',
      registration_code: '',
      vat_status: 'NON_PAYER',
      default_vat_rate: '0',
      active: true,
      invoice_prefix: 'РХ-',
      act_prefix: 'АКТ-',
      ...(form?.values ?? {})
    }))
  );
</script>

<PageHeader title="Нова компанія"
  >{#snippet actions()}<a class="v2-btn" href={resolve('/settings/legal-entities')}>До списку</a
    >{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{/if}
    <form method="POST" action="?/save" use:enhance>
      <section><LegalEntityFields bind:values /></section>
      <button class="v2-btn v2-btn-primary">Зберегти й додати банківський рахунок</button>
    </form>
  </div>
</div>
