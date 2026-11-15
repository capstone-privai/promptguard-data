import { AssistantPanel } from '../features/assistant/AssistantPanel';

export function AssistantPage() {
  return (
    <section>
      <h1>Order assistant</h1>
      <p>Ask about delivery dates, refunds or an order you placed.</p>
      <AssistantPanel />
    </section>
  );
}
