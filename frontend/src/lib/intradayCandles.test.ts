import { describe, expect, it } from 'vitest'
import type { ObservationPoint } from '../types'
import { aggregateIntradayCandles } from './intradayCandles'

const point = (minute: number, value: number | null, comparable_key = 'v1'): ObservationPoint => ({
  timestamp: new Date(Date.UTC(2026, 8, 29, 13, minute)).toISOString(),
  svix: value, core: value, memory: value, ai: value,
  calculation_quality: 1, estimated: true, status: 'FREE_ESTIMATE', coverage: 1, cached_coverage: 0,
  component_counts: {}, reasons: {}, details: {}, comparable_key,
})

describe('aggregateIntradayCandles', () => {
  it('builds OHLC from chronological valid observations and retains missing intervals', () => {
    const candles = aggregateIntradayCandles([point(33, 25), point(31, 23), point(34, 24), point(32, 26), point(37, null), point(41, 22)], 'svix', 5)
    expect(candles).toMatchObject([
      { open: 23, high: 26, low: 23, close: 24, count: 4 },
      { open: 22, high: 22, low: 22, close: 22, count: 1 },
    ])
    expect(candles[1].timestamp - candles[0].timestamp).toBe(10 * 60_000)
  })

  it('does not mix calculation methods within a candle', () => {
    const candles = aggregateIntradayCandles([point(31, 23), point(32, 26, 'v2'), point(33, 27, 'v2')], 'svix', 5)
    expect(candles).toMatchObject([{ open: 26, high: 27, low: 26, close: 27, count: 2, comparableKey: 'v2' }])
  })
})
