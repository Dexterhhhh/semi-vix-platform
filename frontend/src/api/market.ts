export type StockQuote = { symbol: string; timestamp: string; price: number | null; bid: number | null; ask: number | null; volume: number | null; provider: 'IBKR' | 'FUTU'; delayed: boolean | null }
export type OptionQuote = { contract_id: string; symbol: string; expiry: string; strike: number; option_type: 'C' | 'P'; timestamp: string; bid: number | null; ask: number | null; last: number | null; volume: number | null; open_interest: number | null; implied_volatility: number | null; provider: 'IBKR' | 'FUTU'; delayed: boolean | null }

// Phase 2 type boundary only. Collection endpoints are intentionally deferred.
