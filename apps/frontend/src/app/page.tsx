"use client";

import dynamic from "next/dynamic";

const TradingDashboard = dynamic(
  () => import("@/components/trading-dashboard").then((module) => module.TradingDashboard),
  {
    ssr: false,
    loading: () => <div className="min-h-screen bg-slate-950 text-slate-100 px-6 py-10">正在加载现代投资控制台...</div>,
  },
);

export default function Home() {
  return <TradingDashboard />;
}
