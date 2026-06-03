"""Fundamental analysis agent using normalized financial snapshots."""

from __future__ import annotations

from astock_agent_system.models import AnalysisResult, FinancialSnapshot


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _label(score: float) -> str:
    if score >= 0.75:
        return "优质"
    if score >= 0.60:
        return "良好"
    if score >= 0.40:
        return "一般"
    return "偏弱"


class FundamentalAnalyst:
    """Score valuation, profitability, growth and balance-sheet risk."""

    def analyze(self, financial: FinancialSnapshot) -> AnalysisResult:
        score = 0.50
        reasons: list[str] = []
        risks: list[str] = []

        if financial.pe_ttm <= 0:
            score -= 0.18
            risks.append("PE TTM 非正，估值或盈利质量需核查")
        elif financial.pe_ttm < 15:
            score += 0.14
            reasons.append(f"PE TTM={financial.pe_ttm:.1f}，估值相对不高")
        elif financial.pe_ttm <= 30:
            score += 0.06
            reasons.append(f"PE TTM={financial.pe_ttm:.1f}，估值处于可接受区间")
        elif financial.pe_ttm > 50:
            score -= 0.14
            risks.append(f"PE TTM={financial.pe_ttm:.1f}，估值较高")

        if financial.pb <= 0:
            score -= 0.06
            risks.append("PB 非正，需核查财务数据")
        elif financial.pb < 2:
            score += 0.08
            reasons.append(f"PB={financial.pb:.1f}，账面估值较低")
        elif financial.pb <= 5:
            score += 0.03
        elif financial.pb > 8:
            score -= 0.08
            risks.append(f"PB={financial.pb:.1f}，账面估值偏高")

        if financial.roe >= 0.20:
            score += 0.16
            reasons.append(f"ROE={financial.roe:.1%}，盈利质量较强")
        elif financial.roe >= 0.10:
            score += 0.08
            reasons.append(f"ROE={financial.roe:.1%}，盈利质量尚可")
        else:
            score -= 0.10
            risks.append(f"ROE={financial.roe:.1%}，盈利质量偏弱")

        growth = (financial.revenue_growth + financial.profit_growth) / 2
        if growth >= 0.12:
            score += 0.14
            reasons.append(f"营收/利润平均增速约 {growth:.1%}，成长性较好")
        elif growth >= 0.03:
            score += 0.06
            reasons.append(f"营收/利润平均增速约 {growth:.1%}，维持正增长")
        elif growth < 0:
            score -= 0.14
            risks.append(f"营收/利润平均增速约 {growth:.1%}，增长承压")

        if financial.debt_ratio > 0.70 and financial.sector != "金融":
            score -= 0.12
            risks.append(f"资产负债率 {financial.debt_ratio:.1%}，非金融行业杠杆偏高")
        elif financial.debt_ratio < 0.45 or financial.sector == "金融":
            score += 0.05
            reasons.append("杠杆水平与行业特征基本匹配")

        if financial.market_cap >= 100_000_000_000:
            score += 0.05
            reasons.append("市值规模较大，流动性和抗风险能力相对更好")

        final_score = round(_clamp(score), 4)
        return AnalysisResult(
            agent_name="FundamentalAnalyst",
            stock_code=financial.stock_code,
            score=final_score,
            label=_label(final_score),
            reasons=reasons,
            risks=risks,
            metadata={
                "pe_ttm": financial.pe_ttm,
                "pb": financial.pb,
                "roe": financial.roe,
                "debt_ratio": financial.debt_ratio,
                "revenue_growth": financial.revenue_growth,
                "profit_growth": financial.profit_growth,
                "market_cap": financial.market_cap,
            },
        )
