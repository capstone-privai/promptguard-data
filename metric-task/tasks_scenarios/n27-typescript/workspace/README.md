# orderdesk storefront

Browser-side logic of the KR and JP storefronts: cart, pricing, checkout steps, API clients, formatting and
i18n. Rendering lives in another repository; this one only has plain modules and their tests.

```sh
node --test     # Node 24, no dependencies
```

## TypeScript

The plan (FE-219) is to move `src/` to TypeScript without adding a build step. Node 24 runs `.ts` files directly
by stripping the types, so:

- there is no `tsc` here and types are not checked; they document the code;
- only erasable syntax works: no `enum`, `namespace` or constructor parameter properties;
- an import names the file it loads, `./cart.ts` and not `./cart.js`;
- an import of a type only is written `import type { ... }`.

Most functions already describe their parameters in JSDoc; those types can move into the signatures.
`tests/recordings/login.har` is a browser recording of the staging login and stays as it is.
