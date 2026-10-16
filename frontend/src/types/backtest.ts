export type BacktestResponse = {
    engine?: 'python'
    data_info?: { source: 'yahoo' | 'ibkr'; price_basis: string; first_date: string; last_date: string; bar_count: number; fetched_at: string; warnings: string[] } | null
    run_id?: string
    completed_at?: string
    summary: Record<string, number | null>
    equity: {
        date: string
        strategy: number
        benchmark: number
    }[]
    trades: {
        entry_date: string
        exit_date: string
        entry_price: number
        exit_price: number
        holding_period: number
        net_return: number
    }[]
}
