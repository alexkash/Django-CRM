<script>
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import ActForm from '$lib/v2/components/billing/ActForm.svelte';
  /** @type {{data:any,form?:any}} */ let { data, form } = $props();
</script>

<PageHeader title="Редагування акта"
  >{#snippet actions()}<a class="v2-btn" href={resolve(`/invoices/acts/${data.initial.id}`)}
      >До акта</a
    >{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad"><ActForm {data} {form} initial={data.initial} /></div>
