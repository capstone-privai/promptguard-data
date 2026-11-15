// Feature flags with percentage rollouts. A user always lands in the same bucket for a flag.
/**
 * FNV-1a over flag and user, as a bucket in 0..99.
 * @param {string} flag
 * @param {string} userId
 */
export function bucket(flag, userId) {
  let hash = 0x811c9dc5;
  for (const ch of `${flag}:${userId}`) {
    hash ^= ch.codePointAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash % 100;
}

/**
 * @param {Record<string, { on: boolean, rollout?: number, stores?: string[] }>} flags
 * @param {string} name
 * @param {{ userId: string, store: string }} context
 */
export function isEnabled(flags, name, context) {
  const flag = flags[name];
  if (!flag?.on) return false;
  if (flag.stores && !flag.stores.includes(context.store)) return false;
  return bucket(name, context.userId) < (flag.rollout ?? 100);
}
