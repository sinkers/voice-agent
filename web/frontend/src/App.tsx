import { useEffect, useState } from "react";
import type { Agent, ConnectResponse } from "./api";
import { connectWithToken } from "./api";
import CallPage from "./pages/Call";
import HomePage from "./pages/Home";

type Page =
  | { name: "home" }
  | { name: "call"; agent: Agent; prefetched?: ConnectResponse }
  | { name: "error"; message: string };

export default function App() {
  const [page, setPage] = useState<Page>({ name: "home" });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (!token) return;

    connectWithToken(token)
      .then((data) => setPage({ name: "call", agent: data.agent, prefetched: data }))
      .catch((e) => setPage({ name: "error", message: e.message }));
  }, []);

  if (page.name === "error") {
    return (
      <div style={{ textAlign: "center", padding: "4rem", fontFamily: "sans-serif" }}>
        <h2>Unable to start call</h2>
        <p>{page.message}</p>
        <button onClick={() => setPage({ name: "home" })}>Go back</button>
      </div>
    );
  }

  if (page.name === "call") {
    return (
      <CallPage
        agent={page.agent}
        prefetched={page.prefetched}
        onEnd={() => setPage({ name: "home" })}
      />
    );
  }

  return (
    <HomePage
      onStart={(agent) => setPage({ name: "call", agent })}
    />
  );
}
