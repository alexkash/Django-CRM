<script>
  /** @type {{values:any,entities:any[],banks:any[],accounts:any[],contacts:any[],onissuerchange?:()=>void}} */
  let {
    values = $bindable({}),
    entities = [],
    banks = [],
    accounts = [],
    contacts = [],
    onissuerchange = () => {}
  } = $props();
  let contactOptions = $derived(
    contacts.filter((c) => !c.account_id || c.account_id === values.account_id)
  );
</script>

<div class="b-grid">
  <label
    ><span>Наша компанія</span><select
      bind:value={values.issuer_id}
      required
      onchange={onissuerchange}
      ><option value="">Оберіть компанію</option>{#each entities as entity}<option
          value={entity.id}
          disabled={!entity.active}>{entity.legal_name}{entity.active ? '' : ' (архів)'}</option
        >{/each}</select
    ></label
  >
  <label
    ><span>Банківський рахунок</span><select bind:value={values.bank_account_id} required
      ><option value="">Оберіть IBAN</option>{#each banks as bank}<option
          value={bank.id}
          disabled={!bank.active}>{bank.iban} · {bank.bank_name}</option
        >{/each}</select
    ></label
  >
  <label
    ><span>Одержувач</span><select
      bind:value={values.account_id}
      required
      onchange={() => {
        values.contact_id = '';
        values.draft_parties = { customer: {}, payer: {} };
      }}
      ><option value="">Оберіть клієнта</option>{#each accounts as account}<option
          value={account.id}>{account.name}</option
        >{/each}</select
    ></label
  >
  <label
    ><span>Контакт клієнта</span><select bind:value={values.contact_id} required
      ><option value="">Оберіть контакт</option>{#each contactOptions as contact}<option
          value={contact.id}>{contact.name}</option
        >{/each}</select
    ></label
  >
  <label class="b-wide"
    ><span>Платник</span><select
      bind:value={values.payer_id}
      onchange={() => {
        values.draft_parties.payer = {};
      }}
      ><option value="">Той самий, що одержувач</option>{#each accounts as account}<option
          value={account.id}>{account.name}</option
        >{/each}</select
    ></label
  >
</div>
