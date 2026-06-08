"""Interactive configuration wizard for the TUI using InquirerPy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

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
        label="数据模式",
        section="data",
        field_name="mode",
        default="offline",
        required=True,
        help_text="先用 offline 跑通；online 会按 provider chain 读取真实/可选数据源。",
    ),
    WizardQuestion(
        key="provider_chain",
        label="数据源链路（逗号分隔）",
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
        label="LLM 请求档位",
        section="llm",
        field_name="request_profile",
        default="auto",
    ),
    WizardQuestion(
        key="scheduler_models",
        label="比赛模型列表（运行前选择，初始化不再填写）",
        section="scheduler",
        field_name="models",
        value_type="list[str]",
        default="",
        required=False,
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


def run_interactive_wizard(available_models: list[str] | None = None) -> dict[str, str]:
    """Run the interactive configuration wizard using InquirerPy."""
    console.print(Panel.fit(
        "[bold cyan]AStock 配置向导[/bold cyan]\n\n"
        "交互式配置所有必要参数。使用 ↑↓ 导航，空格选择/取消，Enter 确认。\n"
        "密钥输入不会回显。可随时按 Ctrl+C 跳过。",
        border_style="cyan"
    ))
    
    answers: dict[str, str] = {}
    
    sections = {
        "data": [],
        "portfolio": [],
        "risk": [],
        "llm": [],
        "scheduler": [],
    }
    
    for question in CONFIG_WIZARD_QUESTIONS:
        sections.setdefault(question.section, []).append(question)
    
    for section_name, questions in sections.items():
        if not questions:
            continue
        
        console.print(f"\n[bold yellow]━━━ {section_name.upper()} 配置 ━━━[/bold yellow]")
        
        for question in questions:
            if question.section == "scheduler" and question.field_name == "models":
                continue
            if question.help_text:
                console.print(f"[dim]💡 {question.help_text}[/dim]")
            
            try:
                if question.section == "data" and question.field_name == "provider_chain":
                    default_sources = [item.strip() for item in question.default.split(",") if item.strip()]
                    selected = inquirer.checkbox(
                        message=question.label,
                        choices=[
                            Choice(value="tushare", name="Tushare - A股主数据源（需 token）"),
                            Choice(value="baostock", name="Baostock - 免费A股历史行情补充源"),
                            Choice(value="akshare", name="AkShare - 免费A股综合兜底源"),
                            Choice(value="adata", name="AData - 轻量历史行情补充"),
                            Choice(value="openbb", name="OpenBB - 全球/宏观参考"),
                            Choice(value="yfinance", name="yfinance - 海外/港股参考"),
                            Choice(value="alpha-vantage", name="Alpha Vantage - 海外/宏观参考（需 key）"),
                            Choice(value="jqdata", name="JQData - 聚宽研究数据（需账号）"),
                        ],
                        default=default_sources,
                        instruction="空格选择/取消，Enter 确认",
                    ).execute()
                    value = ",".join(str(item) for item in selected)
                elif question.secret:
                    value = inquirer.secret(
                        message=question.label,
                        default=question.default,
                    ).execute()
                elif question.section == "data" and question.field_name == "mode":
                    value = inquirer.select(
                        message=question.label,
                        choices=[
                            Choice(value="offline", name="offline - 离线模式（推荐先用此模式测试）"),
                            Choice(value="online", name="online - 在线模式（需配置数据源凭证）"),
                        ],
                        default="offline",
                    ).execute()
                elif question.section == "llm" and question.field_name == "request_profile":
                    value = inquirer.select(
                        message=question.label,
                        choices=["auto", "openai", "codex", "anthropic", "claude_code"],
                        default="auto",
                    ).execute()
                elif question.section == "llm" and question.field_name == "default_model" and available_models:
                    value = inquirer.fuzzy(
                        message=question.label,
                        choices=[Choice(value=model, name=model) for model in available_models],
                        default=available_models[0],
                        instruction="输入关键字过滤，Tab/Enter 选择",
                    ).execute()
                else:
                    value = inquirer.text(
                        message=question.label,
                        default=question.default,
                        validate=lambda x: len(x) > 0 if question.required else True,
                        invalid_message="此项必填" if question.required else "",
                    ).execute()
                
                answers[question.key] = value or question.default
            
            except KeyboardInterrupt:
                console.print("\n[yellow]配置向导已中断。可稍后用 /config 命令更新配置。[/yellow]")
                return {}
    
    return answers


def build_config_patch(answers: dict[str, str], questions: tuple[WizardQuestion, ...] = CONFIG_WIZARD_QUESTIONS) -> dict[str, Any]:
    """Build the nested runtime config payload sent to ``/api/config``."""
    patch: dict[str, Any] = {}
    for question in questions:
        raw_value = answers.get(question.key, question.default)
        if raw_value is None:
            raw_value = ""
        if isinstance(raw_value, list):
            raw_text = ",".join(str(item).strip() for item in raw_value if str(item).strip())
        else:
            raw_text = str(raw_value).strip()
        if not raw_text and not question.required:
            continue
        value = _coerce(raw_text or question.default, question.value_type)
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


def render_wizard_summary(patch: dict[str, Any]) -> None:
    """Render a Rich-styled, secret-safe wizard completion summary."""
    safe_patch = redact_config_patch(patch)
    table = Table(title="配置向导摘要", show_header=True, header_style="bold magenta")
    table.add_column("配置项", style="cyan", no_wrap=True)
    table.add_column("值", style="green")
    
    for section, values in safe_patch.items():
        if isinstance(values, dict):
            for field_name, value in values.items():
                table.add_row(f"[{section}] {field_name}", str(value))
    
    console.print(table)
    console.print("[dim]配置会保存到 data/runtime/settings.override.json；该目录已被 Git 忽略。[/dim]")


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
