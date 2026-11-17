/**
 * Smoke test for the Opportunity Radar Host plugin.
 * Runs apply() against a fake Cordis context, then executes every registered
 * tool against the real local project and inspects the bundled skill provider.
 * No profile state is touched.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const bundleDir = path.join(here, '..');
const { apply, name, inject } = await import(path.join(bundleDir, 'index.js'));

const config = {
  repoPath: '/Users/joho/Documents/Codex/2026-10-13/opportunity-radar-ai-agent-github-https/work/opportunity-radar',
  appHome: '/Users/joho/Library/Application Support/Opportunity Radar',
  apiPort: '8015',
  uiPort: '3004',
  timeoutMs: 12000,
};

const tools = new Map();
let provider;
const ctx = {
  tools: {
    register(def) {
      assert.equal(typeof def.name, 'string');
      assert.equal(typeof def.description, 'string');
      assert.equal(def.parameters.type, 'object');
      assert.equal(typeof def.output.render, 'function');
      assert.equal(def.output.schema.type, 'object');
      assert.equal(typeof def.execute, 'function');
      assert.ok(!tools.has(def.name), `duplicate tool ${def.name}`);
      tools.set(def.name, def);
      return () => tools.delete(def.name);
    },
  },
  skills: {
    registerProvider(create) {
      provider = create({ signal: new AbortController().signal, invalidate() {} });
      return () => { provider = undefined; };
    },
  },
};

const STATES = ['online', 'offline', 'degraded', 'misconfigured'];

assert.equal(name, 'opportunity-radar');
assert.deepEqual(inject, ['tools', 'skills']);
apply(ctx, config);

const expected = [
  'radar_status', 'radar_search', 'radar_sources', 'radar_list', 'radar_results',
  'radar_runs', 'radar_run_detail', 'radar_provider_diagnose', 'radar_identity',
  'radar_token_status',
];
assert.deepEqual([...tools.keys()].sort(), [...expected].sort());
console.log(`PASS: ${tools.size} read-only tools registered`);

// The result schema must advertise the state the plugin can actually report.
const schema = tools.get('radar_status').output.schema;
assert.deepEqual([...schema.properties.state.enum].sort(), [...STATES].sort());
assert.equal(schema.properties.state.enum.includes('online'), true);
console.log('PASS: result schema advertises online/offline/degraded/misconfigured');

// Skill provider contract.
assert.ok(provider, 'skill provider registered');
const candidates = await provider.list();
assert.equal(candidates.length, 1);
assert.equal(candidates[0].name, 'opportunity-radar');
assert.equal(candidates[0].provider, 'opportunity-radar');
assert.equal(candidates[0].rank, 600);
assert.equal(candidates[0].invocation.modelInvocable, true);
const skill = await provider.get(candidates[0]);
assert.equal(skill.name, 'opportunity-radar');
assert.match(skill.content, /radar_status/);
assert.match(skill.content, /radar_list/);
assert.match(skill.content, /付费运行/);
console.log(`PASS: bundled skill "${skill.name}" (${skill.content.length} chars)`);

// Manifest / locale / icon / detail sanity.
const manifest = JSON.parse(await readFile(path.join(bundleDir, 'package.json'), 'utf8'));
assert.equal(manifest.name, '@local/opportunity-radar');
assert.equal(manifest.dsh.bundle.patch, './cordis.patch.yml');
assert.equal(manifest.exports['./client'], './client.js');
assert.ok(manifest.exports['./icon']);
assert.ok(manifest.files.includes('client.js'), 'client.js must ship');
assert.ok(manifest.files.includes('docs'), 'docs must ship');
for (const loc of ['en', 'zh']) {
  const meta = JSON.parse(await readFile(path.join(bundleDir, 'locale', `${loc}.json`), 'utf8')).meta;
  assert.ok(meta.title && meta.description, `${loc} meta missing`);
  assert.match(meta.detail, /^docs\/DETAIL[^/]*\.md$/, `${loc} meta.detail path`);
  const detail = await readFile(path.join(bundleDir, meta.detail), 'utf8');
  const imageLine = detail.trim().split('\n').filter((line) => line.trim().length);
  assert.equal(imageLine.length, 1, `${loc} detail must be exactly one image line`);
  const imageName = /!\[[^\]]+\]\(([^)]+)\)/.exec(imageLine[0]);
  assert.ok(imageName, `${loc} detail must reference an image`);
  const image = await readFile(path.join(bundleDir, 'docs', imageName[1]), 'utf8');
  assert.match(image, /^<svg[^>]*width="640"[^>]*height="300"/, `${loc} preview must be 640x300`);
  assert.ok(Buffer.byteLength(image) < 1024 * 1024, 'preview must stay under 1 MiB');
}
const icon = await readFile(path.join(bundleDir, 'icon.svg'), 'utf8');
assert.match(icon, /^<svg[\s\S]*<\/svg>\s*$/);
assert.ok(Buffer.byteLength(icon) < 256 * 1024);
// Plugin Manager draws the surrounding tile, so the icon must not draw one.
assert.match(icon, /width="36"/);
assert.match(icon, /viewBox="0 0 36 36"/);
assert.ok(!/<rect\b/.test(icon), 'icon must not draw a background tile');
assert.ok(!/<(text|style|script|image|foreignObject)\b/.test(icon), 'icon must stay self-contained geometry');
console.log('PASS: manifest, locales, detail document, preview and icon');

// Client module must not import Harness Client packages.
const client = await readFile(path.join(bundleDir, 'client.js'), 'utf8');
assert.ok(!/require\(['"]@deepseek-ai\//.test(client), 'client must not require @deepseek-ai/*');
assert.match(client, /__ModuleLoader__/);
assert.match(client, /conversation\.composer\.dock/);
assert.match(client, /locale\.register/);
console.log('PASS: client module registers a slot entry and its own locale dictionary');

// Exercise every tool against the real local project.
const cases = [
  ['radar_status', {}],
  ['radar_sources', {}],
  ['radar_list', { limit: 100 }],
  ['radar_results', { radar_id: '00000000-0000-0000-0000-000000000000', limit: 5, status: 'strict' }],
  ['radar_runs', { limit: 5 }],
  ['radar_provider_diagnose', {}],
  ['radar_identity', {}],
  ['radar_token_status', {}],
];

const results = new Map();
for (const [toolName, args] of cases) {
  const def = tools.get(toolName);
  const value = await def.execute(args, { signal: new AbortController().signal });
  assert.equal(typeof value.ok, 'boolean');
  assert.ok(STATES.includes(value.state), `unexpected state ${value.state}`);
  assert.equal(value.command, toolName);
  assert.equal(typeof value.hint, 'string');
  assert.equal(typeof value.data, 'object');
  assert.equal(typeof value.error.code, 'string');
  assert.ok(value.duration_ms >= 0);
  const blocks = def.output.render(args, value);
  assert.ok(Array.isArray(blocks) && blocks.length === 1 && blocks[0].type === 'text');
  assert.ok(!JSON.stringify(value).includes('"token"'), 'must never emit plaintext token');
  // A real token is the prefix followed by 16+ body characters; the masked
  // form (or_agent_W***iQng) must remain the only occurrence.
  assert.ok(!/or_agent_[A-Za-z0-9_-]{16,}/.test(JSON.stringify(value)), 'must never emit the token value');
  results.set(toolName, value);
  console.log(`\n--- ${toolName}: state=${value.state} ok=${value.ok} exit=${value.exit_code} http=${value.http_status}`);
  console.log(`    error=${value.error.code || '-'} | ${value.error.message.slice(0, 90)}`);
  console.log(`    checks=${JSON.stringify(value.checks)}`);
  console.log(`    hint=${value.hint.slice(0, 220)}...`);
}

// When the service is ready, the fuller payloads must survive compaction.
const status = results.get('radar_status');
const sources = results.get('radar_sources');
const list = results.get('radar_list');
if (status.state === 'online') {
  assert.equal(sources.ok, true, 'radar_sources should succeed while online');
  const platformCount = Number(sources.data.platform_count) || 0;
  assert.ok(Array.isArray(sources.data.items), 'sources must return items');
  // The catalog has more rows than platform_count (namespaces vs platforms), but
  // the old compactor collapsed everything to 3; every row must now survive.
  assert.ok(sources.data.items.length > 3, `sources must not collapse to 3 items (got ${sources.data.items.length})`);
  assert.ok(sources.data.items.length >= platformCount, `sources must keep every catalog row (${sources.data.items.length} < ${platformCount})`);
  assert.ok(!sources.data.truncated, 'sources should fit without truncation');

  assert.equal(list.ok, true, 'radar_list should succeed while online');
  assert.ok(Array.isArray(list.data.items), 'radar_list must return items');
  const total = Number(list.data.page && list.data.page.total);
  assert.ok(Number.isFinite(total) && total >= 0, 'radar_list must report page.total');
  if (total > 0) {
    const first = list.data.items[0];
    assert.ok(first && (first.id || first.radar_id), 'radar rows must carry an id');
    if (total <= 100) {
      assert.equal(list.data.items.length, total, `radar_list must keep all ${total} rows, not ${list.data.items.length}`);
      assert.ok(!list.data.truncated, 'radar_list list view must fit without truncation');
      assert.ok(!('source_config' in first), 'radar_list rows should omit per-radar source configuration');
      const single = await tools.get('radar_list').execute({ radar_id: first.id }, {});
      assert.equal(single.ok, true, 'reading one radar by id must succeed');
      assert.ok(single.data.radar && Object.keys(single.data.radar).length > 5, 'single radar detail must stay complete');
      // `or results --status` rejects hiring_signal, so it must route over HTTP.
      const hs = await tools.get('radar_results').execute({ radar_id: first.id, status: 'hiring_signal', limit: 1 }, {});
      assert.notEqual(hs.error.code, 'OR_OUTPUT_INVALID', 'hiring_signal must not reach the CLI argument parser');
      assert.equal(hs.state, 'online');
    }
    console.log(`\nPASS: radar_list total=${total}, sources kept ${sources.data.items.length}/${platformCount} platforms`);
  }
}

// The paid search tool must refuse without an explicit confirm, spending nothing.
const search = await tools.get('radar_search').execute({ query: '单片机' }, { signal: new AbortController().signal });
assert.equal(search.ok, false);
assert.equal(search.error.code, 'CONFIRM_REQUIRED');
assert.equal(search.state, 'online', 'a rejected request must not be reported as a configuration fault');
assert.ok(!/or_agent_[A-Za-z0-9_-]{16,}/.test(JSON.stringify(search)), 'search must never emit the token');
console.log('PASS: radar_search refuses without confirm=true (no collection, no charge)');

// A concrete run detail is readable, and the diagnose tool tallies platforms.
const diagnose = results.get('radar_provider_diagnose');
if (diagnose && diagnose.ok) {
  assert.ok(diagnose.data.tally && typeof diagnose.data.tally.total === 'number', 'diagnose must tally platforms');
  console.log(`PASS: radar_provider_diagnose ready=${diagnose.data.tally.ready} missing_price=${diagnose.data.tally.missing_price} missing_key=${diagnose.data.tally.missing_key}`);
}
const runsResult = results.get('radar_runs');
const firstRun = runsResult && Array.isArray(runsResult.data.items) ? runsResult.data.items[0] : null;
if (firstRun && firstRun.id) {
  const detail = await tools.get('radar_run_detail').execute({ run_id: firstRun.id }, { signal: new AbortController().signal });
  assert.equal(detail.ok, true, 'radar_run_detail must succeed for an existing run');
  assert.equal(String(detail.data.run && detail.data.run.id), String(firstRun.id), 'run detail must return the requested run');
  console.log(`PASS: radar_run_detail read run ${String(firstRun.id).slice(0, 8)}… (status=${detail.data.run.status})`);
}

console.log('\nALL SMOKE CHECKS PASSED');