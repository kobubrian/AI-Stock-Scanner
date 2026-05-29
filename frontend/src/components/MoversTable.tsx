"use client";

type Snapshot = {
  ticker: string;
  price: number;
  percent_change: number;
  relative_volume: number;
  spread_percent?: number | null;
  above_vwap?: boolean | null;
  session?: string;
  active_session?: string;
  price_as_of?: string | null;
  regular_close?: number | null;
  afterhours_price?: number | null;
  afterhours_percent_change?: number | null;
  premarket_price?: number | null;
  overnight_price?: number | null;
  market_price?: number | null;
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

function fmtSessionLabel(s?: string): string {
  if (!s) return "";
  const map: Record<string, string> = {
    premarket: "Pre-market",
    regular: "Regular",
    afterhours: "After hours",
    overnight: "Overnight",
    weekend: "Weekend",
    overnight_closed: "Overnight",
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

function sessionExtras(r: Snapshot): string[] {
  const lines: string[] = [];
  const active = (r.active_session || r.session || "").toLowerCase();
  const p = r.price;
  const extended = ["afterhours", "premarket", "overnight", "overnight_closed", "weekend"].includes(
    active
  );

  const add = (label: string, val?: number | null, opts?: { always?: boolean }) => {
    if (val == null || val <= 0) return;
    const key = label.toLowerCase();
    const isPrimary =
      (key === "ah" && active === "afterhours") ||
      (key === "on" && (active === "overnight" || active === "overnight_closed")) ||
      (key === "pm" && active === "premarket") ||
      (key === "close" && active === "regular") ||
      (key === "mkt" && active === "market");
    if (isPrimary) return;
    if (!opts?.always && Math.abs(val - p) < 0.005) return;
    lines.push(`${label} $${val.toFixed(2)}`);
  };

  add("Close", r.regular_close);
  add("AH", r.afterhours_price, { always: extended });
  add("PM", r.premarket_price, { always: extended });
  add("ON", r.overnight_price, { always: extended });
  add("Mkt", r.market_price);
  return lines;
}

export function MoversTable({
  rows,
  onRunScan,
  loading,
  scanLabel = "Run scan",
}: {
  rows: Snapshot[];
  onRunScan: () => void;
  loading: boolean;
  scanLabel?: string;
}) {
  const safeRows = Array.isArray(rows) ? rows : [];

  return (
    <div>
      <button
        type="button"
        onClick={onRunScan}
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
              <th>Price (now)</th>
              <th>Session</th>
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
                  No data — click Run scan to load tickers (live prices load automatically)
                </td>
              </tr>
            )}
            {safeRows.map((r, i) => {
              const extras = sessionExtras(r);
              const sess = fmtSessionLabel(r.active_session || r.session);
              return (
                <tr key={`${r.ticker}-${i}`} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "0.5rem", fontWeight: 600 }}>{r.ticker}</td>
                  <td>
                    {r.data_available ? (
                      <div>
                        <div style={{ fontWeight: 600 }}>{r.price.toFixed(2)}</div>
                        {extras.length > 0 && (
                          <div style={{ color: "var(--muted)", fontSize: "0.72rem", marginTop: 2 }}>
                            {extras.join(" · ")}
                          </div>
                        )}
                      </div>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
                    <div style={{ fontWeight: 500, color: "var(--text)" }}>{sess || "—"}</div>
                    {fmtTime(r.price_as_of) ? (
                      <div>updated {fmtTime(r.price_as_of)}</div>
                    ) : null}
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
                  <td
                    style={{
                      color: (r.scores?.squeeze_risk ?? 0) >= 70 ? "var(--warn)" : undefined,
                    }}
                  >
                    {(r.scores?.squeeze_risk ?? 0).toFixed(0)}
                  </td>
                  <td>{r.trade_plan?.stop ?? "—"}</td>
                  <td>{r.trade_plan?.target_1 ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
