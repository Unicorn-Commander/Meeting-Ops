// Conference Room API client.
//
// Wraps every /api/rooms endpoint with a single auth+org-header build.
// Backend agent is shipping the matching endpoints; until they land,
// every call falls back to a small in-memory mock so the UI can be
// exercised end-to-end. The mock layer is keyed on `MOCK_MODE`, which
// flips to true the first time any endpoint 404s — once the backend
// lands no app restart is needed, just a refresh.
//
// TODO(backend-rooms): delete mocks + MOCK_STORE once Phase 1 backend
// is in production. Tracked in CR-006 ticket.

import { config } from '../config';

export type RoomStatus = 'idle' | 'recording' | 'offline' | 'error' | 'paused';
export type RoomSourceType =
  | 'server_usb_mic'
  | 'network_stream'
  | 'satellite'
  | 'companion_app';
export type RoomRole = 'view' | 'record' | 'manage';

/**
 * Frontend Room shape. Note: the backend returns `id` as a string UUID
 * and uses `default_retention_days` instead of `retention_days`. We
 * normalize to numeric id (parsed) and retention_days at the boundary
 * — see `normalizeRoom()`.
 */
export interface Room {
  id: number;
  organization_id: number;
  name: string;
  location?: string | null;
  description?: string | null;
  status: RoomStatus;
  recording_mode: 'manual' | 'scheduled' | 'always_on' | 'wake_word';
  retention_days: number | null;
  legal_hold: boolean;
  current_session_id?: string | null;
  current_session_started_at?: string | null;
  last_recording_at?: string | null;
  created_at: string;
  updated_at: string;
  sources?: RoomSource[];
  /** Stash the raw upstream id so URL params keep working when the
   * backend issues UUIDs that don't parse to a finite Number. */
  raw_id?: string;
}

export interface RoomSource {
  id: number;
  room_id: number;
  hardware_type: RoomSourceType;
  device_path?: string | null;
  device_id?: string | null;
  label: string;
  is_active: boolean;
  health_status: 'healthy' | 'degraded' | 'offline' | 'unbound' | 'error' | 'unknown';
  created_at: string;
  raw_id?: string;
}

/**
 * Map the backend's string ids and slightly different field names to the
 * frontend shape used across the rooms UI. If the input is already in
 * frontend shape (e.g. from mocks) the cast is a no-op.
 */
function normalizeRoom(raw: unknown): Room {
  const r = raw as Record<string, unknown>;
  const idRaw = r.id;
  const id =
    typeof idRaw === 'number'
      ? idRaw
      : typeof idRaw === 'string' && /^\d+$/.test(idRaw)
      ? Number(idRaw)
      : // fallback: hash the UUID into a stable positive int. Used only
        // for `key=` props; URL routing uses raw_id when set.
        Math.abs(
          Array.from(String(idRaw)).reduce(
            (acc, ch) => (acc * 31 + ch.charCodeAt(0)) | 0,
            7,
          ),
        ) || 1;
  const status = (r.status as RoomStatus) || 'idle';
  const retention =
    typeof r.retention_days === 'number'
      ? (r.retention_days as number)
      : typeof r.default_retention_days === 'number'
      ? (r.default_retention_days as number)
      : null;

  // recording_mode isn't in the backend's RoomResponse yet — derive
  // from schedule_json when present, fall back to 'manual'.
  const sched = (r.schedule_json as Record<string, unknown> | null) || null;
  const recording_mode = (sched?.mode as Room['recording_mode']) || 'manual';

  return {
    id,
    raw_id: typeof idRaw === 'string' ? idRaw : undefined,
    organization_id: Number(r.organization_id) || 0,
    name: String(r.name || ''),
    location: (r.location as string | null) || null,
    description: (r.description as string | null) || null,
    status,
    recording_mode,
    retention_days: retention,
    legal_hold: !!r.legal_hold,
    current_session_id: (r.current_session_id as string | null) || null,
    current_session_started_at: (r.current_session_started_at as string | null) || null,
    last_recording_at: (r.last_recording_at as string | null) || null,
    created_at: String(r.created_at || ''),
    updated_at: String(r.updated_at || ''),
    sources: Array.isArray(r.sources) ? (r.sources as unknown[]).map(normalizeSource) : undefined,
  };
}

function normalizeSource(raw: unknown): RoomSource {
  const s = raw as Record<string, unknown>;
  const idRaw = s.id;
  const id =
    typeof idRaw === 'number'
      ? idRaw
      : typeof idRaw === 'string' && /^\d+$/.test(idRaw)
      ? Number(idRaw)
      : Math.abs(
          Array.from(String(idRaw)).reduce(
            (acc, ch) => (acc * 31 + ch.charCodeAt(0)) | 0,
            7,
          ),
        ) || 1;
  const roomIdRaw = s.room_id;
  const room_id =
    typeof roomIdRaw === 'number'
      ? roomIdRaw
      : typeof roomIdRaw === 'string' && /^\d+$/.test(roomIdRaw)
      ? Number(roomIdRaw)
      : 0;
  // Backend uses `status` field; frontend uses health_status. is_active
  // isn't surfaced today — infer from status === 'active' or default to
  // the first source returned.
  const status = String((s.status as string) || 'unknown');
  const isActive =
    typeof s.is_active === 'boolean'
      ? (s.is_active as boolean)
      : status === 'active';
  const healthMap: Record<string, RoomSource['health_status']> = {
    active: 'healthy',
    healthy: 'healthy',
    degraded: 'degraded',
    offline: 'offline',
    error: 'error',
    unbound: 'unbound',
  };
  const health_status = (healthMap[status] as RoomSource['health_status']) || 'unknown';

  return {
    id,
    raw_id: typeof idRaw === 'string' ? idRaw : undefined,
    room_id,
    hardware_type: (s.hardware_type as RoomSourceType) || 'server_usb_mic',
    device_path: (s.device_path as string | null) || null,
    device_id: typeof s.device_id === 'string' ? s.device_id : null,
    label:
      String(s.label || '') ||
      String(s.device_path || '') ||
      String(s.hardware_type || ''),
    is_active: isActive,
    health_status,
    created_at: String(s.created_at || ''),
  };
}

export interface PairingCode {
  code: string;
  expires_at: string;
  room_id: number;
}

export interface RoomAclEntry {
  user_id: number;
  username?: string | null;
  email?: string | null;
  full_name?: string | null;
  role: RoomRole;
  granted_at?: string | null;
}

export interface OrgUser {
  id: number;
  username: string;
  email?: string | null;
  full_name?: string | null;
  role?: string | null;
}

export interface AudioDevice {
  device_path: string;
  card_name: string;
  device_name: string;
}

export interface CreateRoomBody {
  name: string;
  location?: string | null;
  default_retention_days?: number | null;
}

export interface UpdateRoomBody {
  name?: string;
  location?: string | null;
  retention_days?: number | null;
  legal_hold?: boolean;
}

export interface AddSourceBody {
  hardware_type: RoomSourceType;
  device_path?: string | null;
  device_id?: string | null;
  label: string;
}

export interface RecordingSessionSummary {
  id: string;
  title?: string | null;
  created_at: string | null;
  duration?: number | null;
  status: string;
  summary_preview?: string | null;
}

// --- Mock fallback layer ---------------------------------------------------

let MOCK_MODE = false;

interface MockStore {
  rooms: Room[];
  sources: RoomSource[];
  acl: Map<number, RoomAclEntry[]>;
  pairing: Map<number, PairingCode>;
  nextRoomId: number;
  nextSourceId: number;
}

const MOCK_STORE: MockStore = {
  rooms: [
    {
      id: 1,
      organization_id: 1,
      name: 'Conference Room A (sample)',
      location: 'HQ, 2nd floor',
      description: null,
      status: 'recording',
      recording_mode: 'manual',
      retention_days: 90,
      legal_hold: false,
      current_session_id: 'mock-session-1',
      current_session_started_at: new Date(Date.now() - 42 * 60 * 1000).toISOString(),
      last_recording_at: new Date(Date.now() - 42 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 2,
      organization_id: 1,
      name: 'Conference Room B (sample)',
      location: 'Building B, Floor 3',
      description: null,
      status: 'idle',
      recording_mode: 'manual',
      retention_days: 90,
      legal_hold: false,
      current_session_id: null,
      current_session_started_at: null,
      last_recording_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 12 * 24 * 60 * 60 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ],
  sources: [
    {
      id: 1,
      room_id: 1,
      hardware_type: 'server_usb_mic',
      device_path: 'hw:2,0',
      device_id: null,
      label: 'USB mic: hw:2,0',
      is_active: true,
      health_status: 'healthy',
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 2,
      room_id: 1,
      hardware_type: 'server_usb_mic',
      device_path: 'hw:3,0',
      device_id: null,
      label: 'Ceiling mic',
      is_active: false,
      health_status: 'healthy',
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 3,
      room_id: 2,
      hardware_type: 'server_usb_mic',
      device_path: 'hw:3,0',
      device_id: null,
      label: 'USB mic: hw:3,0',
      is_active: true,
      health_status: 'healthy',
      created_at: new Date(Date.now() - 12 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ],
  acl: new Map(),
  pairing: new Map(),
  nextRoomId: 3,
  nextSourceId: 4,
};

function pseudoSleep(): Promise<void> {
  return new Promise((res) => setTimeout(res, 80));
}

function generatePairingCode(): string {
  // 6-digit numeric, no leading zero stripping.
  const n = Math.floor(100000 + Math.random() * 900000);
  return String(n);
}

// --- HTTP layer ------------------------------------------------------------

interface RoomsApiOptions {
  orgSlug: string | null;
}

function buildHeaders(orgSlug: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  try {
    const token = localStorage.getItem('access_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    /* ignore storage failures */
  }
  if (orgSlug) headers['X-MeetingOps-Org'] = orgSlug;
  return headers;
}

async function request<T>(
  url: string,
  options: RequestInit & { orgSlug: string | null },
): Promise<T> {
  const { orgSlug, ...init } = options;
  const headers = {
    ...buildHeaders(orgSlug),
    ...(init.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${config.apiBaseUrl}${url}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (res.status === 404) {
    // Backend agent hasn't landed the endpoint yet — flip to mock mode.
    MOCK_MODE = true;
    throw new MockFallbackNeeded(url);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body);
    } catch {
      detail = `${res.status} ${res.statusText}`;
    }
    throw new Error(detail || `Request failed: ${url}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

class MockFallbackNeeded extends Error {
  constructor(url: string) {
    super(`Mock fallback for ${url}`);
    this.name = 'MockFallbackNeeded';
  }
}

function isMockFallback(err: unknown): err is MockFallbackNeeded {
  return err instanceof MockFallbackNeeded || (err as Error)?.name === 'MockFallbackNeeded';
}

// --- Public API ------------------------------------------------------------

export function isMockMode(): boolean {
  return MOCK_MODE;
}

export const roomsApi = {
  async list({ orgSlug }: RoomsApiOptions): Promise<Room[]> {
    try {
      const raw = await request<unknown[]>('/api/rooms', { orgSlug, method: 'GET' });
      return raw.map(normalizeRoom);
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      return MOCK_STORE.rooms.map((r) => ({
        ...r,
        sources: MOCK_STORE.sources.filter((s) => s.room_id === r.id),
      }));
    }
  },

  async get(id: number | string, { orgSlug }: RoomsApiOptions): Promise<Room> {
    try {
      const raw = await request<unknown>(`/api/rooms/${id}`, { orgSlug, method: 'GET' });
      return normalizeRoom(raw);
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const r = MOCK_STORE.rooms.find((x) => x.id === Number(id));
      if (!r) throw new Error('Room not found');
      return { ...r, sources: MOCK_STORE.sources.filter((s) => s.room_id === Number(id)) };
    }
  },

  async create(body: CreateRoomBody, { orgSlug }: RoomsApiOptions): Promise<Room> {
    try {
      const raw = await request<unknown>('/api/rooms', {
        orgSlug,
        method: 'POST',
        body: JSON.stringify(body),
      });
      return normalizeRoom(raw);
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const now = new Date().toISOString();
      const newRoom: Room = {
        id: MOCK_STORE.nextRoomId++,
        organization_id: 1,
        name: body.name,
        location: body.location || null,
        description: null,
        status: 'idle',
        recording_mode: 'manual',
        retention_days: body.default_retention_days ?? 90,
        legal_hold: false,
        current_session_id: null,
        last_recording_at: null,
        created_at: now,
        updated_at: now,
      };
      MOCK_STORE.rooms.push(newRoom);
      return { ...newRoom, sources: [] };
    }
  },

  async update(id: number | string, body: UpdateRoomBody, { orgSlug }: RoomsApiOptions): Promise<Room> {
    // Backend uses `default_retention_days`; map our `retention_days`
    // through so it lands correctly.
    const wireBody: Record<string, unknown> = { ...body };
    if ('retention_days' in body) {
      wireBody.default_retention_days = body.retention_days;
      delete wireBody.retention_days;
    }
    try {
      const raw = await request<unknown>(`/api/rooms/${id}`, {
        orgSlug,
        method: 'PUT',
        body: JSON.stringify(wireBody),
      });
      return normalizeRoom(raw);
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const idx = MOCK_STORE.rooms.findIndex((x) => x.id === Number(id));
      if (idx === -1) throw new Error('Room not found');
      MOCK_STORE.rooms[idx] = {
        ...MOCK_STORE.rooms[idx],
        ...body,
        updated_at: new Date().toISOString(),
      } as Room;
      return {
        ...MOCK_STORE.rooms[idx],
        sources: MOCK_STORE.sources.filter((s) => s.room_id === Number(id)),
      };
    }
  },

  async remove(id: number | string, { orgSlug }: RoomsApiOptions): Promise<void> {
    try {
      await request<void>(`/api/rooms/${id}`, { orgSlug, method: 'DELETE' });
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      MOCK_STORE.rooms = MOCK_STORE.rooms.filter((r) => r.id !== Number(id));
      MOCK_STORE.sources = MOCK_STORE.sources.filter((s) => s.room_id !== Number(id));
      MOCK_STORE.acl.delete(Number(id));
      MOCK_STORE.pairing.delete(Number(id));
    }
  },

  async listSources(roomId: number | string, { orgSlug }: RoomsApiOptions): Promise<RoomSource[]> {
    try {
      const raw = await request<unknown[]>(`/api/rooms/${roomId}/sources`, {
        orgSlug,
        method: 'GET',
      });
      const list = raw.map(normalizeSource);
      // If the backend doesn't surface is_active, mark the first one
      // active by default so the UI has *something* to point at.
      if (list.length > 0 && !list.some((s) => s.is_active)) {
        list[0].is_active = true;
      }
      return list;
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      return MOCK_STORE.sources.filter((s) => s.room_id === Number(roomId));
    }
  },

  async addSource(
    roomId: number | string,
    body: AddSourceBody,
    { orgSlug }: RoomsApiOptions,
  ): Promise<RoomSource> {
    try {
      const raw = await request<unknown>(`/api/rooms/${roomId}/sources`, {
        orgSlug,
        method: 'POST',
        body: JSON.stringify(body),
      });
      return normalizeSource(raw);
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const newSrc: RoomSource = {
        id: MOCK_STORE.nextSourceId++,
        room_id: Number(roomId),
        hardware_type: body.hardware_type,
        device_path: body.device_path || null,
        device_id: body.device_id || null,
        label: body.label,
        is_active:
          MOCK_STORE.sources.filter((s) => s.room_id === Number(roomId)).length === 0,
        health_status: 'healthy',
        created_at: new Date().toISOString(),
      };
      MOCK_STORE.sources.push(newSrc);
      return newSrc;
    }
  },

  async removeSource(
    roomId: number | string,
    sourceId: number | string,
    { orgSlug }: RoomsApiOptions,
  ): Promise<void> {
    try {
      await request<void>(`/api/rooms/${roomId}/sources/${sourceId}`, {
        orgSlug,
        method: 'DELETE',
      });
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      MOCK_STORE.sources = MOCK_STORE.sources.filter(
        (s) => !(s.id === Number(sourceId) && s.room_id === Number(roomId)),
      );
    }
  },

  async generatePairingCode(roomId: number | string, { orgSlug }: RoomsApiOptions): Promise<PairingCode> {
    try {
      const raw = await request<Record<string, unknown>>(
        `/api/rooms/${roomId}/pairing-codes`,
        { orgSlug, method: 'POST', body: JSON.stringify({}) },
      );
      return {
        code: String(raw.code || ''),
        expires_at: String(raw.expires_at || ''),
        room_id: Number(raw.room_id) || Number(roomId) || 0,
      };
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const code: PairingCode = {
        code: generatePairingCode(),
        expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
        room_id: Number(roomId),
      };
      MOCK_STORE.pairing.set(Number(roomId), code);
      return code;
    }
  },

  async startRecording(roomId: number | string, { orgSlug }: RoomsApiOptions): Promise<{ session_id: string }> {
    try {
      const raw = await request<Record<string, unknown>>(
        `/api/rooms/${roomId}/recordings/start`,
        { orgSlug, method: 'POST', body: JSON.stringify({}) },
      );
      return { session_id: String(raw.session_id || raw.session_pk || '') };
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const idx = MOCK_STORE.rooms.findIndex((r) => r.id === Number(roomId));
      if (idx === -1) throw new Error('Room not found');
      const sessionId = `mock-${Date.now()}`;
      MOCK_STORE.rooms[idx] = {
        ...MOCK_STORE.rooms[idx],
        status: 'recording',
        current_session_id: sessionId,
        current_session_started_at: new Date().toISOString(),
        last_recording_at: new Date().toISOString(),
      };
      return { session_id: sessionId };
    }
  },

  async stopRecording(roomId: number | string, { orgSlug }: RoomsApiOptions): Promise<void> {
    try {
      await request<void>(`/api/rooms/${roomId}/recordings/stop`, {
        orgSlug,
        method: 'POST',
        body: JSON.stringify({}),
      });
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const idx = MOCK_STORE.rooms.findIndex((r) => r.id === Number(roomId));
      if (idx === -1) throw new Error('Room not found');
      MOCK_STORE.rooms[idx] = {
        ...MOCK_STORE.rooms[idx],
        status: 'idle',
        current_session_id: null,
        current_session_started_at: null,
      };
    }
  },

  async listAcl(roomId: number | string, { orgSlug }: RoomsApiOptions): Promise<RoomAclEntry[]> {
    try {
      const raw = await request<Array<Record<string, unknown>>>(`/api/rooms/${roomId}/acl`, {
        orgSlug,
        method: 'GET',
      });
      return raw.map((e) => ({
        user_id: Number(e.user_id),
        role: (e.role as RoomRole) || 'view',
        granted_at: (e.created_at as string) || (e.granted_at as string) || null,
        username: (e.username as string) || null,
        email: (e.email as string) || null,
        full_name: (e.full_name as string) || null,
      }));
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      return MOCK_STORE.acl.get(Number(roomId)) || [];
    }
  },

  async grantAcl(
    roomId: number | string,
    body: { user_id: number; role: RoomRole },
    { orgSlug }: RoomsApiOptions,
  ): Promise<RoomAclEntry> {
    try {
      const raw = await request<Record<string, unknown>>(`/api/rooms/${roomId}/acl`, {
        orgSlug,
        method: 'POST',
        body: JSON.stringify(body),
      });
      return {
        user_id: Number(raw.user_id),
        role: (raw.role as RoomRole) || body.role,
        granted_at: (raw.created_at as string) || (raw.granted_at as string) || null,
      };
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const existing = MOCK_STORE.acl.get(Number(roomId)) || [];
      const entry: RoomAclEntry = {
        user_id: body.user_id,
        role: body.role,
        granted_at: new Date().toISOString(),
      };
      const filtered = existing.filter((e) => e.user_id !== body.user_id);
      filtered.push(entry);
      MOCK_STORE.acl.set(Number(roomId), filtered);
      return entry;
    }
  },

  async revokeAcl(roomId: number | string, userId: number, { orgSlug }: RoomsApiOptions): Promise<void> {
    try {
      await request<void>(`/api/rooms/${roomId}/acl/${userId}`, {
        orgSlug,
        method: 'DELETE',
      });
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      const existing = MOCK_STORE.acl.get(Number(roomId)) || [];
      MOCK_STORE.acl.set(
        Number(roomId),
        existing.filter((e) => e.user_id !== userId),
      );
    }
  },

  async listAudioDevices({ orgSlug }: RoomsApiOptions): Promise<AudioDevice[]> {
    try {
      const raw = await request<Array<Record<string, unknown>>>(
        '/api/system/audio-devices',
        { orgSlug, method: 'GET' },
      );
      return raw.map((d) => ({
        device_path:
          typeof d.device_path === 'string'
            ? d.device_path
            : typeof d.card === 'number' && typeof d.device === 'number'
            ? `hw:${d.card},${d.device}`
            : String(d.device_path || ''),
        card_name: String(d.card_name || d.card || ''),
        device_name: String(d.device_name || d.name || ''),
      }));
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      await pseudoSleep();
      return [
        {
          device_path: 'hw:0,0',
          card_name: 'HDA Intel PCH',
          device_name: 'ALC295 Analog',
        },
        {
          device_path: 'hw:2,0',
          card_name: 'USB Audio Device',
          device_name: 'Yeti Stereo Microphone',
        },
        {
          device_path: 'hw:3,0',
          card_name: 'Ceiling Mic Array',
          device_name: 'ReSpeaker 4-Mic',
        },
      ];
    }
  },

  async listOrgUsers({ orgSlug }: RoomsApiOptions): Promise<OrgUser[]> {
    // Spec said `GET /api/users/org` but that route doesn't exist yet.
    // `/api/auth/users` exists, gated on `user.read`, and returns the same
    // shape we need. Try the spec path first; fall back to /api/auth/users;
    // fall back to mock data last.
    try {
      return await request<OrgUser[]>('/api/users/org', { orgSlug, method: 'GET' });
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      try {
        return await request<OrgUser[]>('/api/auth/users', { orgSlug, method: 'GET' });
      } catch (err2) {
        if (!isMockFallback(err2)) throw err2;
        await pseudoSleep();
        return [
          { id: 1, username: 'aaron', email: 'aaron@magicunicorn.tech', full_name: 'Aaron Stransky', role: 'admin' },
          { id: 2, username: 'shafen', email: 'shafen@example.com', full_name: 'Shafen Khan', role: 'member' },
        ];
      }
    }
  },

  async listSessions(
    roomId: number | string,
    { orgSlug }: RoomsApiOptions,
  ): Promise<RecordingSessionSummary[]> {
    try {
      return await request<RecordingSessionSummary[]>(
        `/api/recordings/sessions/?room_id=${roomId}`,
        { orgSlug, method: 'GET' },
      );
    } catch (err) {
      if (!isMockFallback(err)) throw err;
      // Try the other known endpoint shape as a fallback.
      try {
        return await request<RecordingSessionSummary[]>(
          `/api/simple/recording-sessions?room_id=${roomId}`,
          { orgSlug, method: 'GET' },
        );
      } catch (err2) {
        if (!isMockFallback(err2)) throw err2;
        await pseudoSleep();
        if (Number(roomId) === 1) {
          return [
            {
              id: 'mock-session-prev-1',
              title: 'Engineering standup',
              created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
              duration: 35 * 60,
              status: 'completed',
              summary_preview: 'Discussed Q3 priorities and the new recording stack.',
            },
            {
              id: 'mock-session-prev-2',
              title: 'Customer call: Holloway',
              created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
              duration: 52 * 60,
              status: 'completed',
              summary_preview: 'Walked through content production cadence.',
            },
          ];
        }
        return [];
      }
    }
  },
};

export default roomsApi;
