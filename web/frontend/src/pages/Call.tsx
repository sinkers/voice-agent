import {
  ControlBar,
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useRemoteParticipants,
  useRoomContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { ConnectionState } from "livekit-client";
import { useEffect, useRef, useState } from "react";
import type { Agent, ConnectResponse } from "../api";
import { dispatchAgent, fetchToken } from "../api";
import styles from "./Call.module.css";

interface Props {
  agent: Agent;
  prefetched?: ConnectResponse;
  onEnd: () => void;
}

interface RoomInfo {
  token: string;
  url: string;
  roomName: string;
}

export default function CallPage({ agent, prefetched, onEnd }: Props) {
  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // If we already have a pre-fetched connection (from a signed URL), use it directly.
    if (prefetched) {
      setRoomInfo({ token: prefetched.token, url: prefetched.url, roomName: prefetched.room_name });
      return;
    }

    const roomName = `room-${crypto.randomUUID()}`;
    const identity = `user-${crypto.randomUUID()}`;

    async function setup() {
      try {
        const { token, url } = await fetchToken(roomName, identity, agent.id);
        await dispatchAgent(roomName, agent.id);
        setRoomInfo({ token, url, roomName });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to start call");
      }
    }

    setup();
  }, [agent, prefetched]);

  if (error) {
    return (
      <div className={styles.centered}>
        <p className={styles.error}>{error}</p>
        <button className={styles.endButton} onClick={onEnd}>
          Back
        </button>
      </div>
    );
  }

  if (!roomInfo) {
    return (
      <div className={styles.centered}>
        <p className={styles.status}>Connecting…</p>
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={roomInfo.token}
      serverUrl={roomInfo.url}
      connect
      audio
      video={false}
      onDisconnected={onEnd}
      className={styles.room}
    >
      <RoomAudioRenderer />
      <CallUI agentName={agent.name} onEnd={onEnd} />
    </LiveKitRoom>
  );
}

function CallUI({ agentName, onEnd }: { agentName: string; onEnd: () => void }) {
  const connectionState = useConnectionState();
  const room = useRoomContext();
  const disconnecting = useRef(false);

  async function handleEnd() {
    if (disconnecting.current) return;
    disconnecting.current = true;
    await room.disconnect();
    onEnd();
  }

  const remoteParticipants = useRemoteParticipants();
  const agentConnected = remoteParticipants.length > 0;
  const { state: agentState } = useVoiceAssistant();

  const statusLabel =
    connectionState === ConnectionState.Connecting
      ? "Connecting…"
      : connectionState === ConnectionState.Connected
      ? agentConnected
        ? `In call with ${agentName}`
        : `Waiting for ${agentName} to join…`
      : "Disconnected";

  // Derive activity label from agent state
  const activityLabel =
    agentState === "speaking"
      ? `${agentName} is speaking…`
      : agentState === "thinking"
      ? "Thinking…"
      : agentState === "listening"
      ? "Listening…"
      : null;

  const activityClass =
    agentState === "speaking"
      ? styles.activitySpeaking
      : agentState === "thinking"
      ? styles.activityThinking
      : agentState === "listening"
      ? styles.activityListening
      : styles.activityIdle;

  return (
    <div className={styles.callUi}>
      <p className={styles.callStatus}>{statusLabel}</p>
      <div className={styles.participantStatus}>
        <span className={agentConnected ? styles.dotOnline : styles.dotWaiting} />
        <span>{agentConnected ? `${agentName} is here` : `${agentName} joining…`}</span>
      </div>
      {agentConnected && (
        <div className={`${styles.activityBadge} ${activityClass}`}>
          {activityLabel ?? "Idle"}
        </div>
      )}
      <ControlBar
        controls={{ microphone: true, camera: false, screenShare: false, leave: false }}
      />
      <button className={styles.endButton} onClick={handleEnd}>
        End Call
      </button>
    </div>
  );
}
