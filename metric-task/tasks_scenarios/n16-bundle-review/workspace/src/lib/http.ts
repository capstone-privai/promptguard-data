export class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new HttpError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function getJson<T>(url: string): Promise<T> {
  return parse<T>(await fetch(url));
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parse<T>(response);
}
