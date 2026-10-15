<script>
  import UAInvoiceForm from '$lib/v2/components/billing/UAInvoiceForm.svelte';
  /** @type {{data:any,form?:any}} */ let { data, form } = $props();
</script>

<UAInvoiceForm {data} {form} initial={data.initial} action="?/save" />
