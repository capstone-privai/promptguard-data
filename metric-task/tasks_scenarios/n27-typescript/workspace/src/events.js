export class Emitter {
  constructor() {
    this.handlers = new Map();
  }

  /** @param {string} name @param {(payload: unknown) => void} handler */
  on(name, handler) {
    if (!this.handlers.has(name)) this.handlers.set(name, []);
    this.handlers.get(name).push(handler);
    return () => this.off(name, handler);
  }

  /** @param {string} name @param {(payload: unknown) => void} handler */
  once(name, handler) {
    const off = this.on(name, (payload) => {
      off();
      handler(payload);
    });
    return off;
  }

  /** @param {string} name @param {(payload: unknown) => void} handler */
  off(name, handler) {
    this.handlers.set(name, (this.handlers.get(name) ?? []).filter((h) => h !== handler));
  }

  /** @param {string} name @param {unknown} [payload] */
  emit(name, payload) {
    const handlers = [...(this.handlers.get(name) ?? [])];
    for (const handler of handlers) handler(payload);
    return handlers.length;
  }
}
