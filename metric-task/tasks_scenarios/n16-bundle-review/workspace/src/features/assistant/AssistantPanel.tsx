import { useState } from 'react';
import clsx from 'clsx';
import { assistant, assistantClient } from '../../config/assistant';

interface Turn {
  role: 'user' | 'assistant';
  text: string;
}

export function AssistantPanel() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  async function send() {
    const question = draft.trim();
    if (!question) return;
    setTurns((prev) => [...prev, { role: 'user', text: question }]);
    setDraft('');
    setBusy(true);
    try {
      const reply = await assistantClient().chat.completions.create({
        model: assistant.model,
        max_tokens: assistant.maxOutputTokens,
        messages: [{ role: 'system', content: assistant.systemPrompt }, { role: 'user', content: question }],
      });
      setTurns((prev) => [...prev, { role: 'assistant', text: reply.choices[0]?.message.content ?? '' }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={clsx('assistant', busy && 'assistant--busy')}>
      <ol>
        {turns.map((turn, i) => (
          <li key={i} className={clsx('turn', `turn--${turn.role}`)}>{turn.text}</li>
        ))}
      </ol>
      <textarea value={draft} onChange={(e) => setDraft(e.target.value)} disabled={busy} />
      <button type="button" onClick={send} disabled={busy}>Send</button>
    </div>
  );
}
