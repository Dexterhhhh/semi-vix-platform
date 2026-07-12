export type SVIXPoint = { timestamp: string; svix: number; core: number; memory: number; ai: number; calculation_quality: number }
export type Components = { core: number; memory: number; ai: number }
export type CalculationJob = { id: number; type: string; start_date: string; end_date: string; frequency: 'daily' | 'weekly'; status: string; progress: number; result_summary?: { records_calculated: number }; created_at: string; started_at?: string; finished_at?: string; error_message?: string }
export type DashboardSettings = { refresh_frequency_minutes: number; selected_symbols: string[]; manual_component_weights?: Record<string, number> }
export type SystemStatus = { database: string; market_data: string; svix_engine: string; worker: string; last_calculation?: string }
