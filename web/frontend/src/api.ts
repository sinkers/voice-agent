const API_URL = import.meta.env.VITE_API_URL as string;

export interface Agent {
  id: string;
  name: string;
}

export interface TokenResponse {
  token: string;
  url: string;
}

export interface DispatchResponse {
  dispatch_id: string;
  room: string;
}

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_URL}/agents`);
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function fetchToken(
  roomName: string,
  identity: string,
  agentId: string
): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_name: roomName, identity, agent_id: agentId }),
  });
  if (!res.ok) throw new Error("Failed to fetch token");
  return res.json();
}

export async function dispatchAgent(
  roomName: string,
  agentName: string
): Promise<DispatchResponse> {
  const res = await fetch(`${API_URL}/dispatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_name: roomName, agent_name: agentName }),
  });
  if (!res.ok) throw new Error("Failed to dispatch agent");
  return res.json();
}

export interface ConnectResponse {
  agent: Agent;
  token: string;
  url: string;
  room_name: string;
}

export async function connectWithToken(configToken: string): Promise<ConnectResponse> {
  const res = await fetch(`${API_URL}/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_token: configToken }),
  });
  if (!res.ok) throw new Error("Invalid or expired call link");
  return res.json();
}
