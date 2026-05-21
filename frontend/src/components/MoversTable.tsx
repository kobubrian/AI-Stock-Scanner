"use client";

type Snapshot = {
  ticker: string;
  price: number;
  percent_change: number;
  relative_volume: number;
  spread_percent?: number | null;
  above_vwap?: boolean | null;
  session?: string;
  price_as_of?: string | null;
  scores: {
    long_score: number;
    short_score: number;
    squeeze_risk: number;
  };
  trade_plan: {
    stop?: number | null;
    target_1?: number | null;
  };
  data_available: boolean;
};

function fmtSession(s?: string): string {
  if (!s) return "";
  const map: Record<string, string> = {
    premarket: "PM",
    regular: "RTH",
    afterhours: "AH",
    overnight_closed: "Closed",
    weekend: "Wknd",
  };
  return map[s] || s;
}

function fmtTime(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function MoversTable({
  rows,
  onRefresh,
  loading,
  scanLabel = "Run scan",
}: {
  rows: Snapshot[];
  onRefresh: () => void;
  loading: boolean;
  scanLabel?: string;
}) {
  const safeRows = Array.isArray(rows) ? rows : [];

  return (
    <div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        style={{
          marginBottom: "1rem",
          padding: "0.5rem 1rem",
          background: "var(--accent)",
          border: "none",
          borderRadius: 6,
          color: "#fff",
          cursor: loading ? "wait" : "pointer",
        }}
      >
        {loading ? "Working…" : scanLabel}
      </button>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
              <th style={{ padding: "0.5rem" }}>Ticker</th>
              <th>Price</th>
              <th>As of</th>
              <th>%</th>
              <th>RVOL</th>
              <th>VWAP</th>
              <th>Long</th>
              <th>Short</th>
              <th>Squeeze</th>
              <th>Stop</th>
              <th>T1</th>
            </tr>
          </thead>
          <tbody>
            {safeRows.length === 0 && (
              <tr>
                <td colSpan={11} style={{ padding: "1rem", color: "var(--muted)" }}>
                  No data — run a scan, then use Refresh prices for live quotes
                </td>
              </tr>
            )}
            {safeRows.map((r, i) => (
              <tr key={`${r.ticker}-${i}`} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.5rem", fontWeight: 600 }}>{r.ticker}</td>
                <td>{r.data_available ? r.price.toFixed(2) : "—"}</td>
                <td style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
                  {fmtSession(r.session)}
                  {fmtTime(r.price_as_of) ? ` ${fmtTime(r.price_as_of)}` : ""}
                </td>
                <td style={{ color: r.percent_change >= 0 ? "var(--long)" : "var(--short)" }}>
                  {r.percent_change.toFixed(1)}%
                </td>
                <td>{(r.relative_volume ?? 0).toFixed(1)}x</td>
                <td>
                  {r.above_vwap === true ? "Above" : r.above_vwap === false ? "Below" : "—"}
                </td>
                <td>{(r.scores?.long_score ?? 0).toFixed(0)}</td>
                <td>{(r.scores?.short_score ?? 0).toFixed(0)}</td>
                <td style={{ color: (r.scores?.squeeze_risk ?? 0) >= 70 ? "var(--warn)" : undefined }}>
                  {(r.scores?.squeeze_risk ?? 0).toFixed(0)}
                </td>
                <td>{r.trade_plan?.stop ?? "—"}</td>
                <td>{r.trade_plan?.target_1 ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
