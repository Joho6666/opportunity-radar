"""本机 Agent 令牌：给 agent / 命令行使用的 Bearer Token 凭据。

- 存放于应用数据目录的 config/ 子目录（目录 0700、文件 0600），原子写入。
- 明文只存在于该文件与生成响应的一次性回显中；页面与任何 API 只返回脱敏掩码。
- 每次读取都按 (mtime_ns, size) 判断是否需要重读文件：页面生成/重置/吊销后
  无需重启服务（与 provider_config 的热加载机制一致）。
- 仅对 APP_ENV=local 生效；云端环境完全没有 agent 接口。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

TOKEN_PREFIX = "or_agent_"
TOKEN_BYTES = 32
TOKEN_PATTERN = re.compile(r"or_agent_[A-Za-z0-9_-]{16,120}")


class AgentTokenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(default="", max_length=200)
    created_at: str = ""
    updated_at: str = ""
    rotations: int = Field(default=0, ge=0)

    @field_validator("token")
    @classmethod
    def _shape(cls, value: str) -> str:
        if value and not TOKEN_PATTERN.fullmatch(value):
            raise ValueError("agent token 需为 or_agent_ 前缀的随机串")
        return value


def agent_token_path() -> Path | None:
    explicit = os.getenv("OR_AGENT_TOKEN_PATH")
    if explicit:
        return Path(explicit)
    config_dir = os.getenv("LOCAL_PRIVATE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "agent-token.json"
    runtime_dir = os.getenv("LOCAL_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir).parent / "config" / "agent-token.json"
    return None


def generate_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_BYTES)}"


def masked_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= len(TOKEN_PREFIX) + 8:
        return f"{TOKEN_PREFIX}***"
    return f"{token[: len(TOKEN_PREFIX) + 1]}***{token[-4:]}"


_cache: dict = {"stamp": None, "config": None}


def reset_agent_token_cache() -> None:
    _cache.update(stamp=None, config=None)


def read_agent_token(path: Path | None = None) -> AgentTokenConfig | None:
    """按 mtime/size 热读取令牌文件；未配置或损坏一律视为未配置。"""
    target = path if path is not None else agent_token_path()
    if target is None:
        return None
    if path is None:
        try:
            status = target.stat()
            stamp = (status.st_mtime_ns, status.st_size)
        except FileNotFoundError:
            stamp = None
        if stamp is None:
            _cache.update(stamp=None, config=None)
            return None
        if stamp == _cache["stamp"] and _cache["config"] is not None:
            return _cache["config"]
        config = _load(target)
        _cache.update(stamp=stamp if config is not None else None, config=config)
        return config
    return _load(target)


def _load(target: Path) -> AgentTokenConfig | None:
    try:
        payload = json.loads(target.read_text())
        config = AgentTokenConfig.model_validate(payload)
    except (FileNotFoundError, ValueError):
        return None
    return config if config.token else None


def write_agent_token(config: AgentTokenConfig, path: Path | None = None) -> Path:
    target = path if path is not None else agent_token_path()
    if target is None:
        raise RuntimeError("本机私密配置目录不可用；请通过 scripts/local.sh 启动服务。")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    stamped = config.model_copy(update={"updated_at": datetime.now(UTC).isoformat()})
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".agent-token-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps(stamped.model_dump(), ensure_ascii=False, indent=2))
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if path is None:
        reset_agent_token_cache()
    return target


def delete_agent_token(path: Path | None = None) -> bool:
    target = path if path is not None else agent_token_path()
    if target is None:
        return False
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    if path is None:
        reset_agent_token_cache()
    return True


def current_token(path: Path | None = None) -> str:
    config = read_agent_token(path)
    return config.token if config else ""


def verify_agent_token(supplied: str, path: Path | None = None) -> bool:
    """常数时间比较；未配置令牌时一律拒绝（fail closed）。"""
    import hmac

    expected = current_token(path)
    if not expected or not supplied:
        return False
    return hmac.compare_digest(supplied, expected)
