import { config } from '../config';
import type {
  AgentActionResult,
} from '../types/agent-actions.types';

type HeaderMap = Record<string, string>;

async function postJson<T>(path: string, body: unknown, headers: HeaderMap): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function confirmAgentAction(
  confirmationToken: string,
  headers: HeaderMap,
): Promise<AgentActionResult> {
  return postJson<AgentActionResult>(
    '/api/agent-actions/confirm',
    { confirmation_token: confirmationToken },
    headers,
  );
}

export async function cancelAgentAction(
  confirmationToken: string,
  headers: HeaderMap,
): Promise<AgentActionResult> {
  return postJson<AgentActionResult>(
    '/api/agent-actions/cancel',
    { confirmation_token: confirmationToken },
    headers,
  );
}

