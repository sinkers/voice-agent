/**
 * Tests for src/api.ts
 *
 * Covers:
 * - connectWithToken() sends POST /connect with the correct payload
 * - connectWithToken() returns the parsed ConnectResponse
 * - connectWithToken() throws on a non-200 response
 * - fetchAgents() returns a parsed Agent list
 * - fetchAgents() throws on a non-200 response
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConnectResponse, Agent } from "../api";
import { connectWithToken, fetchAgents } from "../api";

// ---------------------------------------------------------------------------
// fetch mock helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown): void {
  global.fetch = vi.fn().mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

// ---------------------------------------------------------------------------
// connectWithToken
// ---------------------------------------------------------------------------

describe("connectWithToken", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls POST /connect with the config_token in the body", async () => {
    const mockResponse: ConnectResponse = {
      agent: { id: "voice-agent-abc", name: "Voice Agent" },
      token: "livekit-jwt-xyz",
      url: "wss://test.livekit.local",
      room_name: "room-abc123",
    };
    mockFetch(200, mockResponse);

    await connectWithToken("my-config-token");

    expect(global.fetch).toHaveBeenCalledOnce();
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/connect");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    const parsed = JSON.parse(init.body as string);
    expect(parsed.config_token).toBe("my-config-token");
  });

  it("returns the parsed ConnectResponse", async () => {
    const mockResponse: ConnectResponse = {
      agent: { id: "voice-agent-abc", name: "Voice Agent" },
      token: "livekit-jwt-xyz",
      url: "wss://test.livekit.local",
      room_name: "room-abc123",
    };
    mockFetch(200, mockResponse);

    const result = await connectWithToken("some-token");

    expect(result.agent.id).toBe("voice-agent-abc");
    expect(result.agent.name).toBe("Voice Agent");
    expect(result.token).toBe("livekit-jwt-xyz");
    expect(result.url).toBe("wss://test.livekit.local");
    expect(result.room_name).toBe("room-abc123");
  });

  it("throws on a 401 response with server detail", async () => {
    mockFetch(401, { detail: "Config token has expired" });

    await expect(connectWithToken("expired-token")).rejects.toThrow(
      "Config token has expired"
    );
  });

  it("throws on a 500 response", async () => {
    mockFetch(500, { detail: "Internal Server Error" });

    await expect(connectWithToken("any-token")).rejects.toThrow();
  });
});

// ---------------------------------------------------------------------------
// fetchAgents
// ---------------------------------------------------------------------------

describe("fetchAgents", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls GET /agents", async () => {
    const agents: Agent[] = [{ id: "voice-agent", name: "Voice Agent" }];
    mockFetch(200, agents);

    await fetchAgents();

    expect(global.fetch).toHaveBeenCalledOnce();
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/agents");
  });

  it("returns the parsed agent list", async () => {
    const agents: Agent[] = [
      { id: "agent-1", name: "Agent One" },
      { id: "agent-2", name: "Agent Two" },
    ];
    mockFetch(200, agents);

    const result = await fetchAgents();

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("agent-1");
    expect(result[1].name).toBe("Agent Two");
  });

  it("throws on a non-200 response", async () => {
    mockFetch(503, {});

    await expect(fetchAgents()).rejects.toThrow("Failed to fetch agents");
  });
});
