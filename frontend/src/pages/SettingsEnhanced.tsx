import { lazy, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { config } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { useOrg } from '../contexts/OrgContext';
import { isAdminRole } from '../utils/roles';
import SettingsLayout from '../components/settings/SettingsLayout';
import type { SaveStatus } from '../components/settings/SettingsLayout';
import {
  ALL_SECTIONS,
  APPLIANCE_ONLY_SECTIONS,
  SettingsProvider,
  SETTINGS_STORAGE_KEY,
  loadStoredSettings,
} from '../components/settings/SettingsContext';
import type {
  HostCapabilities,
  SettingsState,
} from '../components/settings/SettingsContext';

// Same admin shape as the router — superuser OR per-org admin. Used to
// hide adminOnly settings sections from regular users (Aaron: "hide it
// entirely, don't show with a disabled gray state").

const AudioSettings = lazy(() => import('../components/settings/AudioSettings'));
const AISettings = lazy(() => import('../components/settings/AISettings'));
const VocabularySettings = lazy(
  () => import('../components/settings/VocabularySettings')
);
const ProvidersSettings = lazy(
  () => import('../components/settings/ProvidersSettings')
);
const InBrowserAISettings = lazy(
  () => import('../components/settings/InBrowserAISettings')
);
const NetworkSettings = lazy(
  () => import('../components/settings/NetworkSettings')
);
const WifiSettings = lazy(() => import('../components/settings/WifiSettings'));
const PerformanceSettings = lazy(
  () => import('../components/settings/PerformanceSettings')
);
const PersonalAccessTokens = lazy(
  () => import('../components/settings/PersonalAccessTokens')
);

export default function SettingsEnhanced() {
  const { user } = useAuth();
  const { activeOrganization } = useOrg();
  const location = useLocation();
  const isAdmin = isAdminRole(activeOrganization?.role, user?.is_superuser);
  // Default to 'audio' (the user-preferences section everyone can see).
  // We re-select to a visible section in a useEffect below in case
  // adminOnly filtering kicks out the current pick after a hostCaps /
  // role flip mid-life.
  const [activeSection, setActiveSection] = useState(isAdmin ? 'providers' : 'audio');
  const [hostCaps, setHostCaps] = useState<HostCapabilities>({
    local_audio: true,
    npu: false,
    build: 'unknown',
  });
  const [settings, setSettings] = useState<SettingsState>(loadStoredSettings);
  const [micVolume, setMicVolume] = useState(75);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/system/capabilities');
        if (res.ok) setHostCaps(await res.json());
      } catch {
        /* leave defaults */
      }
    })();
  }, []);

  useEffect(() => {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    (async () => {
      try {
        const response = await fetch(`${config.apiUrl}/api/simple/settings`);
        if (!response.ok) return;
        const backendSettings = await response.json();
        setSettings((prev: SettingsState) => {
          const mapped: SettingsState = {
            ...prev,
            defaultDevice: backendSettings.defaultMicrophone || prev.defaultDevice,
            sampleRate: prev.sampleRate,
            transcriptionModel:
              backendSettings.transcriptionModel || prev.transcriptionModel,
            liveTranscription: backendSettings.enableLiveAI !== false,
            vadEnabled: backendSettings.enableVAD ?? prev.vadEnabled,
            // vadThreshold is a 0.0-1.0 sensitivity float (matches backend storage)
            vadThreshold: backendSettings.vadThreshold ?? prev.vadThreshold,
            enableAI: backendSettings.enableLiveAI ?? prev.enableAI,
            summaryFormat: prev.summaryFormat,
            autoGenerateActions:
              backendSettings.enableAutoSummary ?? prev.autoGenerateActions,
            speakerDiarization:
              backendSettings.enableSpeakerDiarization ?? prev.speakerDiarization,
            maxSpeakers: backendSettings.maxSpeakers || prev.maxSpeakers,
            llmModel: backendSettings.aiModel || prev.llmModel,
            llmProvider: backendSettings.aiProvider || prev.llmProvider,
            hostname: backendSettings.hostname || prev.hostname,
            ipMode: backendSettings.ipMode || prev.ipMode,
            npuEnabled: backendSettings.npuEnabled !== false,
            npuPowerMode: backendSettings.npuPowerMode || prev.npuPowerMode,
          };
          localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(mapped));
          return mapped;
        });
        setMicVolume(backendSettings.microphoneVolume ?? 75);
      } catch (error) {
        console.log('Backend settings not available, using local storage');
      }
    })();
  }, []);

  // Three filters applied in order:
  //   1. Appliance-only sections are dropped in cloud builds (existing).
  //   2. adminOnly sections are dropped entirely for non-admin users
  //      (Aaron's "hide it entirely" directive).
  // Memoized so the layout doesn't re-render the sidebar list each
  // unrelated re-render.
  const sections = useMemo(() => {
    let list = hostCaps.local_audio
      ? ALL_SECTIONS
      : ALL_SECTIONS.filter((s) => !APPLIANCE_ONLY_SECTIONS.has(s.id));
    if (!isAdmin) {
      list = list.filter((s) => !s.adminOnly);
    }
    return list;
  }, [hostCaps.local_audio, isAdmin]);

  // Deep-link bridge: `#audio-devices` (used by the dashboard's
  // first-run onboarding checklist) selects the audio section. The
  // SettingsLayout sidebar can also be cued by `?section=<id>`.
  useEffect(() => {
    const hash = location.hash.replace(/^#/, '').toLowerCase();
    const queryParams = new URLSearchParams(location.search);
    const explicit = queryParams.get('section');
    let target: string | null = null;
    if (explicit) {
      target = explicit;
    } else if (hash) {
      if (hash === 'audio-devices' || hash.startsWith('audio')) target = 'audio';
    }
    if (target && target !== activeSection) {
      setActiveSection(target);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.hash, location.search]);

  // If the active section vanishes (admin/role flip, hostCaps load),
  // re-anchor to the first visible section so the panel doesn't show
  // an "Select a setting category" empty state mid-life.
  useEffect(() => {
    if (sections.length === 0) return;
    if (!sections.some((s) => s.id === activeSection)) {
      setActiveSection(sections[0].id);
    }
  }, [sections, activeSection]);

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus('idle');

    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));

    const backendSettings = {
      defaultMicrophone: settings.defaultDevice,
      microphoneVolume: micVolume,
      transcriptionModel: settings.transcriptionModel,
      enableLiveAI: settings.liveTranscription,
      enableVAD: settings.vadEnabled,
      vadThreshold: settings.vadThreshold,
      enableSpeakerDiarization: settings.speakerDiarization,
      maxSpeakers: settings.maxSpeakers,
      aiModel: settings.llmModel,
      aiProvider: settings.llmProvider,
      enableAutoSummary: settings.autoGenerateActions,
      hostname: settings.hostname,
      ipMode: settings.ipMode,
      ipAddress: settings.ipAddress,
      gateway: settings.gateway,
      dns1: settings.dns1,
      dns2: settings.dns2,
      wifiEnabled: settings.wifiEnabled,
      wifiSSID: settings.wifiSSID,
      wifiPassword: settings.wifiPassword,
      npuEnabled: settings.npuEnabled,
      npuPowerMode: settings.npuPowerMode,
      defaultExportFormat: settings.defaultExportFormat,
      includeTimestamps: settings.includeTimestamps,
      includeSpeakerLabels: settings.includeSpeakerLabels,
    };

    try {
      const response = await fetch(`${config.apiUrl}/api/simple/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(backendSettings),
      });

      if (response.ok) {
        setSaveStatus('success');
        setTimeout(() => setSaveStatus('idle'), 3000);
      } else {
        throw new Error('Backend not available');
      }
    } catch (error) {
      setSaveStatus('backend-pending');
      setTimeout(() => setSaveStatus('idle'), 5000);
    } finally {
      setSaving(false);
    }
  };

  const renderActive = () => {
    switch (activeSection) {
      case 'audio':
        return <AudioSettings />;
      case 'ai':
        return <AISettings />;
      case 'vocabulary':
        return <VocabularySettings />;
      case 'providers':
        return <ProvidersSettings />;
      case 'in-browser-ai':
        return <InBrowserAISettings />;
      case 'network':
        return <NetworkSettings />;
      case 'wifi':
        return <WifiSettings />;
      case 'performance':
        return <PerformanceSettings />;
      case 'personal-access-tokens':
        return <PersonalAccessTokens />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black text-zinc-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
          <p className="text-zinc-400">
            Configure Meeting-Ops hardware and software
          </p>
        </div>

        <SettingsProvider
          value={{
            settings,
            setSettings,
            micVolume,
            setMicVolume,
            hostCaps,
          }}
        >
          <SettingsLayout
            sections={sections}
            activeSection={activeSection}
            onSectionChange={setActiveSection}
            saving={saving}
            saveStatus={saveStatus}
            onSave={handleSave}
            showSave={activeSection !== 'personal-access-tokens'}
          >
            {renderActive()}
          </SettingsLayout>
        </SettingsProvider>

        <div className="mt-4 text-sm text-zinc-500">
          Local agent templates and model configuration:
          <a
            href="#/admin/agents"
            className="text-fuchsia-400 hover:text-fuchsia-300 ml-1 inline-flex items-center gap-1"
          >
            Agent Settings <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
    </div>
  );
}
