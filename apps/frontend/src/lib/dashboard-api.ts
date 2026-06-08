const DEFAULT_BACKEND_BASE_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:18080").replace(/\/+$/, "");
const BACKEND_PORT_START = 18080;
const BACKEND_PORT_END = 18100;
const LEGACY_BACKEND_PORT_START = 8000;
const LEGACY_BACKEND_PORT_END = 8020;
const BACKEND_DISCOVERY_ATTEMPTS = 30;
const BACKEND_DISCOVERY_DELAY_MS = 500;
const BACKEND_PROBE_TIMEOUT_MS = 350;

export const BACKEND_BASE_URL = DEFAULT_BACKEND_BASE_URL;

let resolvedBackendBaseUrl: string | null = null;
let backendDiscoveryPromise: Promise<string> | null = null;

export type BackendProbeStatus = "pending" | "ok" | "http_error" | "invalid_response" | "network_error" | "timeout";

export interface BackendDiscoveryCandidateResult {
  url: string;
  status: BackendProbeStatus;
  checkedAt: string;
  httpStatus?: number;
  statusText?: string;
  app?: string;
  responseStatus?: string;
  errorType?: string;
  errorMessage?: string;
}

export interface BackendDiscoveryDiagnostics {
  configuredBaseUrl: string;
  resolvedBaseUrl: string | null;
  currentCandidate: string | null;
  lastSuccessfulCandidate: string | null;
  lastError: BackendDiscoveryCandidateResult | null;
  candidates: BackendDiscoveryCandidateResult[];
  nextSteps: string[];
  attempts: number;
  updatedAt: string;
}

let backendDiscoveryDiagnostics: BackendDiscoveryDiagnostics = {
  configuredBaseUrl: DEFAULT_BACKEND_BASE_URL,
  resolvedBaseUrl: null,
  currentCandidate: null,
  lastSuccessfulCandidate: null,
  lastError: null,
  candidates: [],
  nextSteps: ["确认后端已经通过 start.bat / start.ps1 启动，默认监听 18080-18100。"],
  attempts: 0,
  updatedAt: new Date().toISOString(),
};

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
  [key: string]: unknown;
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

export interface EventTimelineItem {
  id: string;
  timestamp: string;
  source: string;
  category: string;
  severity: "info" | "warning" | "critical";
  title: string;
  summary: string;
  stock_code: string;
  url: string;
  payload: Record<string, unknown>;
}

export interface EventTimelineResponse {
  status: string;
  items: EventTimelineItem[];
  next_steps: string[];
}

export interface AgentMemoryCase {
  id: string;
  agent_id: string;
  llm_model: string;
  stock_code: string;
  stock_name: string;
  decision_date: string;
  action: string;
  reason: string;
  outcome: string;
  pnl_pct: number;
  tags: string[];
  raw: Record<string, unknown>;
}

export interface AgentMemoryResponse {
  status: string;
  agent_id: string;
  items: AgentMemoryCase[];
  next_steps: string[];
}

export interface AgentToolDefinition {
  agent_id: string;
  agent_name: string;
  tools: string[];
  data_sources: string[];
  skills: string[];
  notes: string;
}

export interface AgentToolsResponse {
  status: string;
  items: AgentToolDefinition[];
}

export interface LlmConfigCheckResponse {
  status: string;
  configured: boolean;
  base_url: string;
  default_model: string;
  request_profile: string;
  models: string[];
  diagnostics: string[];
  warnings: string[];
  bench?: Record<string, unknown> | null;
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function buildBackendCandidates(): string[] {
  const candidates = new Set<string>([DEFAULT_BACKEND_BASE_URL]);

  try {
    const defaultUrl = new URL(DEFAULT_BACKEND_BASE_URL);
    const appendPortRange = (start: number, end: number) => {
      for (let port = start; port <= end; port += 1) {
        const candidate = new URL(defaultUrl.toString());
        candidate.port = String(port);
        candidate.pathname = "";
        candidate.search = "";
        candidate.hash = "";
        candidates.add(candidate.toString().replace(/\/+$/, ""));
      }
    };

    appendPortRange(BACKEND_PORT_START, BACKEND_PORT_END);
    appendPortRange(LEGACY_BACKEND_PORT_START, LEGACY_BACKEND_PORT_END);
  } catch {
    // Keep the configured backend URL as the only candidate if parsing fails.
  }

  return Array.from(candidates);
}

function backendDiscoveryNextSteps(lastError: BackendDiscoveryCandidateResult | null, resolvedBaseUrl: string | null): string[] {
  if (resolvedBaseUrl) {
    return ["后端 HTTP 健康检查已通过；如果 WebSocket 未连接，请确认 /ws/events 未被代理或安全软件拦截。"];
  }

  if (!lastError) {
    return ["确认后端已经通过 start.bat / start.ps1 启动，默认监听 18080-18100。"];
  }

  if (lastError.status === "http_error") {
    return [
      `候选后端 ${lastError.url} 返回 HTTP ${lastError.httpStatus ?? "未知"}，请确认该端口运行的是本项目 FastAPI 后端。`,
      "如果前端端口被旧项目占用，请停止旧前端或使用 start.bat 重新启动本项目。",
    ];
  }

  if (lastError.status === "invalid_response") {
    return [
      `候选后端 ${lastError.url} 有响应但不是 AStock 后端健康包，请检查是否被其他本地服务占用。`,
      "建议关闭占用端口的旧项目，或通过 NEXT_PUBLIC_BACKEND_URL 指向正确后端。",
    ];
  }

  if (lastError.status === "timeout") {
    return ["后端健康检查超时，请确认 sidecar/FastAPI 已完成启动，并检查本机防火墙或安全软件。"];
  }

  return [
    "未能连接任何候选后端，请先运行 start.bat 或 start.ps1。",
    "如果后端使用自定义端口，请设置 NEXT_PUBLIC_BACKEND_URL 后重启前端。",
  ];
}

function updateBackendDiscoveryDiagnostics(update: Partial<BackendDiscoveryDiagnostics>): void {
  const nextDiagnostics = {
    ...backendDiscoveryDiagnostics,
    ...update,
    updatedAt: new Date().toISOString(),
  };
  nextDiagnostics.nextSteps = backendDiscoveryNextSteps(nextDiagnostics.lastError, nextDiagnostics.resolvedBaseUrl);
  backendDiscoveryDiagnostics = nextDiagnostics;
}

function rememberBackendProbeResult(result: BackendDiscoveryCandidateResult): void {
  const previous = backendDiscoveryDiagnostics.candidates.filter((item) => item.url !== result.url);
  const candidates = [result, ...previous].slice(0, 12);
  updateBackendDiscoveryDiagnostics({
    candidates,
    currentCandidate: result.url,
    lastError: result.status === "ok" ? backendDiscoveryDiagnostics.lastError : result,
    lastSuccessfulCandidate: result.status === "ok" ? result.url : backendDiscoveryDiagnostics.lastSuccessfulCandidate,
    resolvedBaseUrl: result.status === "ok" ? result.url : backendDiscoveryDiagnostics.resolvedBaseUrl,
  });
}

function describeFetchError(error: unknown): Pick<BackendDiscoveryCandidateResult, "status" | "errorType" | "errorMessage"> {
  if (error instanceof DOMException && error.name === "AbortError") {
    return { status: "timeout", errorType: "AbortError", errorMessage: "健康检查超时" };
  }
  if (error instanceof Error) {
    return { status: "network_error", errorType: error.name, errorMessage: error.message };
  }
  return { status: "network_error", errorType: "UnknownError", errorMessage: "未知网络错误" };
}

function recordBackendFetchFailure(baseUrl: string, error: unknown): void {
  const errorInfo = describeFetchError(error);
  resolvedBackendBaseUrl = null;
  rememberBackendProbeResult({
    url: baseUrl,
    checkedAt: new Date().toISOString(),
    ...errorInfo,
  });
  updateBackendDiscoveryDiagnostics({ resolvedBaseUrl: null });
}

export function getBackendDiscoveryDiagnostics(): BackendDiscoveryDiagnostics {
  return {
    ...backendDiscoveryDiagnostics,
    candidates: backendDiscoveryDiagnostics.candidates.map((item) => ({ ...item })),
    nextSteps: [...backendDiscoveryDiagnostics.nextSteps],
    lastError: backendDiscoveryDiagnostics.lastError ? { ...backendDiscoveryDiagnostics.lastError } : null,
  };
}

async function probeBackendBaseUrl(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), BACKEND_PROBE_TIMEOUT_MS);
  updateBackendDiscoveryDiagnostics({ currentCandidate: baseUrl, attempts: backendDiscoveryDiagnostics.attempts + 1 });
  try {
    const response = await fetch(`${baseUrl}/api/health`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      rememberBackendProbeResult({
        url: baseUrl,
        status: "http_error",
        checkedAt: new Date().toISOString(),
        httpStatus: response.status,
        statusText: response.statusText,
      });
      return false;
    }

    const payload = (await response.json()) as Partial<HealthResponse>;
    const appName = typeof payload.app === "string" ? payload.app.toLowerCase() : "";
    const healthy = payload.status === "ok" && appName.includes("astock") && Array.isArray(payload.event_types);
    rememberBackendProbeResult({
      url: baseUrl,
      status: healthy ? "ok" : "invalid_response",
      checkedAt: new Date().toISOString(),
      httpStatus: response.status,
      statusText: response.statusText,
      app: typeof payload.app === "string" ? payload.app : undefined,
      responseStatus: typeof payload.status === "string" ? payload.status : undefined,
      errorType: healthy ? undefined : "UnexpectedHealthPayload",
      errorMessage: healthy ? undefined : "健康检查响应不是 AStock 后端格式",
    });
    return healthy;
  } catch (error) {
    rememberBackendProbeResult({
      url: baseUrl,
      checkedAt: new Date().toISOString(),
      ...describeFetchError(error),
    });
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function discoverBackendBaseUrl(): Promise<string | null> {
  for (const candidate of buildBackendCandidates()) {
    if (await probeBackendBaseUrl(candidate)) {
      return candidate;
    }
  }
  return null;
}

export async function getBackendBaseUrl(): Promise<string> {
  if (resolvedBackendBaseUrl) {
    updateBackendDiscoveryDiagnostics({
      resolvedBaseUrl: resolvedBackendBaseUrl,
      lastSuccessfulCandidate: resolvedBackendBaseUrl,
    });
    return resolvedBackendBaseUrl;
  }

  if (backendDiscoveryPromise) {
    return backendDiscoveryPromise;
  }

  backendDiscoveryPromise = (async () => {
    for (let attempt = 0; attempt < BACKEND_DISCOVERY_ATTEMPTS; attempt += 1) {
      const discovered = await discoverBackendBaseUrl();
      if (discovered) {
        resolvedBackendBaseUrl = discovered;
        updateBackendDiscoveryDiagnostics({
          resolvedBaseUrl: discovered,
          lastSuccessfulCandidate: discovered,
          currentCandidate: discovered,
        });
        return discovered;
      }
      await sleep(BACKEND_DISCOVERY_DELAY_MS);
    }

    updateBackendDiscoveryDiagnostics({
      resolvedBaseUrl: null,
      currentCandidate: DEFAULT_BACKEND_BASE_URL,
    });
    return DEFAULT_BACKEND_BASE_URL;
  })().finally(() => {
    backendDiscoveryPromise = null;
  });

  return backendDiscoveryPromise;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const backendBaseUrl = await getBackendBaseUrl();
  let response: Response;
  try {
    response = await fetch(`${backendBaseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (error) {
    recordBackendFetchFailure(backendBaseUrl, error);
    throw error;
  }

  if (!response.ok) {
    resolvedBackendBaseUrl = null;
    rememberBackendProbeResult({
      url: backendBaseUrl,
      status: "http_error",
      checkedAt: new Date().toISOString(),
      httpStatus: response.status,
      statusText: response.statusText,
      errorType: "HttpError",
      errorMessage: `${response.status} ${response.statusText}`,
    });
    updateBackendDiscoveryDiagnostics({ resolvedBaseUrl: null });
    throw new Error(`${response.status} ${response.statusText}`);
  }
  resolvedBackendBaseUrl = backendBaseUrl;
  updateBackendDiscoveryDiagnostics({
    resolvedBaseUrl: backendBaseUrl,
    lastSuccessfulCandidate: backendBaseUrl,
    currentCandidate: backendBaseUrl,
  });
  return (await response.json()) as T;
}

export async function getWebSocketUrl(): Promise<string> {
  const url = new URL(await getBackendBaseUrl());
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

export async function getEventTimeline(): Promise<EventTimelineResponse> {
  return fetchJson<EventTimelineResponse>("/api/events/timeline");
}

export async function pollEvents(): Promise<EventTimelineResponse> {
  return fetchJson<EventTimelineResponse>("/api/events/poll", { method: "POST" });
}

export async function getAgentTools(): Promise<AgentToolsResponse> {
  return fetchJson<AgentToolsResponse>("/api/agents/tools");
}

export async function getAgentMemory(agentId: string): Promise<AgentMemoryResponse> {
  return fetchJson<AgentMemoryResponse>(`/api/agents/${encodeURIComponent(agentId)}/memory`);
}

export async function testLlmConfig(config: Record<string, unknown>, models?: string[]): Promise<LlmConfigCheckResponse> {
  return fetchJson<LlmConfigCheckResponse>("/api/config/test-llm", {
    method: "POST",
    body: JSON.stringify({ config, models, run_bench: false, limit: 8 }),
  });
}

export async function startAutoInvestment(payload: {
  offline: boolean;
  max_count?: number;
  days?: number;
  models?: string[];
}): Promise<{ status: string; run_id: string }> {
  return fetchJson<{ status: string; run_id: string }>("/api/auto-investment", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
