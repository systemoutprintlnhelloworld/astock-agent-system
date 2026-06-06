"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  Activity,
  ArrowUpRight,
  BellRing,
  Bot,
  CandlestickChart,
  Cpu,
  Database,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
  Wifi,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  BACKEND_BASE_URL,
  type AgentStatus,
  type BackendEvent,
  type ConfigDraft,
  configDraftToPayload,
  createConfigDraft,
  getAgentMemory,
  getAgentTools,
  getBackendBaseUrl,
  getConfig,
  getDecisions,
  getEquity,
  getEventTimeline,
  getFlow,
  getHealth,
  getRankings,
  getRunStatus,
  getStockBoard,
  getWebSocketUrl,
  pollEvents,
  saveConfig,
  startAutoInvestment,
  testLlmConfig,
  type AgentMemoryCase,
  type DecisionLogEntry,
  type EquityMetricPoint,
  type EventTimelineItem,
  type FlowNodeData,
  type HealthResponse,
  type HoldingRow,
  type AgentToolDefinition,
  type LlmConfigCheckResponse,
  type RankingRow,
  type RunStatusResponse,
  type StockCandidate,
  type TradeRow,
} from "@/lib/dashboard-api";
import { cn, formatDateTime, formatMoney, formatNumber, formatPercent } from "@/lib/utils";

type StockTab = "holdings" | "candidates" | "trades";
type DashboardTab = "overview" | "flow" | "performance" | "events" | "logs" | "stocks" | "agents" | "settings";
type SettingSectionId = "data" | "llm" | "portfolio" | "risk" | "scheduler";
type ConnectionState = "connecting" | "connected" | "disconnected";

type LiveNodeState = {
  status: AgentStatus;
  description: string;
  progress?: number;
};

const DASHBOARD_TABS: Array<{
  id: DashboardTab;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    id: "overview",
    label: "总览",
    description: "面向小白的首页，汇总当前状态、候选股票和模型表现。",
    icon: Cpu,
  },
  {
    id: "flow",
    label: "流程",
    description: "专门查看多 Agent 流程图、节点状态和当前编排链路。",
    icon: Sparkles,
  },
  {
    id: "performance",
    label: "表现",
    description: "聚焦权益曲线、长期收益与模型排行榜。",
    icon: BellRing,
  },
  {
    id: "events",
    label: "事件",
    description: "展示交易时间、公告、新闻和系统事件如何进入 Agent 输入流。",
    icon: Wifi,
  },
  {
    id: "logs",
    label: "日志",
    description: "集中浏览可折叠决策日志和 WebSocket 事件流。",
    icon: Activity,
  },
  {
    id: "stocks",
    label: "股票",
    description: "查看当前持仓、候选股票和交易记录。",
    icon: CandlestickChart,
  },
  {
    id: "agents",
    label: "智能体",
    description: "查看每个 Agent 的工具、数据源、技能和按模型隔离的记忆入口。",
    icon: Bot,
  },
  {
    id: "settings",
    label: "设置",
    description: "通过目录快速跳转到数据源、LLM、风控和调度配置。",
    icon: Database,
  },
];

const SETTINGS_SECTIONS: Array<{
  id: SettingSectionId;
  label: string;
  description: string;
}> = [
  { id: "data", label: "数据源", description: "切换 offline / online、路径和 Tushare Token。" },
  { id: "llm", label: "LLM", description: "网关、模型、API Key 和请求参数。" },
  { id: "portfolio", label: "组合", description: "初始资金等组合级参数。" },
  { id: "risk", label: "风控", description: "仓位上限和止损阈值。" },
  { id: "scheduler", label: "调度", description: "每日时间、通知和模型列表。" },
];

const FALLBACK_FLOW_NODES = [
  { id: "data_agent", position: { x: 0, y: 120 }, data: { label: "数据 Agent", status: "idle", description: "采集行情与财务数据", metrics: {} }, type: "agentNode" },
  { id: "screener", position: { x: 220, y: 120 }, data: { label: "股票筛选", status: "idle", description: "动态筛选候选股票池", metrics: {} }, type: "agentNode" },
  { id: "technical_analyst", position: { x: 460, y: 0 }, data: { label: "技术分析", status: "idle", description: "评估形态、趋势和动量", metrics: {} }, type: "agentNode" },
  { id: "fundamental_analyst", position: { x: 460, y: 120 }, data: { label: "基本面分析", status: "idle", description: "评估财务健康度与估值", metrics: {} }, type: "agentNode" },
  { id: "sentiment_analyst", position: { x: 460, y: 240 }, data: { label: "舆情分析", status: "idle", description: "跟踪市场热点与消息面", metrics: {} }, type: "agentNode" },
  { id: "debate_room", position: { x: 720, y: 120 }, data: { label: "多 Agent 讨论", status: "idle", description: "汇总争议并生成共识", metrics: {} }, type: "agentNode" },
  { id: "risk_manager", position: { x: 960, y: 120 }, data: { label: "风控检查", status: "idle", description: "检查仓位、止损和波动风险", metrics: {} }, type: "agentNode" },
  { id: "portfolio_manager", position: { x: 1200, y: 120 }, data: { label: "组合执行", status: "idle", description: "输出买卖动作与持仓调整", metrics: {} }, type: "agentNode" },
];

const FALLBACK_FLOW_EDGES = [
  ["data_agent", "screener"],
  ["screener", "technical_analyst"],
  ["screener", "fundamental_analyst"],
  ["screener", "sentiment_analyst"],
  ["technical_analyst", "debate_room"],
  ["fundamental_analyst", "debate_room"],
  ["sentiment_analyst", "debate_room"],
  ["debate_room", "risk_manager"],
  ["risk_manager", "portfolio_manager"],
].map(([source, target]) => ({ id: `${source}-${target}`, source, target, animated: true, label: "" }));

const nodeTypes = {
  agentNode: AgentNodeCard,
};

export function TradingDashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [backendBaseUrl, setBackendBaseUrl] = useState(BACKEND_BASE_URL);
  const [configDraft, setConfigDraft] = useState<ConfigDraft | null>(null);
  const [flowNodes, setFlowNodes] = useState(FALLBACK_FLOW_NODES);
  const [flowEdges, setFlowEdges] = useState(FALLBACK_FLOW_EDGES);
  const [decisions, setDecisions] = useState<DecisionLogEntry[]>([]);
  const [holdings, setHoldings] = useState<HoldingRow[]>([]);
  const [candidates, setCandidates] = useState<StockCandidate[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [equitySeries, setEquitySeries] = useState<EquityMetricPoint[]>([]);
  const [rankings, setRankings] = useState<RankingRow[]>([]);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [liveEvents, setLiveEvents] = useState<BackendEvent[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<EventTimelineItem[]>([]);
  const [agentTools, setAgentTools] = useState<AgentToolDefinition[]>([]);
  const [memoryCases, setMemoryCases] = useState<AgentMemoryCase[]>([]);
  const [selectedMemoryAgent, setSelectedMemoryAgent] = useState("");
  const [llmCheck, setLlmCheck] = useState<LlmConfigCheckResponse | null>(null);
  const [stockTab, setStockTab] = useState<StockTab>("holdings");
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
  const [nodeStateMap, setNodeStateMap] = useState<Record<string, LiveNodeState>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [running, setRunning] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [pollingTimeline, setPollingTimeline] = useState(false);
  const [loadingMemory, setLoadingMemory] = useState(false);
  const [checkingLlm, setCheckingLlm] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const configDirtyRef = useRef(false);

  const setConfigDirtyState = useCallback((dirty: boolean) => {
    configDirtyRef.current = dirty;
    setConfigDirty(dirty);
  }, []);

  const refreshDashboard = useCallback(async () => {
    setRefreshing(true);
    try {
      const [healthData, configData, flowData, decisionsData, boardData, equityData, rankingsData, currentRun, timelineData, toolsData, backendUrl] = await Promise.all([
        getHealth(),
        getConfig(),
        getFlow(),
        getDecisions(),
        getStockBoard(),
        getEquity(),
        getRankings(),
        getRunStatus(),
        getEventTimeline(),
        getAgentTools(),
        getBackendBaseUrl(),
      ]);

      setHealth(healthData);
      setFlowNodes(flowData.nodes.length ? flowData.nodes : FALLBACK_FLOW_NODES);
      setFlowEdges(flowData.edges.length ? flowData.edges : FALLBACK_FLOW_EDGES);
      setDecisions(decisionsData.items);
      setHoldings(boardData.holdings);
      setCandidates(boardData.candidates);
      setTrades(boardData.trades);
      setEquitySeries(equityData.series);
      setRankings(rankingsData.rankings);
      setRunStatus(currentRun);
      setTimelineEvents(timelineData.items);
      setAgentTools(toolsData.items);
      setBackendBaseUrl(backendUrl);
      setErrorMessage(null);
      setConfigDraft((current) => (current && configDirtyRef.current ? current : createConfigDraft(configData.config)));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "无法连接后端服务");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  const handleEvent = useCallback(
    (event: BackendEvent) => {
      if (event.type === "run_started") {
        setRunning(true);
        setNodeStateMap({});
        setRunStatus({ status: "running", run: { run_id: event.run_id, status: "running", started_at: event.timestamp } });
        return;
      }

      if (["agent_started", "agent_step", "agent_completed", "risk_checked"].includes(event.type) && event.agent_id) {
        const status = eventTypeToStatus(event.type);
        const description = typeof event.payload.message === "string" ? event.payload.message : event.agent_id;
        const progress = typeof event.payload.progress === "number" ? event.payload.progress : undefined;
        setNodeStateMap((current) => ({
          ...current,
          [event.agent_id]: {
            status,
            description,
            progress,
          },
        }));
        return;
      }

      if (event.type === "run_completed" || event.type === "run_failed") {
        setRunning(false);
        void refreshDashboard();
        return;
      }

      if (event.type === "config_updated") {
        setConfigDirtyState(false);
        void refreshDashboard();
      }

      if (event.type === "timeline_event") {
        const payload = event.payload as Partial<EventTimelineItem>;
        if (payload.id && payload.title) {
          setTimelineEvents((current) => [payload as EventTimelineItem, ...current.filter((item) => item.id !== payload.id)].slice(0, 60));
        }
      }

      if (event.type === "llm_checked") {
        setLlmCheck(event.payload as unknown as LlmConfigCheckResponse);
      }
    },
    [refreshDashboard, setConfigDirtyState],
  );

  const updateConfigSection = useCallback(
    <K extends keyof ConfigDraft>(section: K, patch: Partial<ConfigDraft[K]>) => {
      setConfigDirtyState(true);
      setConfigDraft((current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          [section]: {
            ...current[section],
            ...patch,
          },
        } as ConfigDraft;
      });
    },
    [setConfigDirtyState],
  );

  const jumpToSettingsSection = useCallback((sectionId: SettingSectionId) => {
    setActiveTab("settings");
    window.setTimeout(() => {
      document.getElementById(`settings-${sectionId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 40);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshDashboard();
  }, [refreshDashboard]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let heartbeat: number | undefined;
    let reconnectTimer: number | undefined;
    let disposed = false;

    const connect = () => {
      void (async () => {
        let websocketUrl: string;
        try {
          const backendUrl = await getBackendBaseUrl();
          websocketUrl = await getWebSocketUrl();
          setBackendBaseUrl(backendUrl);
        } catch {
          setConnectionState("disconnected");
          if (!disposed) {
            reconnectTimer = window.setTimeout(() => {
              connect();
            }, 3000);
          }
          return;
        }

        if (disposed) {
          return;
        }

        socket = new WebSocket(websocketUrl);

        socket.onopen = () => {
          setConnectionState("connected");
          void refreshDashboard();
          heartbeat = window.setInterval(() => {
            if (socket?.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "ping", payload: { source: "frontend" } }));
            }
          }, 15000);
        };

        socket.onmessage = (message) => {
          try {
            const event = JSON.parse(message.data) as BackendEvent;
            setLiveEvents((current) => [event, ...current].slice(0, 40));
            handleEvent(event);
          } catch {
            // Ignore malformed frames from dev servers.
          }
        };

        socket.onerror = () => {
          setConnectionState("disconnected");
        };

        socket.onclose = () => {
          setConnectionState("disconnected");
          if (heartbeat) {
            window.clearInterval(heartbeat);
            heartbeat = undefined;
          }
          if (!disposed) {
            reconnectTimer = window.setTimeout(() => {
              connect();
            }, 3000);
          }
        };
      })();
    };

    connect();

    return () => {
      disposed = true;
      if (heartbeat) {
        window.clearInterval(heartbeat);
      }
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [handleEvent, refreshDashboard]);

  const mergedNodes = useMemo<Node<FlowNodeData>[]>(() => {
    return flowNodes.map((node) => {
      const live = nodeStateMap[node.id];
      return {
        ...node,
        data: {
          ...node.data,
          status: live?.status || node.data.status,
          description: live?.description || node.data.description,
          metrics: {
            ...node.data.metrics,
            ...(typeof live?.progress === "number" ? { progress: live.progress } : {}),
          },
        },
        type: "agentNode",
      };
    });
  }, [flowNodes, nodeStateMap]);

  const mergedEdges = useMemo<Edge[]>(() => {
    return flowEdges.map((edge) => ({
      ...edge,
      type: "smoothstep",
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: "#4f46e5" },
      style: { stroke: "#6366f1", strokeWidth: 1.6 },
    }));
  }, [flowEdges]);

  const topRanking = rankings[0] ?? null;
  const liveDecisionCount = decisions.length;
  const totalMarketValue = holdings.reduce((sum, row) => sum + row.market_value, 0);
  const activeTabMeta = DASHBOARD_TABS.find((tab) => tab.id === activeTab) ?? DASHBOARD_TABS[0];
  const setupChecklist = [
    {
      label: "后端接口已连通",
      done: Boolean(health),
      detail: health ? "健康检查已返回，可继续配置和运行。" : "等待 /api/health 返回。",
    },
    {
      label: "实时事件已接通",
      done: connectionState === "connected",
      detail: connectionState === "connected" ? "WebSocket 已建立，可以实时看 Agent 状态。" : "当前还未连上事件流。",
    },
    {
      label: "Tushare Token 已准备",
      done: Boolean(configDraft?.data.has_tushare_token || configDraft?.data.tushare_token.trim()),
      detail: configDraft?.data.has_tushare_token ? "当前配置中已存在 Tushare Token。" : "在线模式前请先补齐 Tushare Token。",
    },
    {
      label: "LLM 密钥已准备",
      done: Boolean(configDraft?.llm.has_api_key || configDraft?.llm.api_key.trim()),
      detail: configDraft?.llm.has_api_key ? "当前配置中已存在 API Key。" : "在线模式前请先补齐 API Key。",
    },
    {
      label: "比赛模型已配置",
      done: Boolean(configDraft?.scheduler.models_text.trim()),
      detail: configDraft?.scheduler.models_text.trim() ? `当前模型：${configDraft?.scheduler.models_text.trim()}` : "请先填写至少一个模型或 rule-baseline。",
    },
  ];

  const handleRun = async (offline: boolean) => {
    if (!configDraft) {
      return;
    }

    setRunning(true);
    setErrorMessage(null);
    try {
      await startAutoInvestment({
        offline,
        max_count: configDraft.scheduler.max_count,
        days: configDraft.scheduler.history_days,
        models: configDraft.scheduler.models_text
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      });
    } catch (error) {
      setRunning(false);
      setErrorMessage(error instanceof Error ? error.message : "启动自动投资失败");
    }
  };

  const handleSaveConfig = async () => {
    if (!configDraft) {
      return;
    }

    setSavingConfig(true);
    try {
      const response = await saveConfig(configDraftToPayload(configDraft));
      setConfigDraft(createConfigDraft(response.config));
      setConfigDirtyState(false);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "保存配置失败");
    } finally {
      setSavingConfig(false);
    }
  };

  const handlePollTimeline = async () => {
    setPollingTimeline(true);
    try {
      const response = await pollEvents();
      setTimelineEvents(response.items);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "事件轮询失败");
    } finally {
      setPollingTimeline(false);
    }
  };

  const handleCheckLlm = async () => {
    if (!configDraft) {
      return;
    }
    setCheckingLlm(true);
    try {
      const models = configDraft.scheduler.models_text
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await testLlmConfig(configDraftToPayload(configDraft), models);
      setLlmCheck(response);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "LLM 配置检测失败");
    } finally {
      setCheckingLlm(false);
    }
  };

  const handleLoadMemory = async (agentId: string) => {
    if (!agentId) {
      return;
    }
    setLoadingMemory(true);
    setSelectedMemoryAgent(agentId);
    try {
      const response = await getAgentMemory(agentId);
      setMemoryCases(response.items);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Agent 记忆读取失败");
    } finally {
      setLoadingMemory(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(99,102,241,0.18),_transparent_28%),linear-gradient(180deg,_#020617_0%,_#0f172a_45%,_#111827_100%)] text-slate-100">
      <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-6 px-6 py-6 lg:px-10">
        <header className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20 backdrop-blur-xl">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-400/30 bg-indigo-500/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.3em] text-indigo-200">
                <Sparkles className="h-3.5 w-3.5" />
                A 股 LLM 投资系统
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-white md:text-4xl">面向小白的多智能体投资控制台</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300 md:text-base">
                  在一个界面里完成配置、启动自动投资、观察多 Agent 流程图、查看实时日志、股票看板和长期曲线。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
                <StatusPill icon={connectionState === "connected" ? Wifi : WifiOff} tone={connectionState === "connected" ? "success" : "warning"}>
                  {connectionState === "connected" ? "WebSocket 已连接" : connectionState === "connecting" ? "WebSocket 连接中" : "WebSocket 未连接"}
                </StatusPill>
                <StatusPill icon={Cpu} tone={runStatus?.status === "running" || running ? "info" : "neutral"}>
                  {runStatus?.status === "running" || running ? "自动投资运行中" : "等待新的投资轮次"}
                </StatusPill>
                <span className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-slate-300">后端地址：{backendBaseUrl}</span>
                {health ? <span className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-slate-300">后端时间：{formatDateTime(health.time)}</span> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
                  onClick={() => jumpToSettingsSection("llm")}
                >
                  快速跳到 LLM 设置
                </button>
                <button
                  type="button"
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
                  onClick={() => jumpToSettingsSection("risk")}
                >
                  快速跳到风控设置
                </button>
                <button
                  type="button"
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
                  onClick={() => jumpToSettingsSection("scheduler")}
                >
                  快速跳到调度设置
                </button>
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-end">
              <ActionButton onClick={() => void refreshDashboard()} busy={refreshing} icon={RefreshCw} variant="secondary">
                刷新仪表盘
              </ActionButton>
              <ActionButton onClick={() => void handleRun(true)} busy={running} icon={Play}>
                启动离线轮次
              </ActionButton>
              <ActionButton onClick={() => void handleRun(false)} busy={running} icon={ArrowUpRight}>
                启动在线轮次
              </ActionButton>
            </div>
          </div>

          {errorMessage ? (
            <div className="mt-4 rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              无法完全获取后端数据：{errorMessage}。控制台会持续尝试重连，你也可以在后端启动后手动点击“刷新仪表盘”。
            </div>
          ) : null}
          {loading ? (
            <div className="mt-4 rounded-2xl border border-sky-400/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-100">
              正在从后端加载流程图、配置、日志和股票看板。即使接口还没全部返回，你也可以先浏览当前控制台界面。
            </div>
          ) : null}
        </header>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard icon={Bot} title="活跃决策卡片" value={formatNumber(liveDecisionCount)} caption="可折叠查看评分、风险与 LLM 复核" />
          <MetricCard icon={CandlestickChart} title="当前持仓市值" value={formatMoney(totalMarketValue)} caption={`${holdings.length} 个持仓 / ${trades.length} 条交易`} />
          <MetricCard
            icon={ShieldCheck}
            title="风险参数"
            value={configDraft ? formatPercent(configDraft.risk.stop_loss_pct) : "-"}
            caption={configDraft ? `单票 ${formatPercent(configDraft.risk.max_position_per_stock)} / 总仓 ${formatPercent(configDraft.risk.max_total_position)}` : "等待配置加载"}
          />
          <MetricCard
            icon={Activity}
            title="当前领先模型"
            value={topRanking ? topRanking.llm_model || topRanking.agent_id : "暂无"}
            caption={topRanking ? `累计收益 ${formatPercent(topRanking.total_return)} / 回撤 ${formatPercent(topRanking.max_drawdown)}` : "运行一轮后生成排行榜"}
          />
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/5 p-4 shadow-2xl shadow-black/10 backdrop-blur-xl">
          <div className="flex flex-wrap gap-2">
            {DASHBOARD_TABS.map((tab) => (
              <DashboardTabButton
                key={tab.id}
                icon={tab.icon}
                label={tab.label}
                active={activeTab === tab.id}
                dirty={tab.id === "settings" && configDirty}
                onClick={() => setActiveTab(tab.id)}
              />
            ))}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">{activeTabMeta.description}</p>
        </section>

        {activeTab === "overview" ? (
          <>
            <section className="grid gap-6 xl:grid-cols-[1fr_0.95fr]">
              <Panel title="运行摘要" description="桌面版首页优先展示最关键的当前状态、最近轮次与下一步建议。" icon={Cpu}>
                <div className="space-y-4 text-sm text-slate-200">
                  <SummaryRow label="当前状态" value={runStatus?.status || "idle"} />
                  <SummaryRow label="最近运行 ID" value={runStatus?.run?.run_id || "-"} mono />
                  <SummaryRow label="开始时间" value={formatDateTime(runStatus?.run?.started_at || "")} />
                  <SummaryRow label="完成时间" value={formatDateTime(runStatus?.run?.finished_at || "")} />
                  <SummaryRow label="任务消息" value={runStatus?.run?.message || "等待首次运行"} />
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-xs leading-6 text-slate-300">
                    <p className="font-medium text-white">下一步建议</p>
                    <ol className="mt-2 list-decimal space-y-1 pl-5">
                      <li>先在设置页填好 LLM Base URL、API Key 和模型列表。</li>
                      <li>点击“启动离线轮次”验证整条 UI 接线。</li>
                      <li>确认日志、流程图和股票看板都更新后，再切到在线模式。</li>
                    </ol>
                  </div>
                </div>
              </Panel>

              <Panel title="配置快照" description="把最常看的配置摘要集中在一张卡里，并提供快速跳转到对应设置区。" icon={Database}>
                <div className="grid gap-4 md:grid-cols-2">
                  <SummaryRow label="数据模式" value={configDraft?.data.mode || "-"} />
                  <SummaryRow label="离线数据目录" value={configDraft?.data.offline_data_path || "-"} />
                  <SummaryRow label="默认模型" value={configDraft?.llm.default_model || "-"} />
                  <SummaryRow label="模型列表" value={configDraft?.scheduler.models_text || "-"} />
                  <SummaryRow label="每日运行时间" value={configDraft?.scheduler.daily_run_time || "-"} />
                  <SummaryRow label="计划任务" value={configDraft?.scheduler.enabled ? "已启用" : "未启用"} />
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {SETTINGS_SECTIONS.map((section) => (
                    <QuickJumpButton key={section.id} title={section.label} description={section.description} onClick={() => jumpToSettingsSection(section.id)} />
                  ))}
                </div>
                <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                  <div className="text-sm font-medium text-white">开箱检查清单</div>
                  <p className="mt-1 text-xs leading-5 text-slate-400">让小白用户先确认关键配置是否齐全，再开始第一轮离线或在线验证。</p>
                  <div className="mt-4 grid gap-3">
                    {setupChecklist.map((item) => (
                      <ChecklistItem key={item.label} label={item.label} detail={item.detail} done={item.done} />
                    ))}
                  </div>
                </div>
              </Panel>
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <Panel title="首次启动向导" description="把第一次上手拆成 4 个动作，让小白用户不用在长页面里自己找步骤。" icon={Bot}>
                <div className="grid gap-4 md:grid-cols-2">
                  <GuideStepCard
                    title="先补齐数据源"
                    description="先确认 Tushare Token 和数据模式，避免在线轮次没有行情数据。"
                    badge={setupChecklist[2]?.done ? "已就绪" : "待配置"}
                    done={setupChecklist[2]?.done ?? false}
                    icon={Database}
                    actionLabel="去数据源设置"
                    actionIcon={Database}
                    onAction={() => jumpToSettingsSection("data")}
                  />
                  <GuideStepCard
                    title="再接上 LLM"
                    description="填入网关、API Key 和默认模型，后续排行榜才会出现真实模型账户。"
                    badge={setupChecklist[3]?.done ? "已就绪" : "待配置"}
                    done={setupChecklist[3]?.done ?? false}
                    icon={Sparkles}
                    actionLabel="去 LLM 设置"
                    actionIcon={Sparkles}
                    onAction={() => jumpToSettingsSection("llm")}
                  />
                  <GuideStepCard
                    title="保存当前配置"
                    description="参数保存在运行时覆盖文件中，保存后重启或继续运行都会复用。"
                    badge={configDirty ? "待保存" : "已同步"}
                    done={!configDirty}
                    icon={Save}
                    actionLabel="保存配置"
                    actionIcon={Save}
                    onAction={() => void handleSaveConfig()}
                    busy={savingConfig}
                  />
                  <GuideStepCard
                    title="先跑离线再切在线"
                    description="先用离线轮次确认流程图、日志和股票看板都会刷新，再切到在线模式更稳妥。"
                    badge={runStatus?.status === "running" ? "运行中" : decisions.length > 0 || trades.length > 0 ? "已有结果" : "建议先验证"}
                    done={runStatus?.status === "running" || decisions.length > 0 || trades.length > 0}
                    icon={Play}
                    actionLabel="启动离线轮次"
                    actionIcon={Play}
                    onAction={() => void handleRun(true)}
                    busy={running}
                  />
                </div>
              </Panel>

              <Panel title="推荐操作顺序" description="如果你是第一次使用，这里按从易到难整理了最稳妥的一条体验路径。" icon={ArrowUpRight}>
                <div className="space-y-3">
                  {[
                    "先看开箱检查清单，确认后端、WebSocket、Tushare 和 API Key 是否都已就绪。",
                    "先用“去数据源设置”和“去 LLM 设置”补齐配置，再点击保存配置。",
                    "优先启动离线轮次，确认流程图、日志、股票看板都会联动刷新。",
                    "离线轮次通过后，再切到在线模式并观察排行榜、候选股票和持仓变化。",
                  ].map((item, index) => (
                    <div key={item} className="flex items-start gap-3 rounded-2xl border border-white/10 bg-slate-950/55 px-4 py-3 text-sm text-slate-200">
                      <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-xs font-semibold text-indigo-100">{index + 1}</span>
                      <p className="leading-6">{item}</p>
                    </div>
                  ))}
                </div>
              </Panel>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
              <Panel title="候选股票预览" description="不想翻完整表格时，可以先在总览里快速看今天最值得关注的候选池。" icon={CandlestickChart}>
                <CandidatesTable candidates={candidates.slice(0, 6)} />
              </Panel>
              <Panel title="模型排行榜预览" description="直接查看当前领先账户，判断哪条模型策略近期表现更稳定。" icon={BellRing}>
                <RankingsTable rankings={rankings.slice(0, 6)} />
              </Panel>
            </section>
          </>
        ) : null}

        {activeTab === "flow" ? (
          <section className="grid gap-6 xl:grid-cols-[1.7fr_1fr]">
            <Panel title="实时 Agent 流程图" description="React Flow 可视化多智能体执行链路，边缘始终保持动画，节点会根据 WebSocket 事件切换状态。" icon={Sparkles}>
              <div className="h-[520px] overflow-hidden rounded-2xl border border-white/10 bg-slate-950/70">
                <ReactFlow
                  fitView
                  nodes={mergedNodes}
                  edges={mergedEdges}
                  nodeTypes={nodeTypes}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  proOptions={{ hideAttribution: true }}
                >
                  <MiniMap pannable zoomable style={{ backgroundColor: "rgba(15, 23, 42, 0.92)" }} />
                  <Controls className="!bg-slate-900/80 !text-slate-100" />
                  <Background color="rgba(148, 163, 184, 0.18)" gap={24} />
                </ReactFlow>
              </div>
            </Panel>

            <Panel title="流程事件" description="右侧只保留最新事件，让你在看流程图时同步知道当前卡在哪个 Agent。" icon={Wifi}>
              <EventFeed events={liveEvents.slice(0, 10)} />
            </Panel>
          </section>
        ) : null}

        {activeTab === "performance" ? (
          <section className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
            <Panel title="长期表现曲线" description="Recharts 展示权益曲线、收益率与动态回撤，是后续长期运行监控的主视图。" icon={CandlestickChart}>
              <EquityChart series={equitySeries} />
            </Panel>
            <Panel title="模型排行榜" description="实时比较不同 LLM / 规则基线账户的累计收益、胜率与交易频率。" icon={BellRing}>
              <RankingsTable rankings={rankings} />
            </Panel>
          </section>
        ) : null}

        {activeTab === "events" ? (
          <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <Panel title="事件时间线" description="把交易时间、系统状态、公告、新闻和风险提醒统一成 Agent 可消费的输入流。" icon={Wifi}>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                <div>
                  <div className="text-sm font-medium text-white">混合事件模式</div>
                  <p className="mt-1 text-xs leading-5 text-slate-400">重大事件立即进入 Agent 决策链；普通新闻和公告按批次进入时间线。</p>
                </div>
                <ActionButton onClick={() => void handlePollTimeline()} busy={pollingTimeline} icon={RefreshCw} variant="secondary">
                  手动轮询事件
                </ActionButton>
              </div>
              <EventTimelineList events={timelineEvents} />
            </Panel>
            <Panel title="Agent 输入解释" description="这里说明事件会如何进入后续的舆情、风控和组合决策链。" icon={Bot}>
              <div className="space-y-3 text-sm text-slate-200">
                <SummaryRow label="当前事件数" value={formatNumber(timelineEvents.length)} />
                <SummaryRow label="最新来源" value={timelineEvents[0]?.source || "-"} />
                <SummaryRow label="最新类型" value={timelineEvents[0]?.category || "-"} />
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-xs leading-6 text-slate-300">
                  <p className="font-medium text-white">后续接入方向</p>
                  <ol className="mt-2 list-decimal space-y-1 pl-5">
                    <li>Tushare 公告和 AkShare 新闻会进入同一条时间线。</li>
                    <li>critical / risk 事件会触发更快的 Agent 复核。</li>
                    <li>所有输入会在日志中保留可审计摘要，避免黑盒决策。</li>
                  </ol>
                </div>
              </div>
            </Panel>
          </section>
        ) : null}

        {activeTab === "logs" ? (
          <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <Panel title="决策日志" description="每条卡片都展示动作摘要，可折叠查看评分、风险提示与原始上下文。" icon={Activity}>
              <DecisionLogList decisions={decisions} />
            </Panel>
            <Panel title="实时事件流" description="WebSocket 事件会持续写入这里，便于理解当前到底哪个 Agent 在做什么。" icon={Wifi}>
              <EventFeed events={liveEvents} />
            </Panel>
          </section>
        ) : null}

        {activeTab === "stocks" ? (
          <section className="grid gap-6 xl:grid-cols-[1.4fr_0.6fr]">
            <Panel title="股票看板" description="在持仓、候选股和交易记录之间切换，快速查看买卖动作和盈亏。" icon={CandlestickChart}>
              <div className="mb-4 flex flex-wrap gap-2">
                {([
                  ["holdings", "当前持仓"],
                  ["candidates", "候选股票"],
                  ["trades", "交易记录"],
                ] as const).map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    className={cn(
                      "rounded-full px-4 py-2 text-sm transition",
                      stockTab === tab ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/20" : "bg-white/5 text-slate-300 hover:bg-white/10",
                    )}
                    onClick={() => setStockTab(tab)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {stockTab === "holdings" ? <HoldingsTable holdings={holdings} /> : null}
              {stockTab === "candidates" ? <CandidatesTable candidates={candidates} /> : null}
              {stockTab === "trades" ? <TradesTable trades={trades} /> : null}
            </Panel>

            <Panel title="运行提示" description="股票页旁边固定放一张简短说明卡，方便边看数据边执行操作。" icon={Cpu}>
              <div className="space-y-4 text-sm text-slate-200">
                <SummaryRow label="当前状态" value={runStatus?.status || "idle"} />
                <SummaryRow label="活跃事件数" value={formatNumber(liveEvents.length)} />
                <SummaryRow label="候选股票数" value={formatNumber(candidates.length)} />
                <SummaryRow label="已记录交易" value={formatNumber(trades.length)} />
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-xs leading-6 text-slate-300">
                  <p className="font-medium text-white">查看建议</p>
                  <ol className="mt-2 list-decimal space-y-1 pl-5">
                    <li>先看“当前持仓”确认浮盈浮亏和仓位变化。</li>
                    <li>再看“候选股票”理解今天为什么有新的标的进入池子。</li>
                    <li>最后看“交易记录”确认系统是否真的执行了买卖动作。</li>
                  </ol>
                </div>
              </div>
            </Panel>
          </section>
        ) : null}

        {activeTab === "agents" ? (
          <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
            <Panel title="Agent 工具与技能清单" description="明确每个 Agent 能调用什么工具、依赖哪些数据源，以及在 8 Agent 流水线中的独有职责。" icon={Bot}>
              <AgentToolsList tools={agentTools} />
            </Panel>
            <Panel title="按模型隔离的 Agent 记忆" description="每个模型驱动的系统独立查询自己的历史案例，避免 Benchmark 之间互相污染。" icon={Database}>
              <div className="space-y-4">
                <FormField label="选择 Agent 账户 ID">
                  <select
                    className={inputClassName}
                    value={selectedMemoryAgent}
                    onChange={(event) => void handleLoadMemory(event.target.value)}
                  >
                    <option value="">请选择排行榜中的账户</option>
                    {rankings.map((row) => (
                      <option key={row.agent_id} value={row.agent_id}>
                        {row.llm_model || row.agent_id} / {row.agent_id}
                      </option>
                    ))}
                  </select>
                </FormField>
                {selectedMemoryAgent ? (
                  <ActionButton onClick={() => void handleLoadMemory(selectedMemoryAgent)} busy={loadingMemory} icon={RefreshCw} variant="secondary">
                    刷新记忆案例
                  </ActionButton>
                ) : null}
                <MemoryCaseList cases={memoryCases} loading={loadingMemory} />
              </div>
            </Panel>
          </section>
        ) : null}

        {activeTab === "settings" ? (
          <Panel title="设置中心" description="所有当前可热保存的参数都集中在一个标签页里，并支持通过左侧目录快速跳转。" icon={Database}>
            {configDraft ? (
              <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                    <div className="text-sm font-medium text-white">设置目录</div>
                    <div className="mt-3 space-y-2">
                      {SETTINGS_SECTIONS.map((section) => (
                        <button
                          key={section.id}
                          type="button"
                          className="flex w-full items-start justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-left text-sm text-slate-200 transition hover:bg-white/10"
                          onClick={() => jumpToSettingsSection(section.id)}
                        >
                          <div>
                            <div className="font-medium text-white">{section.label}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-400">{section.description}</div>
                          </div>
                          <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
                    <div className="text-sm font-medium text-white">保存状态</div>
                    <p className="mt-2 text-xs leading-6 text-slate-400">
                      {configDirty ? "你有尚未保存的更改。保存后将同步到运行时覆盖配置。" : "当前配置与后端已同步。"}
                    </p>
                    <div className="mt-4">
                      <ActionButton onClick={() => void handleSaveConfig()} busy={savingConfig} icon={Save}>
                        保存配置
                      </ActionButton>
                    </div>
                  </div>
                </aside>

                <div className="space-y-5">
                  <ConfigGroup id="settings-data" title="数据源与轮次" description="先决定跑 offline 还是 online，再补齐本地数据路径和 Tushare Token。">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="数据模式">
                        <select className={inputClassName} value={configDraft.data.mode} onChange={(event) => updateConfigSection("data", { mode: event.target.value })}>
                          <option value="offline">offline</option>
                          <option value="online">online</option>
                        </select>
                      </FormField>
                      <FormField label="选股池上限">
                        <input
                          className={inputClassName}
                          type="number"
                          value={configDraft.data.dynamic_universe_limit}
                          onChange={(event) => updateConfigSection("data", { dynamic_universe_limit: Number(event.target.value || 0) })}
                        />
                      </FormField>
                    </div>
                    <FormField label="离线数据路径">
                      <input className={inputClassName} value={configDraft.data.offline_data_path} onChange={(event) => updateConfigSection("data", { offline_data_path: event.target.value })} />
                    </FormField>
                    <FormField label={configDraft.data.has_tushare_token ? "Tushare Token（已配置，可覆盖）" : "Tushare Token"}>
                      <input
                        className={inputClassName}
                        type="password"
                        placeholder={configDraft.data.has_tushare_token ? "输入以覆盖当前 token" : "输入 token"}
                        value={configDraft.data.tushare_token}
                        onChange={(event) => updateConfigSection("data", { tushare_token: event.target.value })}
                      />
                    </FormField>
                  </ConfigGroup>

                  <ConfigGroup id="settings-llm" title="LLM 网关与模型" description="这里决定后端连哪个模型网关、默认模型是什么，以及请求时的超时和重试策略。">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="Base URL">
                        <input className={inputClassName} value={configDraft.llm.base_url} onChange={(event) => updateConfigSection("llm", { base_url: event.target.value })} />
                      </FormField>
                      <FormField label={configDraft.llm.has_api_key ? "API Key（已配置，可覆盖）" : "API Key"}>
                        <input
                          className={inputClassName}
                          type="password"
                          placeholder={configDraft.llm.has_api_key ? "输入以覆盖当前 key" : "输入 API key"}
                          value={configDraft.llm.api_key}
                          onChange={(event) => updateConfigSection("llm", { api_key: event.target.value })}
                        />
                      </FormField>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="默认模型">
                        <input className={inputClassName} value={configDraft.llm.default_model} onChange={(event) => updateConfigSection("llm", { default_model: event.target.value })} />
                      </FormField>
                      <FormField label="请求档位 / Profile">
                        <input className={inputClassName} value={configDraft.llm.request_profile} onChange={(event) => updateConfigSection("llm", { request_profile: event.target.value })} />
                      </FormField>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <FormField label="Max Tokens">
                        <input className={inputClassName} type="number" value={configDraft.llm.max_tokens} onChange={(event) => updateConfigSection("llm", { max_tokens: Number(event.target.value || 0) })} />
                      </FormField>
                      <FormField label="超时（秒）">
                        <input
                          className={inputClassName}
                          type="number"
                          value={configDraft.llm.timeout_seconds}
                          onChange={(event) => updateConfigSection("llm", { timeout_seconds: Number(event.target.value || 0) })}
                        />
                      </FormField>
                      <FormField label="最大重试次数">
                        <input className={inputClassName} type="number" value={configDraft.llm.max_retries} onChange={(event) => updateConfigSection("llm", { max_retries: Number(event.target.value || 0) })} />
                      </FormField>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <div className="text-sm font-medium text-white">LLM 防呆检测</div>
                          <p className="mt-1 text-xs leading-5 text-slate-400">只检测当前表单内容，不会在响应里回显 API Key；可自动读取模型列表并给出修正建议。</p>
                        </div>
                        <ActionButton onClick={() => void handleCheckLlm()} busy={checkingLlm} icon={ShieldCheck} variant="secondary">
                          检测 LLM 配置
                        </ActionButton>
                      </div>
                      {llmCheck ? <LlmCheckPanel check={llmCheck} /> : null}
                    </div>
                  </ConfigGroup>

                  <ConfigGroup id="settings-portfolio" title="组合参数" description="用于控制模拟盘的资金规模，方便在不同初始本金下对比策略表现。">
                    <FormField label="初始资金">
                      <input
                        className={inputClassName}
                        type="number"
                        value={configDraft.portfolio.initial_capital}
                        onChange={(event) => updateConfigSection("portfolio", { initial_capital: Number(event.target.value || 0) })}
                      />
                    </FormField>
                  </ConfigGroup>

                  <ConfigGroup id="settings-risk" title="风控参数" description="止损、单票仓位和总仓位建议放在一起看，避免一边改仓位一边忘了风险阈值。">
                    <div className="grid gap-3 sm:grid-cols-3">
                      <FormField label="单票仓位上限">
                        <input
                          className={inputClassName}
                          type="number"
                          step="0.01"
                          value={configDraft.risk.max_position_per_stock}
                          onChange={(event) => updateConfigSection("risk", { max_position_per_stock: Number(event.target.value || 0) })}
                        />
                      </FormField>
                      <FormField label="总仓位上限">
                        <input
                          className={inputClassName}
                          type="number"
                          step="0.01"
                          value={configDraft.risk.max_total_position}
                          onChange={(event) => updateConfigSection("risk", { max_total_position: Number(event.target.value || 0) })}
                        />
                      </FormField>
                      <FormField label="止损比例">
                        <input
                          className={inputClassName}
                          type="number"
                          step="0.01"
                          value={configDraft.risk.stop_loss_pct}
                          onChange={(event) => updateConfigSection("risk", { stop_loss_pct: Number(event.target.value || 0) })}
                        />
                      </FormField>
                    </div>
                  </ConfigGroup>

                  <ConfigGroup id="settings-scheduler" title="调度与模型列表" description="安排每日运行时间、是否自动通知，以及参与比赛的模型名单。">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="每日运行时间">
                        <input className={inputClassName} type="time" value={configDraft.scheduler.daily_run_time} onChange={(event) => updateConfigSection("scheduler", { daily_run_time: event.target.value })} />
                      </FormField>
                      <FormField label="单轮最大股票数">
                        <input
                          className={inputClassName}
                          type="number"
                          value={configDraft.scheduler.max_count}
                          onChange={(event) => updateConfigSection("scheduler", { max_count: Number(event.target.value || 0) })}
                        />
                      </FormField>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="历史回看天数">
                        <input
                          className={inputClassName}
                          type="number"
                          value={configDraft.scheduler.history_days}
                          onChange={(event) => updateConfigSection("scheduler", { history_days: Number(event.target.value || 0) })}
                        />
                      </FormField>
                      <FormField label="模型列表（逗号分隔）">
                        <input className={inputClassName} value={configDraft.scheduler.models_text} onChange={(event) => updateConfigSection("scheduler", { models_text: event.target.value })} />
                      </FormField>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <FormField label="计划任务开关">
                        <label className="flex h-11 items-center gap-3 rounded-xl border border-white/10 bg-slate-950/70 px-4 text-sm text-slate-200">
                          <input type="checkbox" checked={configDraft.scheduler.enabled} onChange={(event) => updateConfigSection("scheduler", { enabled: event.target.checked })} />
                          启用每日自动运行
                        </label>
                      </FormField>
                      <FormField label="每日轮次后通知">
                        <label className="flex h-11 items-center gap-3 rounded-xl border border-white/10 bg-slate-950/70 px-4 text-sm text-slate-200">
                          <input
                            type="checkbox"
                            checked={configDraft.scheduler.notify_after_daily_run}
                            onChange={(event) => updateConfigSection("scheduler", { notify_after_daily_run: event.target.checked })}
                          />
                          运行结束后发送通知
                        </label>
                      </FormField>
                    </div>
                  </ConfigGroup>
                </div>
              </div>
            ) : (
              <EmptyState title="配置尚未加载" description="请先启动 FastAPI 后端，再从 /api/config 读取可编辑设置。" />
            )}
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

function AgentNodeCard({ data }: NodeProps) {
  const nodeData = data as FlowNodeData;
  const progress = typeof nodeData.metrics.progress === "number" ? nodeData.metrics.progress : null;

  return (
    <div
      className={cn(
        "w-52 rounded-2xl border p-4 shadow-2xl backdrop-blur",
        nodeData.status === "running" && "border-indigo-400/60 bg-indigo-500/15 shadow-indigo-500/20",
        nodeData.status === "completed" && "border-emerald-400/50 bg-emerald-500/10 shadow-emerald-500/10",
        nodeData.status === "warning" && "border-amber-400/60 bg-amber-500/10 shadow-amber-500/10",
        nodeData.status === "failed" && "border-rose-400/60 bg-rose-500/10 shadow-rose-500/10",
        nodeData.status === "idle" && "border-white/10 bg-slate-950/85 shadow-black/20",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-white">{nodeData.label}</div>
          <div className="mt-1 text-xs leading-5 text-slate-300">{nodeData.description}</div>
        </div>
        <StatusDot status={nodeData.status} />
      </div>
      <div className="mt-4 space-y-2">
        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-slate-400">
          <span>状态</span>
          <span>{nodeData.status}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              nodeData.status === "running" ? "bg-indigo-400" : nodeData.status === "completed" ? "bg-emerald-400" : "bg-slate-500",
            )}
            style={{ width: `${Math.max(8, Math.round((progress ?? 0.08) * 100))}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function DashboardTabButton({
  active,
  dirty,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  dirty?: boolean;
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-2xl border px-4 py-2.5 text-sm font-medium transition",
        active ? "border-indigo-400/40 bg-indigo-500/15 text-white shadow-lg shadow-indigo-500/15" : "border-white/10 bg-black/10 text-slate-300 hover:bg-white/10",
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
      {dirty ? <span className="h-2 w-2 rounded-full bg-amber-400" /> : null}
    </button>
  );
}

function QuickJumpButton({ title, description, onClick }: { title: string; description: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-start justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/55 px-4 py-4 text-left transition hover:bg-white/10"
    >
      <div>
        <div className="text-sm font-medium text-white">{title}</div>
        <p className="mt-1 text-xs leading-5 text-slate-400">{description}</p>
      </div>
      <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
    </button>
  );
}

function ChecklistItem({ label, detail, done }: { label: string; detail: string; done: boolean }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <span
        className={cn(
          "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
          done ? "bg-emerald-500/15 text-emerald-200" : "bg-amber-500/15 text-amber-200",
        )}
      >
        {done ? "OK" : "!"}
      </span>
      <div>
        <div className="text-sm font-medium text-white">{label}</div>
        <div className="mt-1 text-xs leading-5 text-slate-400">{detail}</div>
      </div>
    </div>
  );
}

function GuideStepCard({
  title,
  description,
  badge,
  done,
  icon: Icon,
  actionLabel,
  actionIcon,
  onAction,
  busy,
}: {
  title: string;
  description: string;
  badge: string;
  done: boolean;
  icon: LucideIcon;
  actionLabel: string;
  actionIcon: LucideIcon;
  onAction: () => void;
  busy?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-2xl border border-white/10 bg-black/20 p-2.5 text-indigo-200">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-white">{title}</div>
            <p className="mt-1 text-xs leading-5 text-slate-400">{description}</p>
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-[11px] font-medium",
            done ? "bg-emerald-500/15 text-emerald-100" : "bg-amber-500/15 text-amber-100",
          )}
        >
          {badge}
        </span>
      </div>
      <div className="mt-4">
        <ActionButton onClick={onAction} busy={busy} icon={actionIcon} variant={done ? "secondary" : "primary"}>
          {actionLabel}
        </ActionButton>
      </div>
    </div>
  );
}

function EventTimelineList({ events }: { events: EventTimelineItem[] }) {
  if (!events.length) {
    return <EmptyState title="暂无事件" description="点击“手动轮询事件”后，这里会显示系统、新闻、公告和风险事件如何进入 Agent 输入流。" />;
  }

  return (
    <div className="space-y-3">
      {events.slice(0, 18).map((event) => (
        <div key={event.id} className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-white">{event.title}</span>
                <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", severityTone(event.severity))}>{event.severity}</span>
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {event.source} · {event.category} · {formatDateTime(event.timestamp)} {event.stock_code ? `· ${event.stock_code}` : ""}
              </div>
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-300">{event.summary || "暂无摘要"}</p>
          {event.url ? (
            <a className="mt-3 inline-flex text-xs text-indigo-200 hover:text-indigo-100" href={event.url} target="_blank" rel="noreferrer">
              查看来源
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function AgentToolsList({ tools }: { tools: AgentToolDefinition[] }) {
  if (!tools.length) {
    return <EmptyState title="暂无 Agent 工具清单" description="后端 /api/agents/tools 返回后，这里会列出每个 Agent 的工具、数据源和技能。" />;
  }

  return (
    <div className="grid gap-3">
      {tools.map((item) => (
        <details key={item.agent_id} className="group rounded-2xl border border-white/10 bg-slate-950/60 p-4 open:border-indigo-400/40 open:bg-indigo-500/5">
          <summary className="cursor-pointer list-none">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-white">{item.agent_name}</div>
                <p className="mt-1 text-xs leading-5 text-slate-400">{item.notes}</p>
              </div>
              <span className="rounded-full bg-indigo-500/15 px-2.5 py-1 text-[11px] font-medium text-indigo-100">{item.agent_id}</span>
            </div>
          </summary>
          <div className="mt-4 grid gap-3 text-xs text-slate-300 md:grid-cols-3">
            <TagList title="工具" items={item.tools} />
            <TagList title="数据源" items={item.data_sources} />
            <TagList title="技能" items={item.skills} />
          </div>
        </details>
      ))}
    </div>
  );
}

function MemoryCaseList({ cases, loading }: { cases: AgentMemoryCase[]; loading: boolean }) {
  if (loading) {
    return <EmptyState title="正在读取记忆" description="正在从运行内存或 MongoDB 决策记录中读取该模型账户的历史案例。" />;
  }
  if (!cases.length) {
    return <EmptyState title="暂无记忆案例" description="先运行一轮 Benchmark；系统会按 agent_id 隔离展示该模型驱动系统的历史决策。" />;
  }

  return (
    <div className="space-y-3">
      {cases.slice(0, 8).map((item) => (
        <div key={item.id} className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-white">{item.stock_code || "未知标的"} {item.stock_name}</span>
            <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", actionTone(item.action))}>{item.action}</span>
            <span className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">{item.outcome}</span>
          </div>
          <p className="mt-2 text-xs text-slate-400">{item.agent_id} · {item.llm_model || "model"} · {formatDateTime(item.decision_date)}</p>
          <p className="mt-3 text-sm leading-6 text-slate-300">{item.reason || "暂无记忆摘要"}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {item.tags.map((tag) => (
              <span key={tag} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">{tag}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function LlmCheckPanel({ check }: { check: LlmConfigCheckResponse }) {
  return (
    <div className="mt-4 space-y-3 rounded-2xl border border-white/10 bg-slate-950/60 p-4 text-xs text-slate-300">
      <div className="grid gap-3 md:grid-cols-3">
        <SummaryMetric label="连接状态" value={check.configured ? "已配置" : "未配置"} />
        <SummaryMetric label="模型数量" value={formatNumber(check.models.length)} />
        <SummaryMetric label="请求档位" value={check.request_profile || "-"} />
      </div>
      {check.warnings.length ? (
        <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-amber-100">
          <div className="font-medium">需要注意</div>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {check.warnings.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      {check.diagnostics.length ? (
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3 text-emerald-100">
          <div className="font-medium">检测信息</div>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {check.diagnostics.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      {check.models.length ? <TagList title="可用模型" items={check.models.slice(0, 16)} /> : null}
    </div>
  );
}

function TagList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-2 font-medium text-white">{title}</div>
      <div className="flex flex-wrap gap-2">
        {items.length ? items.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-slate-300">{item}</span>) : <span className="text-slate-500">-</span>}
      </div>
    </div>
  );
}

function severityTone(severity: string): string {
  if (severity === "critical") {
    return "bg-rose-500/15 text-rose-100";
  }
  if (severity === "warning") {
    return "bg-amber-500/15 text-amber-100";
  }
  return "bg-sky-500/15 text-sky-100";
}

function StatusPill({ children, icon: Icon, tone = "neutral" }: { children: string; icon: LucideIcon; tone?: "neutral" | "success" | "warning" | "info" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
        tone === "success" && "border-emerald-400/20 bg-emerald-500/10 text-emerald-100",
        tone === "warning" && "border-amber-400/20 bg-amber-500/10 text-amber-100",
        tone === "info" && "border-indigo-400/20 bg-indigo-500/10 text-indigo-100",
        tone === "neutral" && "border-white/10 bg-black/20 text-slate-200",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </span>
  );
}

function MetricCard({ icon: Icon, title, value, caption }: { icon: LucideIcon; title: string; value: string; caption: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-xl shadow-black/10 backdrop-blur-xl">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm text-slate-300">{title}</div>
          <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-indigo-200">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-400">{caption}</p>
    </div>
  );
}

function Panel({ title, description, icon: Icon, children }: { title: string; description: string; icon: LucideIcon; children: ReactNode }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/10 backdrop-blur-xl">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 text-white">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-2.5 text-indigo-200">
              <Icon className="h-5 w-5" />
            </div>
            <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function ConfigGroup({ id, title, description, children }: { id?: string; title: string; description?: string; children: ReactNode }) {
  return (
    <div id={id} className="scroll-mt-8 space-y-3 rounded-2xl border border-white/10 bg-slate-950/55 p-4">
      <div>
        <div className="text-sm font-medium text-white">{title}</div>
        {description ? <p className="mt-1 text-xs leading-5 text-slate-400">{description}</p> : null}
      </div>
      {children}
    </div>
  );
}

function FormField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium text-slate-300">{label}</span>
      {children}
    </label>
  );
}

function ActionButton({ children, onClick, icon: Icon, busy, variant = "primary" }: { children: string; onClick: () => void; icon: LucideIcon; busy?: boolean; variant?: "primary" | "secondary" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60",
        variant === "primary"
          ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 hover:bg-indigo-400"
          : "border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10",
      )}
    >
      <Icon className={cn("h-4 w-4", busy && "animate-spin")} />
      {busy ? "处理中..." : children}
    </button>
  );
}

function EquityChart({ series }: { series: EquityMetricPoint[] }) {
  if (!series.length) {
    return <EmptyState title="暂无权益曲线" description="运行至少一轮自动投资后，这里会开始累积权益、回撤和现金曲线。" />;
  }

  const topLines = Array.from(new Set(series.map((item) => item.llm_model || item.agent_id))).slice(0, 4);
  const mergedRows = Array.from(
    series.reduce<Map<string, Record<string, number | string>>>((map, point) => {
      const key = point.date;
      if (!map.has(key)) {
        map.set(key, { date: key });
      }
      const row = map.get(key)!;
      row[`${point.llm_model || point.agent_id}-equity`] = point.equity;
      row[`${point.llm_model || point.agent_id}-return`] = point.total_return;
      return map;
    }, new Map()),
  ).map(([, row]) => row);

  const colors = ["#818cf8", "#34d399", "#f472b6", "#fbbf24"];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <SummaryMetric label="样本点数" value={formatNumber(series.length)} />
        <SummaryMetric label="账户数量" value={formatNumber(topLines.length)} />
        <SummaryMetric label="最新日期" value={series[series.length - 1]?.date || "-"} />
      </div>
      <div className="h-[320px] rounded-2xl border border-white/10 bg-slate-950/70 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={mergedRows} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="rgba(148, 163, 184, 0.16)" strokeDasharray="4 4" />
            <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
            <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(value: number) => formatNumber(value)} />
            <Tooltip
              contentStyle={{ background: "#020617", border: "1px solid rgba(148,163,184,0.18)", borderRadius: 16 }}
              labelStyle={{ color: "#cbd5e1" }}
              formatter={(value) => formatMoney(typeof value === "number" ? value : Number(value ?? 0))}
            />
            {topLines.map((line, index) => (
              <Line
                key={line}
                type="monotone"
                dataKey={`${line}-equity`}
                name={line}
                stroke={colors[index % colors.length]}
                strokeWidth={2.5}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RankingsTable({ rankings }: { rankings: RankingRow[] }) {
  if (!rankings.length) {
    return <EmptyState title="暂无排行榜" description="运行一轮后，这里会展示多模型收益、胜率、交易次数与现金水平。" />;
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/55">
      <table className="min-w-full divide-y divide-white/10 text-left text-sm">
        <thead className="bg-white/5 text-slate-300">
          <tr>
            <th className="px-4 py-3">Rank</th>
            <th className="px-4 py-3">模型</th>
            <th className="px-4 py-3">收益</th>
            <th className="px-4 py-3">胜率</th>
            <th className="px-4 py-3">交易</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {rankings.slice(0, 8).map((row) => (
            <tr key={`${row.rank}-${row.agent_id}`} className="text-slate-200">
              <td className="px-4 py-3">#{row.rank}</td>
              <td className="px-4 py-3">
                <div className="font-medium text-white">{row.llm_model || row.agent_id}</div>
                <div className="text-xs text-slate-400">{row.agent_id}</div>
              </td>
              <td className="px-4 py-3 text-emerald-300">{formatPercent(row.total_return)}</td>
              <td className="px-4 py-3">{formatPercent(row.win_rate)}</td>
              <td className="px-4 py-3">{formatNumber(row.total_trades)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionLogList({ decisions }: { decisions: DecisionLogEntry[] }) {
  if (!decisions.length) {
    return <EmptyState title="暂无决策日志" description="当后端完成一轮自动投资后，这里会生成每只股票的可折叠决策卡。" />;
  }

  return (
    <div className="space-y-3">
      {decisions.slice(0, 12).map((decision) => (
        <details key={decision.id} className="group rounded-2xl border border-white/10 bg-slate-950/60 p-4 open:border-indigo-400/40 open:bg-indigo-500/5">
          <summary className="flex cursor-pointer list-none flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-white">{decision.summary}</span>
                <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", actionTone(decision.action))}>{decision.action}</span>
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {decision.stock_code} {decision.stock_name ? `· ${decision.stock_name}` : ""} · {decision.llm_model || decision.agent_id} · {formatDateTime(decision.timestamp)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-right text-xs text-slate-300 md:min-w-56">
              <div>
                <div className="text-slate-500">信心</div>
                <div className="text-sm text-white">{formatPercent(decision.confidence)}</div>
              </div>
              <div>
                <div className="text-slate-500">仓位</div>
                <div className="text-sm text-white">{formatPercent(decision.position_size)}</div>
              </div>
            </div>
          </summary>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="space-y-3">
              <TextChipList title="决策理由" items={decision.reasons} emptyLabel="暂无理由" tone="success" />
              <TextChipList title="风险提示" items={decision.risks} emptyLabel="暂无风险提示" tone="warning" />
            </div>
            <div className="space-y-3">
              {decision.steps.map((step) => (
                <div key={step.id} className="rounded-2xl border border-white/10 bg-black/20 p-3">
                  <div className="text-sm font-medium text-white">{step.title}</div>
                  <div className="mt-1 text-xs text-slate-400">{step.summary || "无摘要"}</div>
                  <pre className="mt-3 overflow-auto rounded-xl bg-slate-950/80 p-3 text-[11px] leading-5 text-slate-300">{JSON.stringify(step.details, null, 2)}</pre>
                </div>
              ))}
            </div>
          </div>
        </details>
      ))}
    </div>
  );
}

function EventFeed({ events }: { events: BackendEvent[] }) {
  if (!events.length) {
    return <EmptyState title="暂无实时事件" description="连接建立后，所有 run_started / agent_step / decision_made 事件都会显示在这里。" />;
  }

  return (
    <div className="space-y-3">
      {events.map((event) => (
        <div key={`${event.timestamp}-${event.type}-${event.agent_id}`} className="rounded-2xl border border-white/10 bg-slate-950/65 p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="rounded-full border border-indigo-400/20 bg-indigo-500/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.2em] text-indigo-100">{event.type}</span>
            <span className="text-xs text-slate-500">{formatDateTime(event.timestamp)}</span>
          </div>
          <div className="mt-2 text-sm text-white">{event.agent_id || event.run_id || "system"}</div>
          <pre className="mt-3 overflow-auto rounded-xl bg-black/25 p-3 text-[11px] leading-5 text-slate-300">{JSON.stringify(event.payload, null, 2)}</pre>
        </div>
      ))}
    </div>
  );
}

function HoldingsTable({ holdings }: { holdings: HoldingRow[] }) {
  if (!holdings.length) {
    return <EmptyState title="暂无持仓" description="当前组合还没有持仓或尚未完成一次投资轮次。" />;
  }

  return (
    <SimpleTable
      headers={["Agent", "股票", "持仓", "现价", "市值", "浮盈"]}
      rows={holdings.map((row) => [
        row.llm_model || row.agent_id,
        `${row.stock_code}${row.stock_name ? ` · ${row.stock_name}` : ""}`,
        formatNumber(row.shares),
        formatMoney(row.current_price),
        formatMoney(row.market_value),
        <span key={`${row.agent_id}-${row.stock_code}`} className={row.unrealized_return >= 0 ? "text-emerald-300" : "text-rose-300"}>
          {formatPercent(row.unrealized_return)}
        </span>,
      ])}
    />
  );
}

function CandidatesTable({ candidates }: { candidates: StockCandidate[] }) {
  if (!candidates.length) {
    return <EmptyState title="暂无候选股票" description="运行一轮后，这里会展示被多 Agent 讨论过的候选列表。" />;
  }

  return (
    <SimpleTable
      headers={["股票", "动作", "分数", "信心", "理由摘要"]}
      rows={candidates.map((row) => [
        `${row.stock_code}${row.stock_name ? ` · ${row.stock_name}` : ""}`,
        <span key={`${row.stock_code}-action`} className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium", actionTone(row.action))}>
          {row.action}
        </span>,
        formatNumber(row.score),
        formatPercent(row.confidence),
        row.reasons[0] || "暂无摘要",
      ])}
    />
  );
}

function TradesTable({ trades }: { trades: TradeRow[] }) {
  if (!trades.length) {
    return <EmptyState title="暂无交易记录" description="交易执行完成后，这里会显示买卖时间、价格、数量和原因。" />;
  }

  return (
    <SimpleTable
      headers={["日期", "Agent", "股票", "方向", "成交额", "原因"]}
      rows={trades.map((row) => [
        row.date || "-",
        row.llm_model || row.agent_id,
        `${row.stock_code}${row.stock_name ? ` · ${row.stock_name}` : ""}`,
        row.side,
        formatMoney(row.amount),
        row.reason || "-",
      ])}
    />
  );
}

function SimpleTable({ headers, rows }: { headers: string[]; rows: Array<Array<ReactNode>> }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/60">
      <table className="min-w-full divide-y divide-white/10 text-left text-sm">
        <thead className="bg-white/5 text-slate-300">
          <tr>
            {headers.map((header) => (
              <th key={header} className="px-4 py-3 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5 text-slate-200">
          {rows.map((cells, rowIndex) => (
            <tr key={`${rowIndex}-${headers[0]}`}>
              {cells.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`} className="px-4 py-3 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <span className="text-slate-400">{label}</span>
      <span className={cn("max-w-[70%] text-right text-white", mono && "font-mono text-xs")}>{value || "-"}</span>
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function TextChipList({ title, items, emptyLabel, tone }: { title: string; items: string[]; emptyLabel: string; tone: "success" | "warning" }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
      <div className="text-sm font-medium text-white">{title}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.length ? (
          items.map((item) => (
            <span
              key={item}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs",
                tone === "success" ? "bg-emerald-500/15 text-emerald-100" : "bg-amber-500/15 text-amber-100",
              )}
            >
              {item}
            </span>
          ))
        ) : (
          <span className="text-xs text-slate-500">{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/15 bg-slate-950/50 px-6 py-10 text-center">
      <div className="text-base font-medium text-white">{title}</div>
      <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
    </div>
  );
}

function StatusDot({ status }: { status: AgentStatus }) {
  return (
    <span
      className={cn(
        "inline-flex h-2.5 w-2.5 rounded-full",
        status === "running" && "bg-indigo-400 shadow-lg shadow-indigo-400/60",
        status === "completed" && "bg-emerald-400 shadow-lg shadow-emerald-400/60",
        status === "warning" && "bg-amber-400 shadow-lg shadow-amber-400/60",
        status === "failed" && "bg-rose-400 shadow-lg shadow-rose-400/60",
        status === "idle" && "bg-slate-500",
      )}
    />
  );
}

function eventTypeToStatus(eventType: string): AgentStatus {
  if (eventType === "agent_started" || eventType === "agent_step") {
    return "running";
  }
  if (eventType === "risk_checked") {
    return "warning";
  }
  if (eventType === "run_failed") {
    return "failed";
  }
  return "completed";
}

function actionTone(action: string): string {
  if (action.includes("BUY")) {
    return "bg-emerald-500/15 text-emerald-100";
  }
  if (action.includes("SELL")) {
    return "bg-rose-500/15 text-rose-100";
  }
  if (action.includes("REJECT")) {
    return "bg-amber-500/15 text-amber-100";
  }
  return "bg-slate-500/15 text-slate-100";
}

const inputClassName =
  "h-11 w-full rounded-xl border border-white/10 bg-slate-950/70 px-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-indigo-400/70 focus:ring-2 focus:ring-indigo-400/20";
