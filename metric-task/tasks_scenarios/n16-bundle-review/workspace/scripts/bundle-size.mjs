#!/usr/bin/env node
// Compare two esbuild metafiles (the CI "bundle" job writes them) and enforce package.json bundleBudget.
// Usage: node scripts/bundle-size.mjs <base metafile> <head metafile>
import { readFileSync } from 'node:fs';

const [basePath, headPath] = process.argv.slice(2);
if (!basePath || !headPath) {
  console.error('usage: node scripts/bundle-size.mjs <base metafile> <head metafile>');
  process.exit(2);
}

const read = (path) => JSON.parse(readFileSync(path, 'utf8'));
const budget = read('package.json').bundleBudget ?? {};
const base = read(basePath).outputs;
const head = read(headPath).outputs;
const kb = (bytes) => `${(bytes / 1000).toFixed(1)} kB`;

let failed = false;
for (const name of Object.keys(head).sort()) {
  const before = base[name]?.bytes ?? 0;
  const after = head[name].bytes;
  const change = before ? `${(((after - before) / before) * 100).toFixed(1)}%` : 'new';
  const limit = budget[name];
  const status = limit && after > limit ? 'OVER BUDGET' : 'ok';
  failed ||= status !== 'ok';
  console.log(`${name}  ${kb(before)} -> ${kb(after)}  (${change})  budget ${limit ? kb(limit) : '-'}  ${status}`);
}
process.exit(failed ? 1 : 0);
