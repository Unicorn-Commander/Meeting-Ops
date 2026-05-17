import { AlertCircle } from 'lucide-react';
import { SectionProps, useSettingsContext } from './SettingsContext';

export default function AuthentikSettings(_props: SectionProps) {
  const { settings, setSettings } = useSettingsContext();

  return (
    <div className="space-y-6">
      <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4 mb-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-yellow-400 mt-0.5" />
          <div>
            <p className="text-sm text-yellow-200 font-medium">
              Authentik SSO Configuration
            </p>
            <p className="text-xs text-yellow-300 mt-1">
              Configure Single Sign-On with your Authentik instance for
              centralized authentication
            </p>
          </div>
        </div>
      </div>

      <div>
        <label className="flex items-center gap-3 mb-4">
          <input
            type="checkbox"
            checked={settings.authentikEnabled}
            onChange={(e) =>
              setSettings({ ...settings, authentikEnabled: e.target.checked })
            }
            className="w-4 h-4 bg-zinc-800 border-zinc-600 rounded"
          />
          <span className="text-sm text-zinc-300">
            Enable Authentik Authentication
          </span>
        </label>

        {settings.authentikEnabled && (
          <div className="space-y-4 ml-7">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Authentik URL
              </label>
              <input
                type="url"
                value={settings.authentikUrl}
                onChange={(e) =>
                  setSettings({ ...settings, authentikUrl: e.target.value })
                }
                placeholder="https://auth.yourdomain.com"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Client ID
              </label>
              <input
                type="text"
                value={settings.authentikClientId}
                onChange={(e) =>
                  setSettings({ ...settings, authentikClientId: e.target.value })
                }
                placeholder="meeting-ops"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Client Secret
              </label>
              <input
                type="password"
                value={settings.authentikClientSecret}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    authentikClientSecret: e.target.value,
                  })
                }
                placeholder="••••••••••••••••"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200 placeholder-zinc-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Redirect URI
              </label>
              <input
                type="url"
                value={settings.authentikRedirectUri}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    authentikRedirectUri: e.target.value,
                  })
                }
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-4 py-2 text-zinc-200"
              />
              <p className="text-xs text-zinc-500 mt-1">
                Add this URI to your Authentik application configuration
              </p>
            </div>

            <button
              onClick={async () => {
                try {
                  await fetch(settings.authentikUrl, { mode: 'no-cors' });
                  alert(
                    'Connection test completed — request sent to ' +
                      settings.authentikUrl
                  );
                } catch (err) {
                  alert('Connection failed: ' + (err as Error).message);
                }
              }}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-sm text-zinc-200 transition-colors"
            >
              Test Connection
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
