"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clearPriceCache, mergeCachedPrices, storePricesFromRows } from "../lib/priceCache";
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
  active_session?: string;
  price_as_of?: string | null;
  regular_close?: number | null;
  afterhours_price?: number | null;
  overnight_price?: number | null;
  premarket_price?: number | null;
  market_price?: number | null;
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

export function Dashboard() {
  const [tab, setTab] = useState<TabId>("live");
  const [rows, setRows] = useState<Snapshot[]>([]);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [regime, setRegime] = useState<Record<string, unknown> | null>(null);
  const [alerts, setAlerts] = useState<Array<Record<string, string>>>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [loadingPrices, setLoadingPrices] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanLimit, setScanLimit] = useState(50);
  const [displayLimit, setDisplayLimit] = useState(100);
  const [maxScan, setMaxScan] = useState(2000);
  const [newsMax, setNewsMax] = useState(100);
  const [minVolume, setMinVolume] = useState(100_000);
  const [minMarketCap, setMinMarketCap] = useState(50_000_000);
  const [lastScanCount, setLastScanCount] = useState(0);
  const [scannedAt, setScannedAt] = useState<string | null>(null);
  const [pricesUpdatedAt, setPricesUpdatedAt] = useState<string | null>(null);
  const [regimeLoading, setRegimeLoading] = useState(false);
  const tabRef = useRef(tab);
  const displayRef = useRef(displayLimit);
  const tabCacheRef = useRef<
    Partial<Record<TabId, { rows: Snapshot[]; at: number; limit: number }>>
  >({});
  tabRef.current = tab;
  displayRef.current = displayLimit;

  const TAB_CACHE_MS = 5 * 60 * 1000;

  const loadFiltered = async (
    kind: TabId,
    limit: number,
    opts?: { live?: boolean; force?: boolean }
  ): Promise<Snapshot[]> => {
    const live = opts?.live ?? false;
    const qs = new URLSearchParams({
      kind,
      limit: String(limit),
    });
    if (live) {
      qs.set("live_prices", "true");
      if (opts?.force) qs.set("force_prices", "true");
    }
    const m = await fetchJson<unknown>(apiUrl(`/api/scanners/live?${qs}`), []);
    let list = Array.isArray(m) ? (m as Snapshot[]) : [];
    if (!live) list = mergeCachedPrices(list);
    if (live && list.length) storePricesFromRows(list);
    return list;
  };

  const loadRegime = useCallback(async () => {
    const r = await fetchJson<Record<string, unknown>>(apiUrl("/api/regime"), {});
    setRegime(r);
  }, []);

  const loadStatus = useCallback(async () => {
    const [h, a, limits, meta] = await Promise.all([
      fetchJson<Record<string, unknown> | null>(apiUrl("/health"), null),
      fetchJson<unknown[]>(apiUrl("/api/alerts?limit=10"), []),
      fetchJson<{
        scan_max_symbols?: number;
        scan_news_max_symbols?: number;
        scan_min_daily_volume?: number;
        scan_min_market_cap?: number;
      }>(apiUrl("/api/scanners/limits"), {}),
      fetchJson<{ symbol_count?: number; scanned_at?: string | null }>(
        apiUrl("/api/scanners/meta"),
        {}
      ),
    ]);
    setHealth(h);
    setAlerts(Array.isArray(a) ? (a as Array<Record<string, string>>) : []);
    if (limits.scan_max_symbols) setMaxScan(limits.scan_max_symbols);
    if (limits.scan_news_max_symbols) setNewsMax(limits.scan_news_max_symbols);
    if (limits.scan_min_daily_volume) setMinVolume(limits.scan_min_daily_volume);
    if (limits.scan_min_market_cap) setMinMarketCap(limits.scan_min_market_cap);
    const count = meta.symbol_count ?? 0;
    setLastScanCount(count);
    setScannedAt(meta.scanned_at ?? null);
    if (!h) setError("Cannot reach the API. Start the backend on port 8000.");
    return { count, meta };
  }, []);

  const applyTabView = async (
    kind: TabId,
    limit: number,
    hasScan?: boolean,
    opts?: { live?: boolean; force?: boolean }
  ) => {
    const live = opts?.live ?? false;
    const cached = tabCacheRef.current[kind];
    if (
      !live &&
      cached &&
      cached.limit === limit &&
      Date.now() - cached.at < TAB_CACHE_MS
    ) {
      setRows(mergeCachedPrices(cached.rows));
      const scanned = hasScan ?? lastScanCount > 0;
      if (cached.rows.length > 0) setError(null);
      return cached.rows.length;
    }

    if (live) setLoadingPrices(true);
    let list: Snapshot[] = [];
    try {
      list = await loadFiltered(kind, limit, opts);
      setRows(list);
      tabCacheRef.current[kind] = { rows: list, at: Date.now(), limit };
    } finally {
      if (live) setLoadingPrices(false);
    }
    const n = list.length;
    const scanned = hasScan ?? lastScanCount > 0;
    if (n === 0) {
      if (!scanned) {
        setError("No scan yet — set symbol count and click Run scan.");
      } else {
        setError(
          `No tickers in ${TABS.find((t) => t.id === kind)?.label ?? kind} for this tab — try Live Movers or run a new scan.`
        );
      }
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
      const res = await fetch(
        apiUrl(
          `/api/scanners/refresh-prices?kind=${tabRef.current}&limit=${displayRef.current}&force=true`
        ),
        { method: "POST" }
      );
      if (!res.ok) throw new Error("refresh failed");
      const list = (await res.json()) as Snapshot[];
      storePricesFromRows(list);
      setRows(list);
      tabCacheRef.current[tabRef.current] = {
        rows: list,
        at: Date.now(),
        limit: displayRef.current,
      };
      setPricesUpdatedAt(new Date().toISOString());
    } catch {
      if (!opts?.silent) setError("Price refresh failed.");
    } finally {
      if (!opts?.silent) setRefreshingPrices(false);
    }
  };

  // Mount only — load API status; no scan, no price refresh until you click a button
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const { count } = await loadStatus();
      if (cancelled) return;
      setRows([]);
      if (count > 0) {
        setError("Cached scan available — click Run scan or switch tabs to load the list.");
      } else {
        setError("No scan yet — set symbol count and click Run scan.");
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadStatus]);

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
    tabCacheRef.current = {};
    clearPriceCache();
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
      const prevCount = lastScanCount;
      const prevScannedAt = scannedAt;
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const meta = await fetchJson<{
          symbol_count?: number;
          scanned_at?: string | null;
        }>(apiUrl("/api/scanners/meta"), {});
        const count = meta.symbol_count ?? 0;
        const scanned = meta.scanned_at ?? null;
        const finished =
          scanned &&
          (scanned !== prevScannedAt || (count > 0 && count !== prevCount));
        if (finished) {
          setLastScanCount(count);
          setScannedAt(scanned);
          const n = await applyTabView(tab, displayLimit, count > 0, { live: true });
          if (n === 0 && count === 0) {
            setError(
              "Scan finished with 0 tickers. Confirm ALPACA_API_KEY and FINNHUB_API_KEY in .env, restart the backend, then scan again. Filters: vol ≥ 100k (when volume known), cap ≥ $50M (when cap known)."
            );
          }
          return;
        }
      }
      setError("Scan still running or timed out — wait and click a tab to reload.");
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

  const loadRegimeClick = async () => {
    setRegimeLoading(true);
    try {
      await loadRegime();
    } finally {
      setRegimeLoading(false);
    }
  };

  const busy = loading || scanning || refreshingPrices || loadingPrices;

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

      <section style={{ marginBottom: "1rem" }}>
        <button
          type="button"
          onClick={loadRegimeClick}
          disabled={regimeLoading || busy}
          style={{
            padding: "0.35rem 0.75rem",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--muted)",
            cursor: "pointer",
            fontSize: "0.85rem",
          }}
        >
          {regimeLoading ? "Loading regime quotes…" : "Load SPY/QQQ regime strip (optional)"}
        </button>
        {regime && Array.isArray((regime as { items?: unknown[] }).items) && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem",
              marginTop: "0.75rem",
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
          </div>
        )}
      </section>

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
          {scanLimit > newsMax ? ` · news skipped above ${newsMax}` : ""}
          {` · vol ≥ ${(minVolume / 1000).toFixed(0)}k · cap ≥ $${(minMarketCap / 1_000_000).toFixed(0)}M`}
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

      {loadingPrices && (
        <p style={{ color: "var(--muted)", marginBottom: "0.75rem", fontSize: "0.9rem" }}>
          Fetching live prices from Alpaca…
        </p>
      )}

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
          {refreshingPrices ? "Updating prices…" : "Update prices now"}
        </button>
      </div>

      <MoversTable
        rows={rows}
        onRunScan={runScan}
        loading={scanning}
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
