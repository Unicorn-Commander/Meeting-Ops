import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { SpeakerTagger } from "../components/SpeakerTagger";
import { AuthProvider } from "../contexts/AuthContext";
import { OrgProvider } from "../contexts/OrgContext";

// Mirrors SpeakerTagger.test.tsx harness. Focus: an unnamed link carrying
// a self-intro name_suggestions prefills the inline enroll input when the
// user opens "+ Enroll new speaker…". Suggestion-only — the chip just sets
// the name, the user still presses Save.

const ORG = {
  id: 1,
  name: "Magic Unicorn",
  slug: "magic-unicorn",
  role: "user",
  is_active: true,
};

const ME = {
  id: 1,
  email: "tester@example.com",
  username: "tester",
  is_active: true,
  is_verified: true,
  is_superuser: false,
  created_at: "2026-05-03T00:00:00Z",
  organizations: [ORG],
  active_organization: ORG,
};

const SPEAKERS = [
  {
    id: 1,
    organization_id: 1,
    display_name: "Aaron Stransky",
    sample_count: 3,
    has_centroid: true,
    embedding_dim: 192,
    embedding_model: "speechbrain/spkrec-ecapa-voxceleb",
  },
];

// SPEAKER_01 is unidentified (speaker_id null) and carries a self-intro
// suggestion parsed from its own utterances.
const LINKS = [
  {
    id: 10,
    session_id: 42,
    raw_label: "SPEAKER_00",
    speaker_id: 1,
    speaker_name: "Aaron Stransky",
    similarity: 0.81,
    source: "auto",
    confirmed: false,
    name_suggestions: [],
  },
  {
    id: 11,
    session_id: 42,
    raw_label: "SPEAKER_01",
    speaker_id: null,
    speaker_name: null,
    similarity: null,
    source: "auto",
    confirmed: false,
    name_suggestions: [{ name: "Sarah", evidence: "you're speaking with Sarah" }],
  },
];

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === "content-type" ? "application/json" : null),
    },
    json: async () => body,
  } as Response;
}

interface FetchCall {
  url: string;
  init?: RequestInit;
}

let fetchCalls: FetchCall[];

function installFetch() {
  fetchCalls = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    fetchCalls.push({ url, init });

    if (url.endsWith("/api/auth/me")) return jsonResponse(ME);
    if (url.includes("/api/speakers?session_id=42")) return jsonResponse(SPEAKERS);
    if (url.match(/\/speaker-links$/)) return jsonResponse(LINKS);
    return jsonResponse({}, 404);
  }));
}

function installLocalStorage() {
  const store: Record<string, string> = {
    access_token: "test-token",
    "meetingops.activeOrg": "magic-unicorn",
  };
  vi.stubGlobal("localStorage", {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      Object.keys(store).forEach((key) => delete store[key]);
    }),
  });
}

async function renderTagger() {
  await act(async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <SpeakerTagger sessionId="42" />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>
    );
  });
}

describe("SpeakerTagger self-introduction suggestions", () => {
  beforeEach(() => {
    installLocalStorage();
    installFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("offers a self-intro name as a suggestion and sends nothing until it is picked", async () => {
    await renderTagger();

    await waitFor(() => expect(screen.getByText("SPEAKER_01")).toBeInTheDocument());

    // Open the picker for the unidentified speaker.
    fireEvent.click(screen.getByRole("button", { name: /Speaker for SPEAKER_01/i }));

    // The heard name is offered first, as a "create" suggestion.
    const suggestion = await screen.findByRole("option", { name: /Create “Sarah”/ });
    expect(suggestion).toBeInTheDocument();
    expect(screen.getByText(/Heard in this meeting/i)).toBeInTheDocument();

    // Suggestion-only: opening the picker fired no enroll POST, and an
    // empty-box Enter picks nothing.
    fireEvent.keyDown(screen.getByRole("combobox", { name: /Search people for Speaker for SPEAKER_01/i }), { key: "Enter" });
    const enrollPost = fetchCalls.find(
      c => c.url.includes("/enroll") && c.init?.method === "POST",
    );
    expect(enrollPost).toBeUndefined();

    // Picking it enrolls under that name.
    fireEvent.click(suggestion);
    await waitFor(() => {
      const post = fetchCalls.find(c => c.url.includes("/enroll") && c.init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(String(post!.init!.body)).display_name).toBe("Sarah");
    });
  });
});
