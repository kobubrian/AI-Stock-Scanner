import { Dashboard } from "@/components/Dashboard";

export default function Home() {
  return (
    <main style={{ padding: "1.5rem 2rem", maxWidth: 1400 }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.75rem" }}>
          Trading Research Scanner
        </h1>
        <p style={{ color: "var(--muted)", margin: "0.5rem 0 0" }}>
          API-first research loop — manual execution in Schwab / thinkorswim
        </p>
      </header>
      <Dashboard />
    </main>
  );
}
