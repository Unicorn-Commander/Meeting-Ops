import { lazy, useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { config } from '../config';
import SettingsLayout, {
  SaveStatus,
} from '../components/settings/SettingsLayout';
import {
  ALL_SECTIONS,
  APPLIANCE_ONLY_SECTIONS,
  HostCapabilities,
  SettingsProvider,
  SettingsState,
  SETTINGS_STORAGE_KEY,
  loadStoredSettings,
} from '../components/settings/SettingsContext';

const AudioSettings = lazy(() => import('../components/settings/AudioSettings'));
const AISettings = lazy(() => import('../components/settings/AISettings'));
const VocabularySettings = lazy(
  () => import('../components/settings/VocabularySettings')
);
const ProvidersSettings = lazy(
  () => import('../components/settings/ProvidersSettings')
);
const NetworkSettings = lazy(
  () => import('../components/settings/NetworkSettings')
);
const WifiSettings = lazy(() => import('../components/settings/WifiSettings'));
const PerformanceSettings = lazy(
  () => import('../components/settings/PerformanceSettings')
);

export default function SettingsEnhanced() {
  const [activeSection, setActiveSection] = useState('providers');
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
            vadEnabled: backendSettings.enableVAD || prev.vadEnabled,
            vadThreshold:
              backendSettings.vadThreshold * 1000 || prev.vadThreshold,
            enableAI: backendSettings.enableLiveAI || prev.enableAI,
            summaryFormat: prev.summaryFormat,
            autoGenerateActions:
              backendSettings.enableAutoSummary || prev.autoGenerateActions,
            speakerDiarization:
              backendSettings.enableSpeakerDiarization || prev.speakerDiarization,
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
        setMicVolume(backendSettings.microphoneVolume || 75);
      } catch (error) {
        console.log('Backend settings not available, using local storage');
      }
    })();
  }, []);

  const sections = hostCaps.local_audio
    ? ALL_SECTIONS
    : ALL_SECTIONS.filter((s) => !APPLIANCE_ONLY_SECTIONS.has(s.id));

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
      vadThreshold: settings.vadThreshold / 1000,
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
      case 'network':
        return <NetworkSettings />;
      case 'wifi':
        return <WifiSettings />;
      case 'performance':
        return <PerformanceSettings />;
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
