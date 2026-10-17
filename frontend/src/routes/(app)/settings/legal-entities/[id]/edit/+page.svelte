<script>
  import { untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import LegalEntityFields from '$lib/v2/components/billing/LegalEntityFields.svelte';
  /** @type {{data:any,form?:any}} */ let { data, form } = $props();
  let values = $state(untrack(() => ({ ...data.entity, ...(form?.values ?? {}) })));
  let newBank = $derived(form?.bank_values && !form.bank_id ? form.bank_values : {});
  const scans = [
    ['logo', 'Логотип'],
    ['signature', 'Підпис'],
    ['stamp', 'Печатка']
  ];
</script>

<PageHeader title={data.entity.legal_name}
  >{#snippet actions()}<a class="v2-btn" href={resolve('/settings/legal-entities')}>Наші компанії</a
    >{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    {#if form?.error}<div class="b-error" role="alert">{form.error}</div>{:else if form?.saved}<p
        role="status"
        style="margin-bottom:15px"
      >
        Зміни збережено.
      </p>{/if}
    <form method="POST" action="?/save" use:enhance>
      <section>
        <h2>Реквізити компанії</h2>
        <LegalEntityFields bind:values />
        <div class="b-actions">
          <button class="v2-btn v2-btn-primary">Зберегти реквізити</button>
        </div>
      </section>
    </form>
    <section>
      <h2>Банківські рахунки</h2>
      {#each data.banks as bank}
        {@const draftBank =
          form?.bank_id === bank.id && form.bank_values ? { ...bank, ...form.bank_values } : bank}
        <form method="POST" action="?/bank" use:enhance style="margin-bottom:22px">
          <input type="hidden" name="bank_id" value={bank.id} />
          <div class="b-grid">
            <label><span>IBAN</span><input name="iban" value={draftBank.iban} required /></label
            ><label
              ><span>Банк</span><input
                name="bank_name"
                value={draftBank.bank_name}
                required
              /></label
            ><label><span>МФО</span><input name="mfo" value={draftBank.mfo} /></label><label
              ><span>Статус рахунку</span><select name="active" value={String(draftBank.active)}
                ><option value="true">Активний</option><option value="false">Архівний</option
                ></select
              ></label
            >
          </div>
          <button class="v2-btn" style="margin-top:10px">Зберегти рахунок</button>
        </form>{/each}
      <details open={!data.banks.length || (form?.bank_values && !form.bank_id)}>
        <summary>Додати банківський рахунок</summary>
        <form method="POST" action="?/bank" use:enhance>
          <input type="hidden" name="active" value={String(newBank.active ?? true)} />
          <div class="b-grid">
            <label
              ><span>Новий IBAN</span><input
                name="iban"
                value={newBank.iban ?? ''}
                required
              /></label
            ><label
              ><span>Назва банку</span><input
                name="bank_name"
                value={newBank.bank_name ?? ''}
                required
              /></label
            ><label><span>МФО</span><input name="mfo" value={newBank.mfo ?? ''} /></label>
          </div>
          <button class="v2-btn" style="margin-top:12px">Додати рахунок</button>
        </form>
      </details>
    </section>
    <section>
      <h2>Логотип і скани для друку</h2>
      <p class="b-muted">PNG або JPEG до 2 MiB. Для прозорого фону використовуйте PNG.</p>
      <div class="b-grid">
        {#each scans as [kind, label]}<div>
            <h3>{label}</h3>
            {#if data.entity[kind + '_sha256']}<img
                class="b-scan"
                src={resolve(`/api/billing/legal-entities/${data.entity.id}/scans/${kind}`) +
                  `?v=${data.entity[kind + '_sha256']}`}
                alt={label}
              />{/if}
            <form method="POST" action="?/scan" enctype="multipart/form-data" use:enhance>
              <input type="hidden" name="kind" value={kind} /><label
                ><span>Файл: {label.toLowerCase()}</span><input
                  name="file"
                  type="file"
                  accept="image/png,image/jpeg"
                  required
                /></label
              ><button class="v2-btn" style="margin-top:10px"
                >{kind === 'logo'
                  ? 'Завантажити логотип'
                  : kind === 'stamp'
                    ? 'Завантажити печатку'
                    : 'Завантажити підпис'}</button
              >
            </form>
            {#if data.entity[kind + '_sha256']}<form
                method="POST"
                action="?/deleteScan"
                use:enhance
              >
                <input type="hidden" name="kind" value={kind} /><button
                  class="v2-btn"
                  style="margin-top:10px"
                  >{kind === 'logo' ? 'Видалити логотип' : 'Видалити поточний скан'}</button
                >
              </form>{/if}
          </div>{/each}
      </div>
    </section>
  </div>
</div>
