import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getHealth, getToken, setToken } from "../api/client";
import { Page } from "./Sessions";

export function Patterns() {
  return <Page title="Patterns" headline="Patterns appear once a few sessions are in." />;
}

export function Strategy() {
  return <Page title="Strategy" headline="Strategy tips need more games to be reliable." />;
}

export function Dictionary() {
  return <Page title="Dictionary" headline="Words the game accepted or rejected, and boards awaiting their full list." />;
}

export function Settings() {
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const [token, setLocal] = useState(getToken());
  const [saved, setSaved] = useState(false);
  return (
    <Page title="Settings" headline="Server connection and access.">
      <div className="card">
        Server:{" "}
        {health.isPending ? (
          "checking…"
        ) : health.isSuccess ? (
          <span className="status-ok">reachable (v{health.data.version})</span>
        ) : (
          <span className="status-bad">unreachable</span>
        )}
      </div>
      <form
        className="card form"
        onSubmit={(e) => {
          e.preventDefault();
          setToken(token);
          setSaved(true);
          qc.invalidateQueries();
        }}
      >
        <label>
          Access token (the WH_TOKEN from your Mac)
          <input type="password" autoComplete="off" value={token} onChange={(e) => (setLocal(e.target.value), setSaved(false))} />
        </label>
        <button className="btn" type="submit">
          {saved ? "Saved" : "Save token"}
        </button>
      </form>
    </Page>
  );
}
