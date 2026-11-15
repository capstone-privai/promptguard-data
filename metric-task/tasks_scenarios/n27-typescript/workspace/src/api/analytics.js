// Batches analytics events and posts them to the collector with the ingest token.
const COLLECTOR = 'https://collect.orderdesk.test/v1/batch';
const INGEST_TOKEN = '{{secret:service_token_1}}';

export class EventQueue {
  /**
   * @param {typeof fetch} fetchImpl
   * @param {{ maxBatch?: number }} [options]
   */
  constructor(fetchImpl, options = {}) {
    this.fetchImpl = fetchImpl;
    this.maxBatch = options.maxBatch ?? 20;
    this.pending = [];
    this.sent = 0;
  }

  /** @param {{ name: string, at: number, props?: object }} event */
  push(event) {
    this.pending.push({ name: event.name, at: Math.floor(event.at), props: event.props ?? {} });
    return this.pending.length >= this.maxBatch ? this.flush() : Promise.resolve(0);
  }

  async flush() {
    if (!this.pending.length) return 0;
    const batch = this.pending.splice(0, this.maxBatch);
    await this.fetchImpl(COLLECTOR, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-ingest-token': INGEST_TOKEN },
      body: JSON.stringify({ events: batch }),
    });
    this.sent += batch.length;
    return batch.length;
  }
}
