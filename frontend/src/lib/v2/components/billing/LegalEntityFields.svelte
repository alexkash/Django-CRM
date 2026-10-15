<script>
  import './billing.css';
  /** @type {{values:any}} */
  let { values = $bindable({}) } = $props();
  const fields = [
    ['legal_name', 'Повне найменування'],
    ['registration_code', 'ЄДРПОУ / РНОКПП'],
    ['address', 'Юридична адреса'],
    ['city', 'Місце складання (місто)'],
    ['phone', 'Телефон'],
    ['email', 'Email'],
    ['vat_registration_number', 'ІПН платника ПДВ'],
    ['signer_name', 'ПІБ підписанта'],
    ['signer_title', 'Посада підписанта'],
    ['tax_system_text', 'Система оподаткування (текст для документа)'],
    ['invoice_prefix', 'Префікс рахунків'],
    ['act_prefix', 'Префікс актів']
  ];
</script>

<div class="b-grid">
  <label
    ><span>Тип компанії</span><select name="entity_type" bind:value={values.entity_type}
      ><option value="FOP">ФОП</option><option value="LLC">ТОВ</option></select
    ></label
  >
  <label
    ><span>ПДВ</span><select
      name="vat_status"
      bind:value={values.vat_status}
      onchange={() => {
        if (values.vat_status === 'NON_PAYER') values.default_vat_rate = '0';
      }}
      ><option value="NON_PAYER">Без ПДВ</option><option value="PAYER">Платник ПДВ</option></select
    ></label
  >
  <label
    ><span>Ставка ПДВ за замовчуванням, %</span><input
      name="default_vat_rate"
      inputmode="decimal"
      bind:value={values.default_vat_rate}
      readonly={values.vat_status === 'NON_PAYER'}
    /></label
  >
  <label
    ><span>Використання</span><select name="active" bind:value={values.active}
      ><option value={true}>Активна</option><option value={false}>Архівна</option></select
    ></label
  >
  {#each fields as [key, label]}
    <label class:b-wide={key === 'address' || key === 'tax_system_text'}
      ><span>{label}</span><input
        name={key}
        bind:value={values[key]}
        required={key === 'legal_name' || key === 'registration_code'}
      /></label
    >
  {/each}
</div>
