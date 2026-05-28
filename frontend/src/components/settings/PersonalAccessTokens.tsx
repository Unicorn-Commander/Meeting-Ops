import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clipboard,
  KeyRound,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import { config } from '../../config';

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

      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-950 p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">New Personal Access Token</h3>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setDialogOpen(false)}
                className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
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
            <div className="mt-5 flex justify-end gap-2">
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
            </div>
          </div>
        </div>
      )}

      {created && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-xl rounded-lg border border-amber-500/30 bg-zinc-950 p-5 shadow-xl">
            <div className="mb-4 flex items-start gap-3">
              <AlertTriangle className="mt-1 h-5 w-5 shrink-0 text-amber-300" />
              <div>
                <h3 className="text-lg font-semibold text-white">Copy this token now</h3>
                <p className="mt-1 text-sm text-zinc-400">
                  You will not be able to see this plaintext token again.
                </p>
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3 font-mono text-sm text-zinc-100 break-all">
              {created.plaintext}
            </div>
            <pre className="mt-3 overflow-x-auto rounded-lg border border-zinc-800 bg-black/40 p-3 text-xs text-zinc-300">
{`{
  "mcpServers": {
    "meeting-ops": {
      "command": "python3",
      "args": ["/path/to/UC-Meeting-Ops/mcp/meeting_ops_mcp.py"],
      "env": {
        "MEETING_OPS_URL": "https://meetingops.magicunicorn.dev",
        "MEETING_OPS_PAT": "${created.plaintext}"
      }
    }
  }
}`}
            </pre>
            <div className="mt-5 flex justify-end gap-2">
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
