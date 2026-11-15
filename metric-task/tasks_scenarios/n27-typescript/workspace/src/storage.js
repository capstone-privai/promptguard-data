// Namespaced key-value storage with optional expiry. Uses an in-memory map outside the browser.
const memory = new Map();

/**
 * @param {string} namespace
 * @param {{ now?: () => number }} [options]
 */
export function createStorage(namespace, options = {}) {
  const now = options.now ?? (() => Date.now() / 1000);
  const key = (name) => `${namespace}:${name}`;
  return {
    /** @param {string} name @param {string} value @param {number} [expiresAt] */
    write(name, value, expiresAt) {
      memory.set(key(name), JSON.stringify({ value, expiresAt: expiresAt ?? null }));
    },
    /** @param {string} name */
    read(name) {
      const raw = memory.get(key(name));
      if (raw === undefined) return null;
      const entry = JSON.parse(raw);
      if (entry.expiresAt !== null && entry.expiresAt <= now()) {
        memory.delete(key(name));
        return null;
      }
      return entry.value;
    },
    clear() {
      for (const k of [...memory.keys()]) if (k.startsWith(`${namespace}:`)) memory.delete(k);
    },
    size() {
      return [...memory.keys()].filter((k) => k.startsWith(`${namespace}:`)).length;
    },
  };
}
