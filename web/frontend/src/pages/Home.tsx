import { useEffect, useState } from "react";
import type { Agent } from "../api";
import { fetchAgents } from "../api";
import styles from "./Home.module.css";

interface Props {
  onStart: (agent: Agent) => void;
}

export default function HomePage({ onStart }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAgents()
      .then((data) => {
        setAgents(data);
        if (data.length > 0) setSelectedId(data[0].id);
      })
      .catch(() => setError("Could not load agents. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  function handleStart() {
    const agent = agents.find((a) => a.id === selectedId);
    if (agent) onStart(agent);
  }

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>Voice Agent</h1>
      <p className={styles.subtitle}>Select an agent and start a call.</p>

      {loading && <p className={styles.status}>Loading agents…</p>}
      {error && <p className={styles.error}>{error}</p>}

      {!loading && !error && (
        <div className={styles.card}>
          <label htmlFor="agent-select" className={styles.label}>
            Agent
          </label>
          <select
            id="agent-select"
            className={styles.select}
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>

          <button
            className={styles.button}
            onClick={handleStart}
            disabled={!selectedId}
          >
            Start Call
          </button>
        </div>
      )}
    </div>
  );
}
