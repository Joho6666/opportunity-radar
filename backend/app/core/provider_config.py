"""本机私密 Provider 配置：界面内保存的 TikHub 密钥与预算上限。

- 存放于应用数据目录的 config/ 子目录（目录 0700、文件 0600），原子写入。
- 一旦界面保存/删除过密钥（manage_key=true），本文件即是密钥的权威来源：
  替换或删除密钥无需编辑 local.env、无需重启服务（get_settings() 会按 mtime 热加载）。
- 密钥明文只存在于该文件与进程内存中；任何 API 响应只返回脱敏掩码。
- 仅对 APP_ENV=local 生效；云端/生产环境完全忽略本机制。
"""
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

KEY_PATTERN = re.compile(r"[!-~]{8,200}")
LOCAL_BUDGET_MAX_USD = 1.0
LOCAL_DAILY_REQUESTS_MAX = 20


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manage_key: bool = False  # 界面保存或删除过密钥后为 True；budget-only 更新不抢管密钥
    tikhub_api_key: str = Field(default="", max_length=200)
    tikhub_manual_enabled: bool = False
    single_run_limit_usd: float = Field(default=0.1, gt=0, le=LOCAL_BUDGET_MAX_USD)
    daily_limit_usd: float = Field(default=1.0, gt=0, le=LOCAL_BUDGET_MAX_USD)
    daily_request_limit: int = Field(default=20, ge=1, le=LOCAL_DAILY_REQUESTS_MAX)
    confirm_required: bool = True
    test_result: dict | None = None
    updated_at: str = ""

    @model_validator(mode="after")
    def bounded(self):
        if self.single_run_limit_usd > self.daily_limit_usd:
            raise ValueError("单轮上限不能高于每日上限")
        if self.tikhub_api_key and not KEY_PATTERN.fullmatch(self.tikhub_api_key):
            raise ValueError("密钥需为 8–200 位无空格的可打印字符")
        if self.tikhub_manual_enabled and not self.tikhub_api_key:
            raise ValueError("启用 TikHub 手动采集前需要先保存密钥")
        return self


def provider_config_path() -> Path | None:
    explicit = os.getenv("OR_PROVIDER_CONFIG_PATH")
    if explicit:
        return Path(explicit)
    config_dir = os.getenv("LOCAL_PRIVATE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "provider-config.json"
    runtime_dir = os.getenv("LOCAL_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir).parent / "config" / "provider-config.json"
    return None


def read_provider_config(path: Path | None = None) -> ProviderConfig | None:
    target = path if path is not None else provider_config_path()
    if target is None:
        return None
    try:
        payload = json.loads(target.read_text())
    except (FileNotFoundError, ValueError):
        return None
    try:
        return ProviderConfig.model_validate(payload)
    except ValueError:
        return None


def write_provider_config(config: ProviderConfig, path: Path | None = None) -> Path:
    target = path if path is not None else provider_config_path()
    if target is None:
        raise RuntimeError("本机私密配置目录不可用；请通过 scripts/local.sh 启动服务。")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    stamped = config.model_copy(update={"updated_at": datetime.now(UTC).isoformat()})
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".provider-config-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps(stamped.model_dump(), ensure_ascii=False, indent=2))
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def masked_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


_OVERLAY_FIELDS = ("tikhub_api_key", "local_manual_tikhub_enabled", "paid_api_enabled", "paid_daily_cost_limit", "paid_daily_request_limit")
_overlay_state: dict = {"stamp": None, "config": None, "base": None}


def reset_provider_overlay_cache() -> None:
    _overlay_state.update(stamp=None, config=None, base=None)


def apply_provider_overlay(settings) -> None:
    """把本机私密配置叠加到进程内 settings 单例上。

    get_settings() 每次调用都会经过这里；文件 mtime/size 未变化时只是一次 stat。
    界面保存后无需重启：API 与 worker 都通过 get_settings() 读取同一份配置。
    """
    if settings.app_env.lower() != "local":
        return
    path = provider_config_path()
    if path is None:
        return
    try:
        status = path.stat()
        stamp = (status.st_mtime_ns, status.st_size)
    except FileNotFoundError:
        stamp = None
    state = _overlay_state
    if stamp == state["stamp"] and state["base"] is not None:
        return
    config = read_provider_config(path) if stamp is not None else None
    state["stamp"] = stamp
    state["config"] = config
    if state["base"] is None:
        state["base"] = {field: getattr(settings, field) for field in _OVERLAY_FIELDS}
    base = state["base"]
    if config is None:
        for field, value in base.items():
            setattr(settings, field, value)
        return
    if config.manage_key:
        enabled = bool(config.tikhub_manual_enabled and config.tikhub_api_key)
        settings.tikhub_api_key = config.tikhub_api_key
        settings.local_manual_tikhub_enabled = enabled
        settings.paid_api_enabled = enabled
    else:
        settings.tikhub_api_key = base["tikhub_api_key"]
        settings.local_manual_tikhub_enabled = base["local_manual_tikhub_enabled"]
        settings.paid_api_enabled = base["paid_api_enabled"]
    settings.paid_daily_cost_limit = config.daily_limit_usd
    settings.paid_daily_request_limit = config.daily_request_limit


def effective_key(settings) -> tuple[str, str]:
    """返回 (密钥, 来源)。来源为 ui / env / none；密钥永不出现在响应里。"""
    config = read_provider_config()
    if config is not None and config.manage_key:
        return (config.tikhub_api_key, "ui" if config.tikhub_api_key else "none")
    return (settings.tikhub_api_key, "env" if settings.tikhub_api_key else "none")


def provider_state(settings) -> dict:
    config = read_provider_config()
    key, source = effective_key(settings)
    if source == "ui":
        enabled = bool(config and config.tikhub_manual_enabled and key)
    else:
        enabled = bool(key and settings.paid_api_enabled and settings.local_manual_tikhub_enabled)
    budgets = {
        "single_run_limit_usd": config.single_run_limit_usd if config else 0.1,
        "daily_limit_usd": config.daily_limit_usd if config else settings.paid_daily_cost_limit,
        "daily_request_limit": config.daily_request_limit if config else settings.paid_daily_request_limit,
        "confirm_required": config.confirm_required if config else True,
    }
    return {
        "configured": bool(key),
        "enabled": enabled,
        "key_source": source,
        "masked_key": masked_key(key),
        "budgets": budgets,
        "last_test": (config.test_result if config else None),
        "updated_at": (config.updated_at if config else ""),
        "restart_required": False,
    }


PLACEHOLDER_PROVIDERS = [
    {"id": "firecrawl", "name": "Firecrawl 网页搜索", "available": False, "status": "未接入界面配置", "detail": "保持 local.env 手动开关；本轮不提供界面密钥输入，仍按原计费与授权机制执行。"},
    {"id": "llm", "name": "大模型分析（OpenAI 兼容）", "available": False, "status": "未接入界面配置", "detail": "按需分析继续由 local.env 与服务端授权控制；本轮不提供界面密钥输入。"},
]
