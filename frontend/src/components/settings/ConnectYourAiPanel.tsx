import { useState, type KeyboardEvent } from 'react';
import { Check, Clipboard, Plug, Sparkles } from 'lucide-react';

const TOKEN_PLACEHOLDER = 'mops_pat_…';

const CONNECT_TABS = [
  { id: 'claude-code', label: 'Claude Code' },
  { id: 'claude-desktop', label: 'Claude Desktop / claude.ai' },
  { id: 'chatgpt', label: 'ChatGPT' },
  { id: 'cursor-codex', label: 'Cursor / Codex' },
] as const;

type ConnectTabId = (typeof CONNECT_TABS)[number]['id'];

/**
 * The hosted MCP URL is a public Vite setting so each ring can point at its
 * own canonical host. A same-origin fallback keeps self-hosted deployments
 * useful without baking a ring hostname into the bundle.
 */
function getHostedMcpUrl(): string {
  const configured = import.meta.env.VITE_HOSTED_MCP_URL?.trim();
  if (configured) return configured;
  if (typeof window !== 'undefined') return `${window.location.origin}/mcp`;
  return '/mcp';
}

function claudeCodeOauthCommand(url: string): string {
  return `claude mcp add --transport http meeting-ops ${url}`;
}

function claudeCodeTokenCommand(url: string): string {
  return `${claudeCodeOauthCommand(url)} \\\n  --header "Authorization: Bearer ${TOKEN_PLACEHOLDER}"`;
}

function mcpJsonSnippet(url: string, withToken: boolean): string {
  const server: {
    type: 'http';
    url: string;
    headers?: { Authorization: string };
  } = {
    type: 'http',
    url,
  };
  if (withToken) {
    server.headers = { Authorization: `Bearer ${TOKEN_PLACEHOLDER}` };
  }
  return JSON.stringify({ mcpServers: { 'meeting-ops': server } }, null, 2);
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void copy()}
      aria-label={copied ? `${label} copied` : label}
      className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-300" /> : <Clipboard className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function Snippet({ value, label }: { value: string; label: string }) {
  return (
    <div className="mt-2">
      <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-800 bg-black/30 p-3 font-mono text-xs leading-5 text-zinc-300">
        {value}
      </pre>
      <div className="mt-2">
        <CopyButton value={value} label={label} />
      </div>
    </div>
  );
}

function ClaudeCodeTab({ url }: { url: string }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm leading-6 text-zinc-300">
          Run this command. A browser window asks you to sign in, then Claude Code can use Meeting-Ops with your permissions.
        </p>
        <Snippet value={claudeCodeOauthCommand(url)} label="Copy OAuth sign-in command" />
      </div>
      <div>
        <p className="text-sm leading-6 text-zinc-300">or paste a token</p>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          Replace <code className="font-mono text-zinc-300">{TOKEN_PLACEHOLDER}</code> with the token shown once below.
        </p>
        <Snippet value={claudeCodeTokenCommand(url)} label="Copy token command" />
      </div>
    </div>
  );
}

const CLAUDE_DESKTOP_STEPS = 'Settings → Connectors → Add custom connector → URL';
const CHATGPT_STEPS = 'Settings → Connectors → Developer mode → New connector → URL';

function UrlStepsTab({ url, steps }: { url: string; steps: string }) {
  return (
    <div>
      <p className="text-sm leading-6 text-zinc-300">
        {steps}. A browser window asks you to sign in for your account.
      </p>
      <Snippet value={url} label="Copy MCP URL" />
    </div>
  );
}

function CursorCodexTab({ url }: { url: string }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm leading-6 text-zinc-300">
          Add the URL-only entry to <code className="font-mono text-zinc-200">mcp.json</code> for browser sign-in.
        </p>
        <Snippet value={mcpJsonSnippet(url, false)} label="Copy mcp.json" />
      </div>
      <div>
        <p className="text-sm leading-6 text-zinc-300">
          Or use the token-header variant when the client cannot complete browser sign-in.
        </p>
        <Snippet value={mcpJsonSnippet(url, true)} label="Copy mcp.json with token header" />
      </div>
    </div>
  );
}

function moveTab(
  event: KeyboardEvent<HTMLButtonElement>,
  current: ConnectTabId,
  setTab: (id: ConnectTabId) => void,
) {
  const index = CONNECT_TABS.findIndex((item) => item.id === current);
  if (index < 0) return;

  let next = index;
  if (event.key === 'ArrowRight') next = (index + 1) % CONNECT_TABS.length;
  else if (event.key === 'ArrowLeft') next = (index - 1 + CONNECT_TABS.length) % CONNECT_TABS.length;
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = CONNECT_TABS.length - 1;
  else return;

  event.preventDefault();
  const id = CONNECT_TABS[next].id;
  setTab(id);
  const target = document.getElementById(`connect-your-ai-tab-${id}`);
  if (target instanceof HTMLButtonElement) target.focus();
}

export default function ConnectYourAiPanel() {
  const [tab, setTab] = useState<ConnectTabId>('claude-code');
  const url = getHostedMcpUrl();
  const activePanelId = `connect-your-ai-panel-${tab}`;

  return (
    <section className="rounded-xl border border-fuchsia-500/20 bg-zinc-950/50 p-4 sm:p-5" aria-labelledby="connect-your-ai-title">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-fuchsia-500/15 text-fuchsia-300">
          <Sparkles className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-zinc-500" aria-hidden="true" />
            <h3 id="connect-your-ai-title" className="text-base font-semibold text-white">Connect your AI</h3>
          </div>
          <p className="mt-1 text-sm leading-6 text-zinc-400">
            Use Meeting-Ops from an AI client over the hosted MCP connection.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/70 p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Canonical MCP URL</p>
        <div className="mt-1.5 flex items-start gap-2">
          <code className="min-w-0 flex-1 break-all font-mono text-sm text-fuchsia-200">{url}</code>
          <CopyButton value={url} label="Copy MCP URL" />
        </div>
        <p className="mt-2 text-xs text-zinc-500">This address comes from the public configuration for the current ring.</p>
      </div>

      <div
        role="tablist"
        aria-label="Connect your AI clients"
        className="mt-4 flex flex-wrap gap-1 border-b border-zinc-800"
      >
        {CONNECT_TABS.map((item) => {
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              id={`connect-your-ai-tab-${item.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`connect-your-ai-panel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setTab(item.id)}
              onKeyDown={(event) => moveTab(event, tab, setTab)}
              className={`-mb-px min-h-9 rounded-t-md border-b-2 px-3 py-2 text-left text-xs font-medium transition-colors ${
                selected
                  ? 'border-fuchsia-500 text-fuchsia-200'
                  : 'border-transparent text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div
        id={activePanelId}
        role="tabpanel"
        aria-labelledby={`connect-your-ai-tab-${tab}`}
        className="mt-4"
      >
        {tab === 'claude-code' && <ClaudeCodeTab url={url} />}
        {tab === 'claude-desktop' && <UrlStepsTab url={url} steps={CLAUDE_DESKTOP_STEPS} />}
        {tab === 'chatgpt' && <UrlStepsTab url={url} steps={CHATGPT_STEPS} />}
        {tab === 'cursor-codex' && <CursorCodexTab url={url} />}
      </div>

      <p className="mt-5 border-t border-zinc-800 pt-4 text-sm leading-6 text-zinc-400">
        Your AI gets your permissions and nothing more; revoke any time below
      </p>
    </section>
  );
}
