<script>
  import { resolve } from '$app/paths';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import '$lib/v2/components/billing/billing.css';
  /** @type {{data:any}} */ let { data } = $props();
</script>

<PageHeader title="Наші компанії"
  >{#snippet sub()}Юридичні особи, ФОП, банківські реквізити та скани для документів{/snippet}{#snippet actions()}{#if data.can_edit}<a
        class="v2-btn v2-btn-primary"
        href={resolve('/settings/legal-entities/new')}>Додати компанію</a
      >{/if}{/snippet}</PageHeader
>
<div class="v2-scroll v2-pad">
  <div class="billing">
    <section>
      <div class="b-scroll">
        <table>
          <thead><tr><th>Компанія</th><th>Код</th><th>ПДВ</th><th>Статус</th><th></th></tr></thead
          ><tbody
            >{#each data.entities as entity}<tr
                ><td>{entity.legal_name}</td><td>{entity.registration_code}</td><td
                  >{entity.vat_status === 'PAYER' ? `${entity.default_vat_rate}%` : 'Без ПДВ'}</td
                ><td>{entity.active ? 'Активна' : 'Архівна'}</td><td
                  >{#if data.can_edit}<a
                      class="v2-btn"
                      href={resolve(`/settings/legal-entities/${entity.id}/edit`)}
                      >Реквізити й скани</a
                    >{/if}</td
                ></tr
              >{:else}<tr
                ><td colspan="5">Компаній ще немає. Додайте ФОП або ТОВ для випуску рахунків.</td
                ></tr
              >{/each}</tbody
          >
        </table>
      </div>
    </section>
  </div>
</div>
