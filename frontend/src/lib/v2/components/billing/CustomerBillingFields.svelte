<script>
  import { CUSTOMER_BILLING_FIELDS, PARTY_LABELS } from '$lib/v2/billing.js';
  import './billing.css';
  /** @type {{values:any, prefix?:string}} */
  let { values = $bindable({}), prefix = '' } = $props();
</script>

<div class="b-grid">
  {#each CUSTOMER_BILLING_FIELDS as field}
    <label class:b-wide={field === 'legal_address' || field === 'tax_system_text'}>
      <span>{PARTY_LABELS[field]}</span>
      <input name={prefix + field} bind:value={values[field]} placeholder="З картки клієнта" />
    </label>
  {/each}
</div>
