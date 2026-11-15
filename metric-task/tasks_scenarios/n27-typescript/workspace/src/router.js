// Path patterns such as /orders/:id and /c/:category/* matched in declaration order.
/** @param {string} pattern */
export function compile(pattern) {
  const names = [];
  const source = pattern
    .split('/')
    .map((part) => {
      if (part === '*') return '(.*)';
      if (part.startsWith(':')) {
        names.push(part.slice(1));
        return '([^/]+)';
      }
      return part.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
    })
    .join('/');
  return { names, regex: new RegExp(`^${source}/?$`) };
}

/**
 * @param {{ pattern: string, name: string }[]} routes
 * @param {string} path
 */
export function match(routes, path) {
  const [pathname, search = ''] = path.split('?');
  for (const route of routes) {
    const { names, regex } = compile(route.pattern);
    const found = regex.exec(pathname);
    if (found) {
      const params = Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(found[i + 1])]));
      return { name: route.name, params, query: Object.fromEntries(new URLSearchParams(search)) };
    }
  }
  return null;
}
