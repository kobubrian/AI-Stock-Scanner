DAILY_SCAN_SYSTEM = """You are a short-term trading research assistant. Output valid JSON only.
Rules: verify prices are plausible, flag stale analyst targets, distinguish confirmed news from MOU/hype,
never recommend blind shorts on active squeezes, always include entry/stop/targets and what to avoid."""

TICKER_RESEARCH_SYSTEM = """You are an intraday/overnight trading analyst. Return JSON matching the schema exactly.
Include bull case, bear case, squeeze risk, catalyst quality, stale target warnings, and fragment exit plan."""

TICKER_SCHEMA = {
    "ticker": "string",
    "bias": "long|short|neutral|avoid",
    "timeframe": "scalp|daytrade|overnight|week",
    "long_score": "number 0-100",
    "short_score": "number 0-100",
    "squeeze_risk": "number 0-100",
    "catalyst_quality": "high|medium|low|none",
    "current_price": "number",
    "fair_value_estimate": "string",
    "entry_zone": "string",
    "stop_loss": "number",
    "targets": ["number"],
    "action_tree": "string",
    "key_risks": ["string"],
    "news_summary": "string",
    "valuation_summary": "string",
    "confidence": "low|medium|high",
    "avoid_reason": "string or null",
}


def build_ticker_prompt(snapshot: dict, account: dict) -> str:
    return f"""Analyze {snapshot.get('ticker')} at price {snapshot.get('price')}.
Change: {snapshot.get('percent_change')}%
VWAP status: {'above' if snapshot.get('above_vwap') else 'below' if snapshot.get('above_vwap') is False else 'unknown'}
RVOL: {snapshot.get('relative_volume')}
Scores: long={snapshot.get('scores', {}).get('long_score')}, short={snapshot.get('scores', {}).get('short_score')}, squeeze={snapshot.get('scores', {}).get('squeeze_risk')}
Catalysts: {snapshot.get('catalysts', [])}
Trade plan: {snapshot.get('trade_plan', {})}

Account: balance={account.get('balance')}, PDT restricted={account.get('pdt_restricted')}, max risk={account.get('max_risk')}

Return JSON with fields: {list(TICKER_SCHEMA.keys())}"""
