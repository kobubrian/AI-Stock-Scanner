/** Client-side quote cache — instant tab switches without re-fetching every ticker. */

export type PriceFields = {
  price: number;
  percent_change: number;
  previous_close?: number;
  session?: string;
  active_session?: string;
  price_as_of?: string | null;
  price_session?: string;
  regular_close?: number | null;
  afterhours_price?: number | null;
  afterhours_percent_change?: number | null;
  premarket_price?: number | null;
  overnight_price?: number | null;
  market_price?: number | null;
  data_available?: boolean;
};

const TTL_MS = 5 * 60 * 1000;
const priceByTicker = new Map<string, { at: number; fields: PriceFields }>();

export function mergeCachedPrices<T extends { ticker: string }>(rows: T[]): T[] {
  if (priceByTicker.size === 0) return rows;
  return rows.map((row) => {
    const hit = priceByTicker.get(row.ticker.toUpperCase());
    if (!hit || Date.now() - hit.at > TTL_MS) return row;
    return { ...row, ...hit.fields };
  });
}

export function storePricesFromRows(rows: Array<{ ticker: string } & PriceFields>) {
  const now = Date.now();
  for (const r of rows) {
    if (!r.ticker || !r.price) continue;
    priceByTicker.set(r.ticker.toUpperCase(), {
      at: now,
      fields: {
        price: r.price,
        percent_change: r.percent_change,
        previous_close: r.previous_close,
        session: r.session,
        active_session: r.active_session,
        price_as_of: r.price_as_of,
        price_session: r.price_session,
        regular_close: r.regular_close,
        afterhours_price: r.afterhours_price,
        afterhours_percent_change: r.afterhours_percent_change,
        premarket_price: r.premarket_price,
        overnight_price: r.overnight_price,
        market_price: r.market_price,
        data_available: r.data_available ?? true,
      },
    });
  }
}

export function clearPriceCache() {
  priceByTicker.clear();
}
