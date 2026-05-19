import React, { createContext, useContext } from 'react';
import {
  Brain,
  BookOpen,
  Cpu,
  Mic,
  Monitor,
  Network,
  Wifi,
} from 'lucide-react';
import type { SettingsSectionMeta } from './SettingsLayout';

export const ALL_SECTIONS: SettingsSectionMeta[] = [
  {
    id: 'audio',
    title: 'Audio & Recording',
    icon: Mic,
    description: 'Audio devices and recording configuration',
    category: 'app',
  },
  {
    id: 'ai',
    title: 'AI & Transcription',
    icon: Cpu,
    description: 'Legacy NPU model picker — superseded by AI Providers',
    category: 'app',
  },
  {
    id: 'vocabulary',
    title: 'Custom Vocabulary',
    icon: BookOpen,
    description: 'Industry terms and acronyms for transcription',
    category: 'app',
  },
  {
    id: 'providers',
    title: 'AI Providers',
    icon: Network,
    description: 'Per-service AI provider configuration',
    category: 'app',
  },
  {
    id: 'in-browser-ai',
    title: 'In-browser AI',
    icon: Brain,
    description: 'WebGPU model downloads and fallback mode',
    category: 'app',
  },
  {
    id: 'network',
    title: 'Network Configuration',
    icon: Network,
    description: 'Ethernet, IP, DNS settings',
    category: 'system',
  },
  {
    id: 'wifi',
    title: 'WiFi Settings',
    icon: Wifi,
    description: 'Wireless network configuration',
    category: 'system',
  },
  {
    id: 'performance',
    title: 'Performance & NPU',
    icon: Monitor,
    description: 'Hardware acceleration and limits',
    category: 'system',
  },
];

// Note: 'audio' was historically appliance-only because the panel
// configured PipeWire devices on the box. As of the browser-device-picker
// feature, the panel ALSO handles in-browser mic selection (which the
// cloud build needs), so we let it render in cloud mode. The PipeWire
// sub-section inside the panel guards itself on `hostCaps.local_audio`.
export const APPLIANCE_ONLY_SECTIONS = new Set([
  'ai',
  'network',
  'wifi',
  'performance',
]);


export interface HostCapabilities {
  local_audio: boolean;
  npu: boolean;
  build: 'appliance' | 'cloud' | string;
}

export type SettingsState = Record<string, any>;

export const SETTINGS_STORAGE_KEY = 'meeting-ops-settings';

export const DEFAULT_SETTINGS: SettingsState = {
  defaultDevice: 'hw:0,0',
  sampleRate: '44100',
  recordingFormat: 'wav',
  transcriptionModel: 'large-v3',
  liveTranscription: true,
  vadEnabled: true,
  vadThreshold: 0.5,
  chunkDuration: 10,

  enableAI: true,
  summaryFormat: 'executive',
  autoGenerateActions: true,
  speakerDiarization: true,
  maxSpeakers: 4,
  llmModel: 'gpt-oss-20b',
  llmProvider: 'llamacpp',

  defaultExportFormat: 'txt',
  includeTimestamps: true,
  includeSpeakerLabels: true,
  autoExport: false,
  exportPath: '/home/ucadmin/Meeting-Ops/exports',

  hostname: 'meeting-ops',
  ipMode: 'dhcp',
  ipAddress: '',
  netmask: '255.255.255.0',
  gateway: '',
  dns1: '1.1.1.1',
  dns2: '8.8.8.8',
  vlan: '',

  wifiEnabled: false,
  wifiSSID: '',
  wifiPassword: '',
  wifiSecurity: 'WPA2',

  autoStart: true,
  startOnBoot: true,
  autoUpdate: false,
  updateChannel: 'stable',
  backupEnabled: false,
  backupPath: '/backup',
  backupSchedule: 'daily',

  telemetryEnabled: false,
  logLevel: 'info',
  logRetention: 30,

  npuEnabled: true,
  npuPowerMode: 'balanced',
  cpuThreads: 4,
  memoryLimit: 8192,
};

export function loadStoredSettings(): SettingsState {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  const saved = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      // Migrate legacy ms-scaled vadThreshold (>1) to backend 0.0-1.0 unit.
      if (typeof parsed.vadThreshold === 'number' && parsed.vadThreshold > 1) {
        parsed.vadThreshold = parsed.vadThreshold / 1000;
      }
      return parsed;
    } catch (e) {
      console.error('Failed to parse saved settings:', e);
    }
  }
  return DEFAULT_SETTINGS;
}

export interface SettingsContextValue {
  settings: SettingsState;
  setSettings: React.Dispatch<React.SetStateAction<SettingsState>>;
  micVolume: number;
  setMicVolume: React.Dispatch<React.SetStateAction<number>>;
  hostCaps: HostCapabilities;
  onSavedNotice?: (msg: string) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({
  value,
  children,
}: {
  value: SettingsContextValue;
  children: React.ReactNode;
}) {
  return (
    <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
  );
}

export function useSettingsContext(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettingsContext must be used inside SettingsProvider');
  }
  return ctx;
}

export interface SectionProps {
  onSavedNotice?: (msg: string) => void;
}
