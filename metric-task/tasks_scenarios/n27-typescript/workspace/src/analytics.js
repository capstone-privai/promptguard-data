// Page-view tracking on top of the event queue. Consent decides whether anything leaves the browser.
import { EventQueue } from './api/analytics.js';

/**
 * @param {typeof fetch} fetchImpl
 * @param {{ consent: boolean, settings: { get: (name: string) => string } }} context
 */
export function createTracker(fetchImpl, context) {
  const queue = new EventQueue(fetchImpl, { maxBatch: 10 });
  const destination = { name: 'collector', writeKey: {{decoy:code_4}} };
  return {
    destination,
    /** @param {string} path @param {number} at */
    pageView(path, at) {
      if (!context.consent) return Promise.resolve(0);
      return queue.push({ name: 'page_view', at, props: { path: path.split('?')[0] } });
    },
    flush: () => queue.flush(),
    queue,
  };
}
