# ledgershop-web

Storefront for LedgerShop (React 18, Vite 5, TypeScript).

```sh
npm install
npm run dev        # http://localhost:5173
npm test           # vitest
npm run build      # dist/
```

## Bundle size

CI builds every pull request with `--metafile` and commits the esbuild metafiles under `reports/bundle/`:
`main.json` is the current main branch and `pr.json` is the pull request head. Compare them with

```sh
npm run bundle:report
```

The budget for each output file is `bundleBudget` in `package.json`. A metafile lists every input that ended up in
an output (`outputs[...].inputs`, with `bytesInOutput`) and, under `inputs[...].imports`, which import statement
(`original`) pulled each file in.
