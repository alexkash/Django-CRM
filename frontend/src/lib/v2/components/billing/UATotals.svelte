<script>
  /** @type {{totals:any, status?:string, rate?:string}} */
  let { totals, status = 'NON_PAYER', rate = '0' } = $props();
  const money = (value) =>
    new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
      Number(value ?? 0)
    );
</script>

<dl class="b-totals">
  <div>
    <dt>Вартість без ПДВ</dt>
    <dd>{money(totals?.subtotal)} грн</dd>
  </div>
  {#if status === 'PAYER'}<div>
      <dt>ПДВ {rate}%</dt>
      <dd>{money(totals?.tax_amount)} грн</dd>
    </div>{/if}
  <div class="b-grand">
    <dt>{status === 'PAYER' ? 'Всього з ПДВ' : 'Всього, без ПДВ'}</dt>
    <dd>{money(totals?.total_amount)} грн</dd>
  </div>
</dl>
