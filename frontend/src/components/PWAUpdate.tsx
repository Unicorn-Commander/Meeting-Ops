import { useEffect, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';

/**
 * Banner that surfaces a "New version available — click to reload" prompt
 * when vite-plugin-pwa's auto-update detects a fresh build on the server.
 *
 * Without this, the service worker silently caches the next deploy in the
 * background and only swaps it in when the user closes every tab and comes
 * back later. That's how Aaron got stuck on a stale bundle that still
 * referenced onnxruntime-web@1.17.0 even though the server had 1.20.1.
 *
 * The registerSW helper is provided by virtual:pwa-register at build time;
 * we import it dynamically + tolerate its absence in case PWA gets disabled.
 */
export function PWAUpdate() {
  const [needRefresh, setNeedRefresh] = useState(false);
  const [updateFn, setUpdateFn] = useState<(() => Promise<void>) | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mod = await import(/* @vite-ignore */ 'virtual:pwa-register');
        const fn = mod.registerSW({
          immediate: true,
          onNeedRefresh: () => { if (!cancelled) setNeedRefresh(true); },
        });
        if (!cancelled) {
          setUpdateFn(() => async () => {
            await fn(true);
            window.location.reload();
          });
        }
      } catch {
        // PWA disabled at build time — banner just never fires.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!needRefresh || !updateFn) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] max-w-sm rounded-xl border border-purple-500/40 bg-zinc-900/95 px-4 py-3 shadow-xl backdrop-blur-sm">
      <div className="flex items-start gap-3">
        <RefreshCw className="mt-0.5 h-5 w-5 shrink-0 text-purple-400" />
        <div className="flex-1 text-sm text-zinc-100">
          <div className="font-medium">New version available</div>
          <div className="mt-0.5 text-xs text-zinc-400">
            We just shipped an update. Reload to get the latest fixes.
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={updateFn}
              className="rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-500"
            >
              Reload now
            </button>
            <button
              type="button"
              onClick={() => setNeedRefresh(false)}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
            >
              Later
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setNeedRefresh(false)}
          className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
