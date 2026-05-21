"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MoversTable } from "./MoversTable";

const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const TABS = [
  { id: "live", label: "Live Movers" },
  { id: "long", label: "Long Watch" },
  { id: "short", label: "Short Watch" },
  { id: "squeeze", label: "Squeeze Watch" },
  { id: "overnight_long", label: "Overnight Long" },
  { id: "overnight_short", label: "Overnight Short" },
] as const;

type TabId = (typeof TABS)[number]["id"];

type Snapshot = {
  ticker: string;
  price: number;
  percent_change: number;
  relative_volume: number;
  above_vwap?: boolean | null;
  session?: string;
  price_as_of?: string | null;
  scores: { long_score: number; short_score: number; squeeze_risk: number };
  trade_plan: { stop?: number | null; target_1?: number | null };
  data_available: boolean;
};

function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API ? `${API}${p}` : p;
}

async function fetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

function isPriceStale(iso: string | null | undefined, maxSec = 120): boolean {
  if (!iso) return true;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return true;
  return Date.now() - t > maxSec * 1000;
}

export function Dashboard() {
  const [tab, setTab] = useState<TabId>("live");
  const [rows, setRows] = useState<Snapshot[]>([]);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [regime, setRegime] = useState<Record<string, unknown> | null>(null);
  const [alerts, setAlerts] = useState<Array<Record<string, string>>>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanLimit, setScanLimit] = useState(50);
  const [displayLimit, setDisplayLimit] = useState(100);
  const [maxScan, setMaxScan] = useState(2000);
  const [newsMax, setNewsMax] = useState(100);
  const [lastScanCount, setLastScanCount] = useState(0);
  const [scannedAt, setScannedAt] = useState<string | null>(null);
  const [pricesUpdatedAt, setPricesUpdatedAt] = useState<string | null>(null);
  const [newestPriceAsOf, setNewestPriceAsOf] = useState<string | null>(null);
  const tabRef = useRef(tab);
  const displayRef = useRef(displayLimit);
  tabRef.current = tab;
  displayRef.current = displayLimit;

  const loadFiltered = async (kind: TabId, limit: number) => {
    const m = await fetchJson<unknown>(
      apiUrl(`/api/scanners/live?kind=${kind}&limit=${limit}`),
      []
    );
    const list = Array.isArray(m) ? (m as Snapshot[]) : [];
    setRows(list);
    return list.length;
  };

  const loadStatus = useCallback(async () => {
    const [h, r, a, limits, meta] = await Promise.all([
      fetchJson<Record<string, unknown> | null>(apiUrl("/health"), null),
      fetchJson<Record<string, unknown>>(apiUrl("/api/regime"), {}),
      fetchJson<unknown[]>(apiUrl("/api/alerts?limit=10"), []),
      fetchJson<{ scan_max_symbols?: number; scan_news_max_symbols?: number }>(
        apiUrl("/api/scanners/limits"),
        {}
      ),
      fetchJson<{ symbol_count?: number; scanned_at?: string | null; prices_updated_at?: string | null; newest_price_as_of?: string | null }>(
        apiUrl("/api/scanners/meta"),
        {}
      ),
    ]);
    setHealth(h);
    setRegime(r);
    setAlerts(Array.isArray(a) ? (a as Array<Record<string, string>>) : []);
    if (limits.scan_max_symbols) setMaxScan(limits.scan_max_symbols);
    if (limits.scan_news_max_symbols) setNewsMax(limits.scan_news_max_symbols);
    const count = meta.symbol_count ?? 0;
    setLastScanCount(count);
    setScannedAt(meta.scanned_at ?? null);
    setPricesUpdatedAt(meta.prices_updated_at ?? null);
    setNewestPriceAsOf(meta.newest_price_as_of ?? null);
    if (!h) setError("Cannot reach the API. Start the backend on port 8000.");
    return { count, meta };
  }, []);

  const applyTabView = async (kind: TabId, limit: number) => {
    const n = await loadFiltered(kind, limit);
    if (n === 0) {
      setError(
        `No tickers in ${TABS.find((t) => t.id === kind)?.label ?? kind} — run a scan or try another tab.`
      );
    } else {
      setError(null);
    }
    return n;
  };

  const refreshPrices = async (opts?: { silent?: boolean }) => {
    if (lastScanCount === 0) {
      if (!opts?.silent) setError("Run a scan first, then refresh prices.");
      return;
    }
    if (!opts?.silent) setRefreshingPrices(true);
    if (!opts?.silent) setError(null);
    try {
      await fetch(
        apiUrl(`/api/scanners/refresh-prices?kind=${tabRef.current}&limit=${displayRef.current}`),
        { method: "POST" }
      );
      await applyTabView(tabRef.current, displayRef.current);
      const meta = await fetchJson<{
        scanned_at?: string | null;
        prices_updated_at?: string | null;
        newest_price_as_of?: string | null;
      }>(apiUrl("/api/scanners/meta"), {});
      setScannedAt(meta.scanned_at ?? null);
      setPricesUpdatedAt(meta.prices_updated_at ?? null);
      setNewestPriceAsOf(meta.newest_price_as_of ?? null);
    } catch {
      if (!opts?.silent) setError("Price refresh failed.");
    } finally {
      if (!opts?.silent) setRefreshingPrices(false);
    }
  };

  // Mount only — no auto-scan; refresh quotes if cache is stale
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const { count, meta } = await loadStatus();
      if (cancelled) return;
      if (count > 0) {
        await applyTabView(tabRef.current, displayRef.current);
        const stale =
          isPriceStale(meta.prices_updated_at) || isPriceStale(meta.newest_price_as_of);
        if (stale && !cancelled) {
          await refreshPrices({ silent: true });
        }
      } else {
        setRows([]);
        setError("No scan yet — set symbol count and click Run scan.");
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadStatus]);

  // Keep prices current while dashboard is open (every 60s)
  useEffect(() => {
    if (lastScanCount === 0) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible" && !scanning) {
        refreshPrices({ silent: true });
      }
    }, 60_000);
    return () => window.clearInterval(id);
  }, [lastScanCount, scanning]);

  const handleTabChange = (id: TabId) => {
    setTab(id);
    if (lastScanCount > 0) {
      applyTabView(id, displayLimit);
    }
  };

  const handleDisplayLimitChange = (n: number) => {
    setDisplayLimit(n);
    if (lastScanCount > 0) {
      applyTabView(tab, n);
    }
  };

  const runScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const res = await fetch(
        apiUrl(`/api/scanners/run?limit=${Math.min(scanLimit, maxScan)}`),
        { method: "POST" }
      );
      const body = await res.json();
      if (!res.ok || body.status === "error") {
        setError(body.message || "Scan failed to start");
        return;
      }
      const prev = lastScanCount;
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const meta = await fetchJson<{
          symbol_count?: number;
          scanned_at?: string | null;
          prices_updated_at?: string | null;
          newest_price_as_of?: string | null;
        }>(apiUrl("/api/scanners/meta"), {});
        const count = meta.symbol_count ?? 0;
        if (count > 0 && count !== prev) {
          setLastScanCount(count);
          setScannedAt(meta.scanned_at ?? null);
          setPricesUpdatedAt(meta.prices_updated_at ?? null);
          setNewestPriceAsOf(meta.newest_price_as_of ?? null);
          await applyTabView(tab, displayLimit);
          setError(null);
          return;
        }
      }
      setError("Scan still running or timed out — try Refresh prices in a minute.");
    } catch {
      setError("Run scan failed — is the backend running?");
    } finally {
      setScanning(false);
    }
  };

  const exportForAI = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        apiUrl(`/api/export/ai-pack?limit=${Math.min(scanLimit, maxScan)}`),
        { method: "POST" }
      );
      const data = await res.json();
      alert(
        data.files
          ? `Export saved:\n${data.files.json}\n${data.files.markdown}`
          : JSON.stringify(data)
      );
    } catch {
      alert("Export failed — is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const busy = loading || scanning || refreshingPrices;

  return (
    <div>
      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        <strong>API status</strong>
        <pre style={{ margin: "0.5rem 0 0", fontSize: "0.8rem" }}>
          {health ? JSON.stringify(health, null, 2) : "Backend offline"}
        </pre>
      </section>

      {regime && Array.isArray((regime as { items?: unknown[] }).items) && (
        <section
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          {((regime as { items: Array<Record<string, unknown>> }).items || []).map((item) => (
            <div
              key={String(item.symbol)}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "0.5rem 0.75rem",
                fontSize: "0.8rem",
              }}
            >
              <strong>{String(item.symbol)}</strong>{" "}
              {item.data_available
                ? `${item.price} (${Number(item.change_pct).toFixed(1)}%)`
                : "no data"}
            </div>
          ))}
        </section>
      )}

      <section
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          alignItems: "center",
          marginBottom: "1rem",
          fontSize: "0.9rem",
        }}
      >
        <label>
          Scan symbols:{" "}
          <input
            type="number"
            min={1}
            max={maxScan}
            value={scanLimit}
            onChange={(e) => setScanLimit(Number(e.target.value) || 50)}
            style={{
              width: 80,
              padding: "0.25rem 0.5rem",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--text)",
            }}
          />
          <span style={{ color: "var(--muted)", marginLeft: 6 }}>max {maxScan}</span>
        </label>
        <label>
          Show rows:{" "}
          <input
            type="number"
            min={1}
            max={500}
            value={displayLimit}
            onChange={(e) => handleDisplayLimitChange(Number(e.target.value) || 100)}
            style={{
              width: 70,
              padding: "0.25rem 0.5rem",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              color: "var(--text)",
            }}
          />
        </label>
        <span style={{ color: "var(--muted)" }}>
          Last scan: {lastScanCount} symbols
          {scannedAt ? ` · scanned ${new Date(scannedAt).toLocaleString()}` : ""}
          {pricesUpdatedAt ? ` · prices ${new Date(pricesUpdatedAt).toLocaleTimeString()}` : ""}
          {isPriceStale(pricesUpdatedAt) || isPriceStale(newestPriceAsOf) ? " · stale" : ""}
          {scanLimit > newsMax ? ` · news skipped above ${newsMax}` : ""}
        </span>
      </section>

      <nav style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1rem" }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => handleTabChange(t.id)}
            style={{
              padding: "0.35rem 0.75rem",
              background: tab === t.id ? "var(--accent)" : "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              color: tab === t.id ? "#fff" : "var(--muted)",
              cursor: "pointer",
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error && (
        <p style={{ color: "var(--warn)", marginBottom: "0.75rem", fontSize: "0.9rem" }}>
          {error}
        </p>
      )}

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        <button
          type="button"
          onClick={exportForAI}
          disabled={busy}
          style={{
            padding: "0.5rem 1rem",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--text)",
            cursor: "pointer",
          }}
        >
          Export for ChatGPT
        </button>
        <button
          type="button"
          onClick={() => refreshPrices()}
          disabled={busy || lastScanCount === 0}
          style={{
            padding: "0.5rem 1rem",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--text)",
            cursor: "pointer",
          }}
        >
          {refreshingPrices ? "Refreshing prices…" : "Refresh prices"}
        </button>
      </div>

      <MoversTable
        rows={rows}
        onRefresh={runScan}
        loading={busy}
        scanLabel={scanning ? `Scanning ${scanLimit}…` : `Run scan (${scanLimit})`}
      />

      {alerts.length > 0 && (
        <section style={{ marginTop: "1.5rem" }}>
          <h3 style={{ fontSize: "1rem" }}>Recent alerts</h3>
          <ul style={{ paddingLeft: "1.25rem", color: "var(--muted)" }}>
            {alerts.map((a) => (
              <li key={a.id}>
                [{a.alert_type}] {a.symbol}: {a.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
