import type { ObservationPoint } from '../types'
import type { MetricKey } from '../components/VolatilityChart'

export type IntradayCandle = {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  count: number
  comparableKey: string | null
}

/** Aggregate observed indicator values into OHLC candles; no stock price data is involved. */
export function aggregateIntradayCandles(points: ObservationPoint[], metric: MetricKey, intervalMinutes: number): IntradayCandle[] {
  const duration = intervalMinutes * 60_000
  if (!Number.isInteger(intervalMinutes) || intervalMinutes <= 0) return []
  const candles: IntradayCandle[] = []
  const sorted = [...points].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
  for (const point of sorted) {
    const time = Date.parse(point.timestamp)
    const value = point[metric]
    if (!Number.isFinite(time) || typeof value !== 'number' || !Number.isFinite(value)) continue
    const timestamp = Math.floor(time / duration) * duration
    const previous = candles.at(-1)
    if (previous?.timestamp === timestamp && previous.comparableKey === (point.comparable_key ?? null)) {
      previous.high = Math.max(previous.high, value)
      previous.low = Math.min(previous.low, value)
      previous.close = value
      previous.count++
    } else if (previous?.timestamp === timestamp) {
      // A changed calculation basis cannot be represented by one candle.
      candles[candles.length - 1] = { timestamp, open: value, high: value, low: value, close: value, count: 1, comparableKey: point.comparable_key ?? null }
    } else {
      candles.push({ timestamp, open: value, high: value, low: value, close: value, count: 1, comparableKey: point.comparable_key ?? null })
    }
  }
  return candles
}
