"""Framework-neutral configuration wizard helpers for the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SECRET_FIELDS = {
    ("data", "tushare_token"),
    ("data", "alpha_vantage_api_key"),
    ("data", "jqdata_password"),
    ("llm", "api_key"),
    ("notification", "smtp_password"),
    ("notification", "webhook_url"),
}


@dataclass(frozen=True, slots=True)
class WizardQuestion:
    """One prompt in the terminal configuration wizard."""

    key: str
    label: str
    section: str
    field_name: str
    value_type: str = "str"
    default: str = ""
    secret: bool = False
    required: bool = False
    help_text: str = ""


CONFIG_WIZARD_QUESTIONS: tuple[WizardQuestion, ...] = (
    WizardQuestion(
        key="data_mode",
        label="数据模式 offline/online",
        section="data",
        field_name="mode",
        default="offline",
        required=True,
        help_text="先用 offline 跑通；online 会按 provider chain 读取真实/可选数据源。",
    ),
    WizardQuestion(
        key="provider_chain",
        label="数据源链路",
        section="data",
        field_name="provider_chain",
        value_type="list[str]",
        default="tushare,baostock,akshare",
        help_text="可手动加入 adata/openbb/yfinance/alpha-vantage/jqdata；AAStock/同花顺仅登记诊断，不做未授权抓取。",
    ),
    WizardQuestion(
        key="dynamic_universe_limit",
        label="动态股票池上限",
        section="data",
        field_name="dynamic_universe_limit",
        value_type="int",
        default="20",
    ),
    WizardQuestion(
        key="tushare_token",
        label="Tushare Token（可留空）",
        section="data",
        field_name="tushare_token",
        secret=True,
    ),
    WizardQuestion(
        key="alpha_vantage_api_key",
        label="Alpha Vantage API Key（可留空）",
        section="data",
        field_name="alpha_vantage_api_key",
        secret=True,
    ),
    WizardQuestion(
        key="jqdata_username",
        label="JQData 用户名（可留空）",
        section="data",
        field_name="jqdata_username",
    ),
    WizardQuestion(
        key="jqdata_password",
        label="JQData 密码（可留空）",
        section="data",
        field_name="jqdata_password",
        secret=True,
    ),
    WizardQuestion(
        key="initial_capital",
        label="每个模型账户初始资金",
        section="portfolio",
        field_name="initial_capital",
        value_type="float",
        default="100000",
    ),
    WizardQuestion(
        key="max_position_per_stock",
        label="单股最大仓位比例",
        section="risk",
        field_name="max_position_per_stock",
        value_type="float",
        default="0.10",
    ),
    WizardQuestion(
        key="max_total_position",
        label="组合最大总仓位比例",
        section="risk",
        field_name="max_total_position",
        value_type="float",
        default="0.50",
    ),
    WizardQuestion(
        key="stop_loss_pct",
        label="止损比例",
        section="risk",
        field_name="stop_loss_pct",
        value_type="float",
        default="0.05",
    ),
    WizardQuestion(
        key="llm_base_url",
        label="LLM Base URL",
        section="llm",
        field_name="base_url",
        default="https://example.com/v1",
    ),
    WizardQuestion(
        key="llm_api_key",
        label="LLM API Key（可留空，留空时只跑 rule-baseline）",
        section="llm",
        field_name="api_key",
        secret=True,
    ),
    WizardQuestion(
        key="llm_default_model",
        label="默认 LLM 模型（可留空）",
        section="llm",
        field_name="default_model",
    ),
    WizardQuestion(
        key="request_profile",
        label="LLM 请求档位 openai/codex/anthropic/claude_code/auto",
        section="llm",
        field_name="request_profile",
        default="auto",
    ),
    WizardQuestion(
        key="scheduler_models",
        label="比赛模型列表",
        section="scheduler",
        field_name="models",
        value_type="list[str]",
        default="rule-baseline",
        required=True,
    ),
    WizardQuestion(
        key="scheduler_max_count",
        label="每轮候选股票数量",
        section="scheduler",
        field_name="max_count",
        value_type="int",
        default="1",
    ),
    WizardQuestion(
        key="scheduler_history_days",
        label="历史窗口天数",
        section="scheduler",
        field_name="history_days",
        value_type="int",
        default="12",
    ),
)


def build_config_patch(answers: dict[str, str], questions: tuple[WizardQuestion, ...] = CONFIG_WIZARD_QUESTIONS) -> dict[str, Any]:
    """Build the nested runtime config payload sent to ``/api/config``."""
    patch: dict[str, Any] = {}
    for question in questions:
        raw_value = answers.get(question.key, question.default)
        if raw_value is None:
            raw_value = ""
        raw_value = str(raw_value).strip()
        if not raw_value and not question.required:
            continue
        value = _coerce(raw_value or question.default, question.value_type)
        patch.setdefault(question.section, {})[question.field_name] = value
    return patch


def redact_config_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Return a display-safe copy of a config patch."""
    redacted: dict[str, Any] = {}
    for section, values in patch.items():
        if not isinstance(values, dict):
            continue
        redacted[section] = {}
        for field_name, value in values.items():
            if (section, field_name) in SECRET_FIELDS:
                redacted[section][field_name] = "[已设置]" if str(value).strip() else "[未设置]"
            else:
                redacted[section][field_name] = value
    return redacted


def render_wizard_summary(patch: dict[str, Any]) -> str:
    """Render a compact, secret-safe wizard completion summary."""
    safe_patch = redact_config_patch(patch)
    lines = ["配置向导摘要", "=" * 40]
    for section, values in safe_patch.items():
        lines.append(f"[{section}]")
        if isinstance(values, dict):
            for field_name, value in values.items():
                lines.append(f"  {field_name}: {value}")
    lines.append("配置会保存到 data/runtime/settings.override.json；该目录已被 Git 忽略。")
    return "\n".join(lines)


def _coerce(value: str, value_type: str) -> Any:
    if value_type == "int":
        return int(float(value))
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if value_type == "list[str]":
        return [item.strip() for item in value.split(",") if item.strip()]
    return value
