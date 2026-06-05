export const BACKEND_BASE_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

export type AgentStatus = "idle" | "running" | "completed" | "failed" | "warning" | "skipped";

export interface HealthResponse {
  status: string;
  app: string;
  time: string;
  event_types: string[];
}

export interface PublicConfig {
  data: {
    mode: string;
    offline_data_path: string;
    dynamic_universe_limit: number;
    has_tushare_token: boolean;
  };
  portfolio: {
    initial_capital: number;
    commission_rate: number;
    stamp_tax_rate: number;
    slippage_rate: number;
  };
  risk: {
    max_position_per_stock: number;
    max_total_position: number;
    stop_loss_pct: number;
    max_volatility: number;
    min_turnover: number;
  };
  llm: {
    base_url: string;
    has_api_key: boolean;
    default_model: string;
    request_profile: string;
    max_tokens: number;
    timeout_seconds: number;
    max_retries: number;
    has_user_agent: boolean;
  };
  notification: {
    enabled: boolean;
    channels: string[];
    smtp_host: string;
    smtp_port: number;
    has_smtp_username: boolean;
    has_smtp_password: boolean;
    has_email_from: boolean;
    has_email_to: boolean;
    has_webhook_url: boolean;
  };
  storage: {
    mongo_uri: string;
    mongo_db: string;
    mongo_timeout_ms: number;
    redis_url: string;
  };
  scheduler: {
    enabled: boolean;
    timezone: string;
    daily_run_time: string;
    stop_loss_interval_minutes: number;
    notify_after_daily_run: boolean;
    max_count: number;
    history_days: number;
    output_dir: string;
    models: string[];
  };
}

export interface ConfigResponse {
  status: string;
  config: PublicConfig;
}

export interface FlowNodeData {
  label: string;
  status: AgentStatus;
  description: string;
  metrics: Record<string, unknown>;
}

export interface FlowNode {
  id: string;
  position: { x: number; y: number };
  data: FlowNodeData;
  type: string;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  animated: boolean;
  label: string;
}

export interface FlowResponse {
  status: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface DecisionLogStep {
  id: string;
  agent_id: string;
  title: string;
  summary: string;
  status: AgentStatus;
  started_at: string;
  finished_at: string;
  details: Record<string, unknown>;
}

export interface DecisionLogEntry {
  id: string;
  run_id: string;
  timestamp: string;
  agent_id: string;
  llm_model: string;
  stock_code: string;
  stock_name: string;
  action: string;
  confidence: number;
  position_size: number;
  summary: string;
  reasons: string[];
  risks: string[];
  steps: DecisionLogStep[];
  raw: Record<string, unknown>;
}

export interface DecisionLogResponse {
  status: string;
  items: DecisionLogEntry[];
  next_steps: string[];
}

export interface HoldingRow {
  agent_id: string;
  llm_model: string;
  stock_code: string;
  stock_name: string;
  shares: number;
  cost_basis: number;
  current_price: number;
  market_value: number;
  unrealized_return: number;
}

export interface StockCandidate {
  stock_code: string;
  stock_name: string;
  sector: string;
  score: number;
  action: string;
  confidence: number;
  reasons: string[];
  risks: string[];
}

export interface TradeRow {
  agent_id: string;
  llm_model: string;
  date: string;
  stock_code: string;
  stock_name: string;
  side: string;
  price: number;
  shares: number;
  amount: number;
  realized_pnl: number;
  reason: string;
}

export interface StockBoardResponse {
  status: string;
  holdings: HoldingRow[];
  candidates: StockCandidate[];
  trades: TradeRow[];
}

export interface EquityMetricPoint {
  date: string;
  agent_id: string;
  llm_model: string;
  equity: number;
  cash: number;
  daily_pnl: number;
  total_return: number;
  max_drawdown: number;
}

export interface EquityMetricsResponse {
  status: string;
  series: EquityMetricPoint[];
  next_steps: string[];
}

export interface RankingRow {
  rank: number;
  agent_id: string;
  llm_model: string;
  total_return: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  equity: number;
  cash: number;
  daily_pnl: number;
  skipped_execution: boolean;
  skip_reason: string;
}

export interface RankingsResponse {
  status: string;
  rankings: RankingRow[];
}

export interface RunStatusResponse {
  status: string;
  run: {
    run_id?: string;
    status?: string;
    started_at?: string;
    finished_at?: string;
    task_name?: string;
    message?: string;
    request?: Record<string, unknown>;
  } | null;
}

export interface BackendEvent {
  type: string;
  timestamp: string;
  run_id: string;
  agent_id: string;
  payload: Record<string, unknown>;
}

export interface ConfigDraft {
  data: {
    mode: string;
    offline_data_path: string;
    dynamic_universe_limit: number;
    tushare_token: string;
    has_tushare_token: boolean;
  };
  portfolio: {
    initial_capital: number;
  };
  risk: {
    max_position_per_stock: number;
    max_total_position: number;
    stop_loss_pct: number;
  };
  llm: {
    base_url: string;
    api_key: string;
    has_api_key: boolean;
    default_model: string;
    request_profile: string;
    max_tokens: number;
    timeout_seconds: number;
    max_retries: number;
  };
  scheduler: {
    enabled: boolean;
    daily_run_time: string;
    max_count: number;
    history_days: number;
    notify_after_daily_run: boolean;
    models_text: string;
  };
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BACKEND_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function getWebSocketUrl(): string {
  const url = new URL(BACKEND_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/events";
  return url.toString();
}

export function createConfigDraft(config: PublicConfig): ConfigDraft {
  return {
    data: {
      mode: config.data.mode,
      offline_data_path: config.data.offline_data_path,
      dynamic_universe_limit: config.data.dynamic_universe_limit,
      tushare_token: "",
      has_tushare_token: config.data.has_tushare_token,
    },
    portfolio: {
      initial_capital: config.portfolio.initial_capital,
    },
    risk: {
      max_position_per_stock: config.risk.max_position_per_stock,
      max_total_position: config.risk.max_total_position,
      stop_loss_pct: config.risk.stop_loss_pct,
    },
    llm: {
      base_url: config.llm.base_url,
      api_key: "",
      has_api_key: config.llm.has_api_key,
      default_model: config.llm.default_model,
      request_profile: config.llm.request_profile,
      max_tokens: config.llm.max_tokens,
      timeout_seconds: config.llm.timeout_seconds,
      max_retries: config.llm.max_retries,
    },
    scheduler: {
      enabled: config.scheduler.enabled,
      daily_run_time: config.scheduler.daily_run_time,
      max_count: config.scheduler.max_count,
      history_days: config.scheduler.history_days,
      notify_after_daily_run: config.scheduler.notify_after_daily_run,
      models_text: config.scheduler.models.join(", "),
    },
  };
}

export function configDraftToPayload(draft: ConfigDraft): Record<string, unknown> {
  return {
    data: {
      mode: draft.data.mode,
      offline_data_path: draft.data.offline_data_path,
      dynamic_universe_limit: draft.data.dynamic_universe_limit,
      ...(draft.data.tushare_token.trim() ? { tushare_token: draft.data.tushare_token.trim() } : {}),
    },
    portfolio: {
      initial_capital: draft.portfolio.initial_capital,
    },
    risk: {
      max_position_per_stock: draft.risk.max_position_per_stock,
      max_total_position: draft.risk.max_total_position,
      stop_loss_pct: draft.risk.stop_loss_pct,
    },
    llm: {
      base_url: draft.llm.base_url,
      default_model: draft.llm.default_model,
      request_profile: draft.llm.request_profile,
      max_tokens: draft.llm.max_tokens,
      timeout_seconds: draft.llm.timeout_seconds,
      max_retries: draft.llm.max_retries,
      ...(draft.llm.api_key.trim() ? { api_key: draft.llm.api_key.trim() } : {}),
    },
    scheduler: {
      enabled: draft.scheduler.enabled,
      daily_run_time: draft.scheduler.daily_run_time,
      max_count: draft.scheduler.max_count,
      history_days: draft.scheduler.history_days,
      notify_after_daily_run: draft.scheduler.notify_after_daily_run,
      models: draft.scheduler.models_text
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    },
  };
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/api/health");
}

export async function getConfig(): Promise<ConfigResponse> {
  return fetchJson<ConfigResponse>("/api/config");
}

export async function saveConfig(config: Record<string, unknown>): Promise<ConfigResponse> {
  return fetchJson<ConfigResponse>("/api/config", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export async function getFlow(): Promise<FlowResponse> {
  return fetchJson<FlowResponse>("/api/agents/flow");
}

export async function getDecisions(): Promise<DecisionLogResponse> {
  return fetchJson<DecisionLogResponse>("/api/decisions");
}

export async function getStockBoard(): Promise<StockBoardResponse> {
  return fetchJson<StockBoardResponse>("/api/stocks/board");
}

export async function getEquity(): Promise<EquityMetricsResponse> {
  return fetchJson<EquityMetricsResponse>("/api/metrics/equity");
}

export async function getRankings(): Promise<RankingsResponse> {
  return fetchJson<RankingsResponse>("/api/metrics/rankings");
}

export async function getRunStatus(): Promise<RunStatusResponse> {
  return fetchJson<RunStatusResponse>("/api/runs/current");
}

export async function startAutoInvestment(payload: {
  offline: boolean;
  max_count?: number;
  days?: number;
}): Promise<{ status: string; run_id: string }> {
  return fetchJson<{ status: string; run_id: string }>("/api/auto-investment", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

