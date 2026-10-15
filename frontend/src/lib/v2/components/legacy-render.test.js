import { readFile, writeFile, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { compile } from 'svelte/compiler';
import { render } from 'svelte/server';
import { expect, it } from 'vitest';

async function rendered(name, props) {
  const source = await readFile(new URL(`./${name}.svelte`, import.meta.url), 'utf8');
  const code = compile(source, { generate: 'server' }).js.code;
  const path = `${process.cwd()}/test/.legacy-${randomUUID()}.mjs`;
  await writeFile(path, code);
  try {
    const { default: component } = await import(/* @vite-ignore */ pathToFileURL(path).href);
    return render(component, { props }).body;
  } finally {
    await unlink(path);
  }
}

it('email markup is escaped text, without executable elements or remote images', async () => {
  const html = await rendered('LegacyMessage', {
    bodyText: 'Plain message',
    bodyHtml:
      '<script>alert(1)</script><img src="https://tracker.test/pixel"><iframe src="https://evil.test"></iframe><form action="javascript:alert(1)">x</form>'
  });
  expect(html).toContain('Plain message');
  expect(html).toContain('&lt;script');
  expect(html).not.toMatch(/<(script|img|iframe|form)\b/i);
});

it('original fields show unknown amounts and exact long values with no financial actions', async () => {
  const phone = '12345;'.repeat(30);
  const html = await rendered('LegacyFields', {
    fields: { total_amount: null, phone_work: phone, email_address: 'old@example.com' }
  });
  expect(html).toContain('Не указано');
  expect(html).toContain(phone);
  expect(html).toContain('old@example.com');
  expect(html).not.toContain('Send a reminder');
  expect(html).not.toContain('Pay');
});

it('unclassified stages ask for classification without claiming closure', async () => {
  const html = await rendered('StageMeter', {
    code: 'SOURCE',
    name: 'Original label',
    kind: 'unknown',
    steps: []
  });
  expect(html).toContain('Needs classification');
  expect(html).not.toContain('Closed');
});

it('adaptations expose exact original contact values', async () => {
  const html = await rendered('LegacyAdaptations', {
    adaptations: [
      { field: 'email', reason: 'duplicate_email', original: 'duplicate@example.com' },
      { field: 'phone', reason: 'original_phone_preserved', original: '12345;'.repeat(20) }
    ]
  });
  expect(html).toContain('duplicate@example.com');
  expect(html).toContain('12345;'.repeat(20));
  expect(html).not.toContain('[object Object]');
});
