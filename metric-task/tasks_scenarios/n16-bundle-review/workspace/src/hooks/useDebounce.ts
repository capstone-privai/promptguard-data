import { useEffect, useMemo, useState } from 'react';
import debounce from 'lodash-es/debounce';

export function useDebounce<T>(value: T, waitMs: number): T {
  const [settled, setSettled] = useState(value);
  const update = useMemo(() => debounce((next: T) => setSettled(next), waitMs), [waitMs]);

  useEffect(() => {
    update(value);
    return () => update.cancel();
  }, [value, update]);

  return settled;
}
