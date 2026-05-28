import React, { Suspense, useMemo } from 'react';
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
} from 'lucide-react';

export type SaveStatus = 'idle' | 'success' | 'error' | 'backend-pending';

/**
 * Settings sections are bucketed into one of three groups per Aaron's
 * regrouping audit (2026-05-20 UX refactor). The pre-existing
 * 'app' / 'admin' / 'system' values are retained for compatibility
 * with any callers we missed, but the modern groups are:
 *   - 'preferences'  → per-user, mostly client-side. Visible to
 *                       everyone. Mic device, in-browser AI, theme.
 *   - 'workspace'    → per-org, admin-only. AI Providers, Custom
 *                       Vocabulary, anything that ties to the active
 *                       organization's shared config.
 *   - 'advanced'     → power-user / debugging / appliance plumbing.
 *                       Network, WiFi, Performance, legacy AI panel.
 */
export type SettingsCategory =
  | 'preferences'
  | 'workspace'
  | 'advanced'
  | 'app'
  | 'admin'
  | 'system';

export interface SettingsSectionMeta {
  id: string;
  title: string;
  icon: React.ElementType;
  description: string;
  category: SettingsCategory;
  /**
   * When true, the section is hidden entirely from non-admin users
   * (not shown disabled — actually omitted). Aaron's directive: "If a
   * setting is admin-only but the user isn't admin, hide it entirely
   * (don't show with a disabled gray state — that's noisy)."
   */
  adminOnly?: boolean;
}

interface SettingsLayoutProps {
  sections: SettingsSectionMeta[];
  activeSection: string;
  onSectionChange: (id: string) => void;
  children: React.ReactNode;
  saving: boolean;
  saveStatus: SaveStatus;
  onSave: () => void;
  showSave?: boolean;
}

function LoadingShell() {
  return (
    <div className="flex items-center justify-center py-16 text-zinc-500">
      <RefreshCw className="w-5 h-5 animate-spin mr-2" />
      <span className="text-sm">Loading settings panel...</span>
    </div>
  );
}

function EmptyShell() {
  return (
    <div className="flex items-center justify-center h-64 text-zinc-500">
      <div className="text-center">
        <SettingsIcon className="w-16 h-16 mx-auto mb-4 text-zinc-700" />
        <p>Select a setting category</p>
      </div>
    </div>
  );
}

export default function SettingsLayout({
  sections,
  activeSection,
  onSectionChange,
  children,
  saving,
  saveStatus,
  onSave,
  showSave = true,
}: SettingsLayoutProps) {
  // Group sections by the new categories first; map old categories
  // ('app' → preferences, 'admin' → workspace, 'system' → advanced) so
  // any callers that haven't migrated still render under the right
  // heading. Empty groups are filtered out in the render below.
  const groupedSections = useMemo(() => {
    const buckets: Record<string, SettingsSectionMeta[]> = {
      'Your preferences': [],
      'Workspace setup': [],
      'Advanced': [],
    };
    for (const s of sections) {
      if (s.category === 'preferences' || s.category === 'app') {
        buckets['Your preferences'].push(s);
      } else if (s.category === 'workspace' || s.category === 'admin') {
        buckets['Workspace setup'].push(s);
      } else {
        // 'advanced' + 'system' + anything unknown lands in Advanced
        buckets['Advanced'].push(s);
      }
    }
    return buckets;
  }, [sections]);

  const active = sections.find((s) => s.id === activeSection);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      <div className="lg:col-span-1">
        <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-2">
          {Object.entries(groupedSections).map(([category, items]) =>
            items.length === 0 ? null : (
              <div key={category} className="mb-4">
                <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wider px-3 py-2">
                  {category}
                </div>
                {items.map((section) => {
                  const Icon = section.icon;
                  return (
                    <button
                      key={section.id}
                      onClick={() => onSectionChange(section.id)}
                      className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left transition-colors ${
                        activeSection === section.id
                          ? 'bg-zinc-800 text-white'
                          : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
                      }`}
                    >
                      <Icon className="w-5 h-5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium">{section.title}</div>
                        <div className="text-xs text-zinc-500 truncate">
                          {section.description}
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 shrink-0" />
                    </button>
                  );
                })}
              </div>
            )
          )}
        </div>
      </div>

      <div className="lg:col-span-3">
        <div className="rounded-2xl bg-zinc-900/70 border border-zinc-800 p-6">
          <h2 className="text-xl font-semibold text-white mb-6">
            {active?.title}
          </h2>

          <Suspense fallback={<LoadingShell />}>
            {active ? children : <EmptyShell />}
          </Suspense>

          {showSave && (
          <div className="mt-8 pt-6 border-t border-zinc-800">
            <div className="flex items-center gap-3">
              <button
                onClick={onSave}
                disabled={saving}
                className="px-6 py-3 bg-gradient-to-r from-fuchsia-600 to-indigo-600 hover:from-fuchsia-500 hover:to-indigo-500 text-white rounded-xl font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
              >
                {saving ? (
                  <>
                    <RefreshCw className="w-5 h-5 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="w-5 h-5" />
                    Save Changes
                  </>
                )}
              </button>

              {saveStatus === 'success' && (
                <div className="flex items-center gap-2 text-green-400">
                  <CheckCircle className="w-5 h-5" />
                  <span className="text-sm">Settings saved successfully</span>
                </div>
              )}

              {saveStatus === 'error' && (
                <div className="flex items-center gap-2 text-red-400">
                  <AlertCircle className="w-5 h-5" />
                  <span className="text-sm">Failed to save settings</span>
                </div>
              )}

              {saveStatus === 'backend-pending' && (
                <div className="flex items-center gap-2 text-yellow-400">
                  <AlertCircle className="w-5 h-5" />
                  <span className="text-sm">
                    Settings saved locally (backend integration pending)
                  </span>
                </div>
              )}
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  );
}
