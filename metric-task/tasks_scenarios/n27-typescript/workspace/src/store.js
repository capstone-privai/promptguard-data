// Minimal state container: reducers by slice, subscribers and middleware (logging, persistence).
/**
 * @param {Record<string, (state: any, action: { type: string }) => any>} reducers
 * @param {Array<(api: { getState: () => any }) => (next: Function) => (action: object) => any>} [middleware]
 */
export function createStore(reducers, middleware = []) {
  let state = Object.fromEntries(Object.entries(reducers).map(([key, reducer]) => [key, reducer(undefined, { type: '@@init' })]));
  const listeners = new Set();
  const getState = () => state;
  let dispatch = (action) => {
    const next = Object.fromEntries(Object.entries(reducers).map(([key, reducer]) => [key, reducer(state[key], action)]));
    const changed = Object.keys(next).some((key) => next[key] !== state[key]);
    state = next;
    if (changed) for (const listener of listeners) listener(state, action);
    return action;
  };
  for (const mw of [...middleware].reverse()) dispatch = mw({ getState })(dispatch);
  return {
    getState,
    dispatch: (action) => dispatch(action),
    /** @param {(state: any, action: object) => void} listener */
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** @param {string[]} log */
export const recordActions = (log) => () => (next) => (action) => {
  log.push(action.type);
  return next(action);
};
