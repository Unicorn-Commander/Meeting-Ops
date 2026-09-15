import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import Digests from "../pages/Digests";
import { AuthProvider } from "../contexts/AuthContext";
import { OrgProvider } from "../contexts/OrgContext";

const ORG_FIXTURE = {
  id: 1,
  name: "Magic Unicorn",
  slug: "magic-unicorn",
  role: "admin",
  is_active: true,
};

const ME_PAYLOAD = {
  id: 1,
  email: "test@example.com",
  username: "tester",
  is_active: true,
  is_verified: true,
  created_at: "2026-05-03T00:00:00Z",
  organizations: [ORG_FIXTURE],
  active_organization: ORG_FIXTURE,
};

const DIGEST_FIXTURE = {
  period: "month",
  date: "2026-05-01",
  content: "Your team shipped the multi-org migration and stood up the RAG endpoint.",
  meeting_count: 7,
  cached: false,
};

const CACHED_DIGEST_FIXTURE = {
  ...DIGEST_FIXTURE,
  content: "Cached digest from Postgres.",
  cached: true,
};

interface FetchCall {
  url: string;
  init?: RequestInit;
}

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

let fetchMock: ReturnType<typeof vi.fn>;
let fetchCalls: FetchCall[];
let digestQueue: Array<unknown | "error">;
let historyItems: unknown[];
let historyStatus: number;
let preferences = { email_daily_digest: false, email_weekly_digest: false, organization_email_enabled: true };
const HISTORY_FIXTURE = { id: 91, period: 'day', date: '2026-05-01', meeting_count: 2, generated_at: '2026-05-02T13:00:00Z', emailed_to_you: true };


function installFetch(initialDigests: Array<unknown | "error"> = [DIGEST_FIXTURE]) {
  fetchCalls = [];
  historyItems = [];
  historyStatus = 200;
  preferences = { email_daily_digest: false, email_weekly_digest: false, organization_email_enabled: true };
  digestQueue = [...initialDigests];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    fetchCalls.push({ url, init });

    if (url.endsWith("/api/auth/me")) {
      return jsonResponse(ME_PAYLOAD);
    }
    if (url.includes('/api/digests/preferences')) {
      if (init?.method === 'PATCH') preferences = { ...preferences, ...JSON.parse(init.body as string) };
      return jsonResponse(preferences);
    }
    if (url.includes('/api/digests/history/91')) {
      return jsonResponse({ ...HISTORY_FIXTURE, content: 'Selected stored digest.', sources_recorded: true, source_meetings: [{ id: 'meeting-1', title: 'Product planning' }] });
    }
    if (url.includes('/api/digests/history?')) {
      return jsonResponse({ items: historyItems, next_cursor: null }, historyStatus);
    }
    if (url.includes("/api/digests?")) {
      const next = digestQueue.shift();
      if (next === undefined) {
        return jsonResponse({ detail: "no digest" }, 500);
      }
      if (next === "error") {
        return jsonResponse({ detail: "bad request" }, 500);
      }
      return jsonResponse(next);
    }
    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function installLocalStorage() {
  const store: Record<string, string> = { access_token: "test-token" };
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

async function renderDigests() {
  await act(async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <OrgProvider>
            <Digests />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>
    );
  });
  await waitFor(() => expect(screen.getByText(/Meeting Digests/i)).toBeInTheDocument());
}

describe("Digests", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows daily and weekly history and source meeting detail', async () => {
    installFetch();
    historyItems = [HISTORY_FIXTURE];
    await renderDigests();
    expect(screen.getByRole('tab', { name: 'Daily' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(await screen.findByRole('button', { name: /2026-05-01.*2 meetings/i }));
    expect(await screen.findByText('Selected stored digest.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Product planning' })).toHaveAttribute('href', '/sessions/meeting-1');
    expect(screen.getByText('Emailed to you')).toBeInTheDocument();
    historyItems = [];
    fireEvent.click(screen.getByRole('tab', { name: 'Weekly' }));
    expect(await screen.findByText(/No weekly digests yet/)).toBeInTheDocument();
    expect(fetchCalls.some(call => call.url.includes('/history?period=week'))).toBe(true);
    expect(screen.queryByText('Selected stored digest.')).not.toBeInTheDocument();
  });

  it('saves personal daily and weekly email opt-ins, initially off', async () => {
    installFetch();
    await renderDigests();
    const daily = await screen.findByRole('checkbox', { name: 'Email me the daily digest' });
    const weekly = screen.getByRole('checkbox', { name: 'Email me the weekly digest' });
    expect(daily).not.toBeChecked();
    expect(weekly).not.toBeChecked();
    fireEvent.click(daily);
    await waitFor(() => expect(daily).toBeChecked());
    fireEvent.click(weekly);
    await waitFor(() => expect(weekly).toBeChecked());
    const patches = fetchCalls.filter(call => call.init?.method === 'PATCH');
    expect(patches.map(call => JSON.parse(call.init?.body as string))).toEqual([{ email_daily_digest: true }, { email_weekly_digest: true }]);
    expect(new Headers(patches[0].init?.headers).get('X-MeetingOps-Org')).toBe('magic-unicorn');
  });

  it('explains the org email kill-switch and shows history errors with retry', async () => {
    installFetch();
    preferences.organization_email_enabled = false;
    historyStatus = 500;
    await renderDigests();
    expect(await screen.findByText(/Digest email is disabled for this workspace/)).toBeInTheDocument();
    expect(await screen.findByText(/Could not load digest history/)).toBeInTheDocument();
    historyStatus = 200;
    fireEvent.click(screen.getByRole('button', { name: 'Retry history' }));
    expect(await screen.findByText(/No daily digests yet/)).toBeInTheDocument();
  });

  it("renders the period selector with all five window options", async () => {
    installFetch();
    await renderDigests();

    const periodSelect = screen.getByRole("combobox") as HTMLSelectElement;
    const optionValues = Array.from(periodSelect.querySelectorAll("option")).map(
      (opt) => opt.value
    );
    expect(optionValues).toEqual(["day", "week", "month", "quarter", "year"]);
  });

  it("fetches /api/digests with the selected period and renders the response", async () => {
    installFetch([DIGEST_FIXTURE]);
    await renderDigests();

    fireEvent.click(screen.getByRole("button", { name: /generate/i }));

    expect(
      await screen.findByText(/Your team shipped the multi-org migration/i)
    ).toBeInTheDocument();

    const digestCall = fetchCalls.find((call) => call.url.includes("/api/digests?"));
    expect(digestCall).toBeTruthy();
    expect(digestCall?.url).toContain("period=day");
    const headers = new Headers(digestCall?.init?.headers as HeadersInit);
    expect(headers.get("X-MeetingOps-Org")).toBe("magic-unicorn");
  });

  it("shows an error message when the digest endpoint fails", async () => {
    installFetch(["error"]);
    await renderDigests();

    fireEvent.click(screen.getByRole("button", { name: /generate/i }));

    expect(await screen.findByText(/Failed to generate digest\./i)).toBeInTheDocument();
  });

  it("renders the cached digest content immediately on a re-fetch", async () => {
    installFetch([DIGEST_FIXTURE, CACHED_DIGEST_FIXTURE]);
    await renderDigests();

    fireEvent.click(screen.getByRole("button", { name: /generate/i }));
    expect(
      await screen.findByText(/Your team shipped the multi-org migration/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /generate/i }));
    expect(await screen.findByText(/Cached digest from Postgres\./i)).toBeInTheDocument();

    const digestCalls = fetchCalls.filter((call) => call.url.includes("/api/digests?"));
    expect(digestCalls.length).toBe(2);
    // Re-fetch should NOT carry force=true.
    expect(digestCalls[1].url).not.toContain("force=true");
  });
});
