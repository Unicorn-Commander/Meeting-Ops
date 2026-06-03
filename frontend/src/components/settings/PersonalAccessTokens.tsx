import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clipboard,
  KeyRound,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { config } from '../../config';
import { Dialog } from '../ui/Dialog';
import { track } from '../../utils/posthog';

// Hosted MCP base URL surfaced after token creation. Default to the
// current origin so a self-hosted instance gets the right URL; allow
// override via Vite env so dev builds can point at the cloud endpoint
// without copying the SPA to that domain.
const HOSTED_MCP_URL = (
  (import.meta as ImportMeta & { env: Record<string, string | undefined> })
    .env?.VITE_HOSTED_MCP_URL || `${window.location.origin}/mcp`
);

type ClientId = 'claude' | 'cursor' | 'continue' | 'zed' | 'cline' | 'stdio';

interface ClientPreset {
  id: ClientId;
  label: string;
  snippet: (pat: string) => string;
  language: 'json' | 'yaml';
}

const CLIENT_PRESETS: ClientPreset[] = [
  {
    id: 'claude',
    label: 'Claude Desktop',
    language: 'json',
    snippet: (pat) => `{
  "mcpServers": {
    "meeting-ops": {
      "url": "${HOSTED_MCP_URL}",
      "headers": {
        "Authorization": "Bearer ${pat}"
      }
    }
  }
}`,
  },
  {
    id: 'cursor',
    label: 'Cursor',
    language: 'json',
    snippet: (pat) => `// .cursor/mcp.json
{
  "mcpServers": {
    "meeting-ops": {
      "url": "${HOSTED_MCP_URL}",
      "headers": {
        "Authorization": "Bearer ${pat}"
      }
    }
  }
}`,
  },
  {
    id: 'continue',
    label: 'Continue',
    language: 'yaml',
    snippet: (pat) => `# ~/.continue/config.yaml
mcpServers:
  - name: meeting-ops
    url: ${HOSTED_MCP_URL}
    headers:
      Authorization: Bearer ${pat}`,
  },
  {
    id: 'zed',
    label: 'Zed',
    language: 'json',
    snippet: (pat) => `// ~/.config/zed/settings.json
{
  "context_servers": {
    "meeting-ops": {
      "url": "${HOSTED_MCP_URL}",
      "headers": {
        "Authorization": "Bearer ${pat}"
      }
    }
  }
}`,
  },
  {
    id: 'cline',
    label: 'Cline / Roo Code',
    language: 'json',
    snippet: (pat) => `// VS Code settings.json
{
  "mcp.servers": {
    "meeting-ops": {
      "url": "${HOSTED_MCP_URL}",
      "headers": {
        "Authorization": "Bearer ${pat}"
      }
    }
  }
}`,
  },
  {
    id: 'stdio',
    label: 'Self-hosted (stdio)',
    language: 'json',
    snippet: (pat) => `{
  "mcpServers": {
    "meeting-ops": {
      "command": "python3",
      "args": ["/path/to/UC-Meeting-Ops/mcp/meeting_ops_mcp.py"],
      "env": {
        "MEETING_OPS_URL": "${window.location.origin}",
        "MEETING_OPS_PAT": "${pat}"
      }
    }
  }
}`,
  },
];

interface PersonalAccessToken {
  id: number;
  name: string;
  token_prefix: string;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

interface CreatedToken extends PersonalAccessToken {
  plaintext: string;
}

function formatDate(value: string | null): string {
  if (!value) return 'Never';
  return new Date(value).toLocaleString();
}

export default function PersonalAccessTokens() {
  const [tokens, setTokens] = useState<PersonalAccessToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState('');
  const [created, setCreated] = useState<CreatedToken | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [activeClient, setActiveClient] = useState<ClientId>('claude');

  const activePreset = useMemo(
    () => CLIENT_PRESETS.find((p) => p.id === activeClient) ?? CLIENT_PRESETS[0],
    [activeClient],
  );

  const loadTokens = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/auth/pats`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTokens(await res.json());
    } catch (err) {
      setError(`Failed to load tokens: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTokens();
  }, []);

  const createToken = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/auth/pats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCreated(data);
      // PATs are currently unscoped (full-access); scopes_count is 0
      // until the backend grows a scopes model. Read defensively so the
      // event stays correct if/when scopes land.
      track('mcp_pat_created', {
        scopes_count: Array.isArray(data?.scopes) ? data.scopes.length : 0,
      });
      setName('');
      setDialogOpen(false);
      await loadTokens();
    } catch (err) {
      setError(`Failed to create token: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const revokeToken = async (id: number) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/auth/pats/${id}`, {
        method: 'DELETE',
      });
      if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
      await loadTokens();
    } catch (err) {
      setError(`Failed to revoke token: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const copyCreatedToken = async () => {
    if (!created?.plaintext) return;
    await navigator.clipboard.writeText(created.plaintext);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-zinc-400">
            Per-user tokens for MCP clients. Tokens are shown once and stored hashed.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-fuchsia-600 px-3 py-2 text-sm font-medium text-white hover:bg-fuchsia-500"
        >
          <Plus className="h-4 w-4" />
          New Token
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <div className="grid grid-cols-12 gap-3 border-b border-zinc-800 bg-zinc-950/70 px-4 py-3 text-xs uppercase tracking-wide text-zinc-500">
          <div className="col-span-4">Name</div>
          <div className="col-span-3">Prefix</div>
          <div className="col-span-2">Last used</div>
          <div className="col-span-2">Created</div>
          <div className="col-span-1 text-right">Action</div>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-zinc-400">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading tokens...
          </div>
        ) : tokens.length === 0 ? (
          <div className="px-4 py-8 text-sm text-zinc-500">No personal access tokens yet.</div>
        ) : (
          tokens.map((token) => (
            <div
              key={token.id}
              className="grid grid-cols-12 items-center gap-3 border-b border-zinc-800 px-4 py-3 text-sm last:border-b-0"
            >
              <div className="col-span-4 flex items-center gap-2 text-zinc-100">
                <KeyRound className="h-4 w-4 text-fuchsia-300" />
                <span className={token.revoked_at ? 'line-through text-zinc-500' : ''}>
                  {token.name}
                </span>
              </div>
              <div className="col-span-3 font-mono text-xs text-zinc-300">
                {token.token_prefix}...
              </div>
              <div className="col-span-2 text-xs text-zinc-400">{formatDate(token.last_used_at)}</div>
              <div className="col-span-2 text-xs text-zinc-400">{formatDate(token.created_at)}</div>
              <div className="col-span-1 text-right">
                {token.revoked_at ? (
                  <span className="text-xs text-zinc-500">Revoked</span>
                ) : (
                  <button
                    type="button"
                    aria-label={`Revoke ${token.name}`}
                    disabled={busy}
                    onClick={() => revokeToken(token.id)}
                    className="inline-flex rounded-md p-2 text-zinc-400 hover:bg-zinc-800 hover:text-red-300 disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* v3.19. PAT modals moved off ad-hoc `fixed inset-0` overlays
          onto Radix Dialog so they inherit focus trap, focus return,
          `role="dialog"` + `aria-modal="true"`, ESC, and click-outside.
          Audit §6. */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Content size="md" describedById="pat-create-description">
          <Dialog.Header>
            <Dialog.Title>New Personal Access Token</Dialog.Title>
            <Dialog.Close />
          </Dialog.Header>
          <div className="px-5 py-4">
            <p id="pat-create-description" className="sr-only">
              Create a new personal access token. You must give the
              token a name before creating it.
            </p>
            <label className="block text-sm text-zinc-300" htmlFor="pat-name">
              Token name
            </label>
            <input
              id="pat-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Claude Desktop on Mac"
              className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-fuchsia-500"
            />
          </div>
          <Dialog.Footer>
            <button
              type="button"
              onClick={() => setDialogOpen(false)}
              className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-200 hover:bg-zinc-800"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={createToken}
              disabled={!name.trim() || busy}
              className="inline-flex items-center gap-2 rounded-lg bg-fuchsia-600 px-3 py-2 text-sm font-medium text-white hover:bg-fuchsia-500 disabled:opacity-50"
            >
              {busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create
            </button>
          </Dialog.Footer>
        </Dialog.Content>
      </Dialog>

      <Dialog
        open={created !== null}
        onOpenChange={(open) => { if (!open) setCreated(null); }}
      >
        <Dialog.Content
          size="xl"
          describedById="pat-created-description"
          contentClassName="border-amber-500/30"
        >
          <Dialog.Header>
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
              <Dialog.Title>Copy this token now</Dialog.Title>
            </div>
            <Dialog.Close />
          </Dialog.Header>
          <div className="px-5 py-4">
            <p id="pat-created-description" className="text-sm text-zinc-400">
              You will not be able to see this plaintext token again.
            </p>
            <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900 p-3 font-mono text-sm text-zinc-100 break-all">
              {created?.plaintext}
            </div>
            {created && (
              <div className="mt-4">
                <p className="text-sm font-medium text-zinc-200">
                  Set up in your AI client
                </p>
                <p className="mt-1 text-xs text-zinc-400">
                  Pick a client; paste the snippet into its MCP config.
                  Hosted endpoint:{' '}
                  <code className="font-mono text-fuchsia-300">{HOSTED_MCP_URL}</code>
                </p>
                <div
                  className="mt-3 flex flex-wrap gap-1 border-b border-zinc-800"
                  role="tablist"
                  aria-label="AI client preset"
                >
                  {CLIENT_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      role="tab"
                      aria-selected={activeClient === preset.id}
                      onClick={() => setActiveClient(preset.id)}
                      className={`-mb-px rounded-t-md border-b-2 px-3 py-1.5 text-xs font-medium transition ${
                        activeClient === preset.id
                          ? 'border-fuchsia-500 text-fuchsia-200'
                          : 'border-transparent text-zinc-400 hover:text-zinc-200'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
                <pre className="mt-3 overflow-x-auto rounded-lg border border-zinc-800 bg-black/40 p-3 text-xs text-zinc-300">
{activePreset.snippet(created.plaintext)}
                </pre>
                <p className="mt-2 text-xs text-zinc-500">
                  Hosted MCP works without a clone — point your client at{' '}
                  <code className="font-mono">{HOSTED_MCP_URL}</code> with the
                  Bearer header above. See{' '}
                  <a
                    href="/docs/mcp-hosted"
                    target="_blank"
                    rel="noreferrer"
                    className="text-fuchsia-300 hover:underline"
                  >
                    docs/mcp-hosted.md
                  </a>{' '}
                  for the full setup guide and troubleshooting.
                </p>
              </div>
            )}
          </div>
          <Dialog.Footer>
            <button
              type="button"
              onClick={copyCreatedToken}
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-100 hover:bg-zinc-800"
            >
              {copied ? <Check className="h-4 w-4 text-emerald-300" /> : <Clipboard className="h-4 w-4" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="rounded-lg bg-fuchsia-600 px-3 py-2 text-sm font-medium text-white hover:bg-fuchsia-500"
            >
              Done
            </button>
          </Dialog.Footer>
        </Dialog.Content>
      </Dialog>
    </div>
  );
}
