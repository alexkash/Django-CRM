<script>
  /** @type {{lines:any[], quantities:any}} */
  let { lines = [], quantities = $bindable({}) } = $props();
</script>

<div class="b-scroll">
  <table class="b-lines">
    <thead
      ><tr
        ><th>Послуга</th><th>Од.</th><th>Залишок кількості</th><th>Включити в акт</th><th></th></tr
      ></thead
    ><tbody
      >{#each lines as line}<tr
          ><td>{line.name}</td><td>{line.unit}</td><td>{line.remaining_quantity}</td><td
            ><input
              aria-label={`Кількість: ${line.name}`}
              inputmode="decimal"
              bind:value={quantities[line.source_line_id]}
              placeholder="Не включати"
            /></td
          ><td
            ><button
              type="button"
              class="v2-btn"
              onclick={() => (quantities[line.source_line_id] = line.remaining_quantity)}
              >Весь залишок</button
            ></td
          ></tr
        >{/each}</tbody
    >
  </table>
</div>
