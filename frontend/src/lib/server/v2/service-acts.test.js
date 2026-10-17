import { describe, it, expect, vi } from 'vitest';
const apiRequest = vi.fn();
vi.mock('$lib/api-helpers.js', () => ({ apiRequest: (...args) => apiRequest(...args) }));
const event = { cookies: { get: () => 'session' } };

describe('partial service acts', () => {
  it('preserves exact fractional quantities and decimal totals', async () => {
    const { createAct, listActs } = await import('./service-acts.js');
    apiRequest.mockResolvedValueOnce({
      id: 'act',
      lines: [{ source_line_id: 'line', quantity: '0.08333333' }],
      total_amount: '1000.01'
    });
    const act = await createAct(event, {
      invoice_id: 'invoice',
      lines: [{ source_line_id: 'line', quantity: '0.08333333' }],
      org: 'forged',
      total_amount: '999'
    });
    expect(act.lines[0].quantity).toBe('0.08333333');
    expect(act.total_amount).toBe('1000.01');
    expect(apiRequest.mock.calls[0][1].body).not.toHaveProperty('org');
    expect(apiRequest.mock.calls[0][1].body).not.toHaveProperty('total_amount');
    apiRequest.mockResolvedValueOnce({ results: [], count: 0 });
    await listActs(
      event,
      new URLSearchParams({ invoice: 'invoice', status: 'Draft', period_start: '2027-01-01' })
    );
    expect(apiRequest.mock.calls[1][0]).toContain('period_start=2027-01-01');
  });
  it('keeps a stale409 rejection distinct from not-found404', async () => {
    const { issueAct } = await import('./service-acts.js');
    apiRequest.mockRejectedValue({ status: 409, message: 'remaining changed' });
    await expect(issueAct(event, 'act')).rejects.toMatchObject({ status: 409 });
  });
});
