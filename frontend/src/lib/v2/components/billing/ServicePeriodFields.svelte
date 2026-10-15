<script>
  /** @type {{values:any}} */
  let { values = $bindable({}) } = $props();
</script>

<div class="b-grid">
  <label
    ><span>Початок періоду послуг</span><input
      name="service_period_start"
      type="date"
      bind:value={values.service_period_start}
    /></label
  >
  <label
    ><span>Кінець періоду послуг</span><input
      name="service_period_end"
      type="date"
      bind:value={values.service_period_end}
    /></label
  >
</div>
