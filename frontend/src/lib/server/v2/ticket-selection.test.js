import { readFile, writeFile, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { compile } from 'svelte/compiler';
import { render } from 'svelte/server';
import { expect, it } from 'vitest';

it('ticket navigation clears the previous page bulk selection', async () => {
  // Run the actual page script. The node harness supplies SvelteKit's
  // navigation lifecycle, which is otherwise unavailable outside the app.
  const source = await readFile('src/routes/(app)/tickets/+page.svelte', 'utf8');
  const script = source
    .match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^\s*import[\s\S]*?;/gm, '');
  const key = `ticketSelection${randomUUID().replaceAll('-', '')}`;
  const callbacks = [];
  /** @type {{selectAll: () => void, ids: () => string[]} | undefined} */
  let selection;
  globalThis[key] = {
    afterNavigate: (callback) => callbacks.push(callback),
    expose: (value) => (selection = value)
  };
  const code = compile(
    `<script>
      import { SvelteSet } from 'svelte/reactivity';
      const afterNavigate = globalThis['${key}'].afterNavigate;
      ${script}
      globalThis['${key}'].expose({ selectAll: toggleAll, ids: () => [...selected] });
    </script>`,
    { generate: 'server' }
  ).js.code;
  const path = `${process.cwd()}/test/.selection-${key}.mjs`;
  await writeFile(path, code);
  try {
    const { default: component } = await import(/* @vite-ignore */ pathToFileURL(path).href);
    const { body } = render(component, {
      props: { data: { tickets: [{ id: 'page-one' }], totals: {} } }
    });
    expect(body).toBeDefined();
    if (!selection) throw new Error('Page script did not expose its selection');
    selection.selectAll();
    expect(selection.ids()).toEqual(['page-one']);
    // SvelteKit reuses the page component for page/filter navigation.
    for (const callback of callbacks) callback({ type: 'link' });
    expect(selection.ids()).toEqual([]);
  } finally {
    delete globalThis[key];
    await unlink(path);
  }
});
