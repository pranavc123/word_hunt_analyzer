import { useQuery } from "@tanstack/react-query";
import { getHealth } from "../api/client";

function Page({ title, headline, children }: { title: string; headline: string; children?: React.ReactNode }) {
  return (
    <main className="page">
      <h1>{title}</h1>
      <p className="headline">{headline}</p>
      {children}
    </main>
  );
}

export function Sessions() {
  return <Page title="Sessions" headline="Your latest session will show up here after you play." />;
}

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
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  return (
    <Page title="Settings" headline="Server connection and app info.">
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
    </Page>
  );
}
