"""身份默认值：新建/编辑抓单雷达时补齐缺省字段，绝不覆盖用户显式选择。

只对 source_config.lead_hunt == "true" 的雷达生效；旧雷达在用户主动编辑前
不会被重算或改写。角色/地区进入 hunt_conditions 参与搜索词与匹配；业务匹配词
进入 collection_policy.required_terms；排除词并入 collection_policy.excluded_terms，
由既有 filter_page 在采集阶段真实过滤。
"""
import json
from typing import get_args

from ..core.errors import AppError
from ..schemas.domain import RadarCreate
from ..schemas.hunt import HuntConditions
from ..schemas.identity import IdentityProfile

HUNT_ROLE_VALUES = set(get_args(get_args(HuntConditions.model_fields["roles"].annotation)[0]))


def apply_identity_defaults(value: RadarCreate, identity: IdentityProfile | None) -> RadarCreate:
    if identity is None or value.source_config.get("lead_hunt") != "true":
        return value
    raw = value.source_config.get("hunt_conditions")
    if raw:
        try:
            conditions = json.loads(raw)
        except ValueError:
            return value  # 非法 JSON 由 RadarCreate 校验拦截；此处不做静默修复
    else:
        conditions = {}
    changed = dict(conditions)
    roles = [role for role in changed.get("roles") or []]
    if not roles:
        roles = [role for role in identity.target_roles if role in HUNT_ROLE_VALUES][:5]
        if roles:
            changed["roles"] = roles
    if not changed.get("regions") and identity.service_mode == "regions" and identity.regions:
        changed["regions"] = list(identity.regions[:10])
    if (identity.service_mode == "regions" and changed.get("regions")
            and any(not business.remote_deliverable for business in identity.businesses)
            and changed.get("match_mode", "remote") == "remote"):
        changed["match_mode"] = "local"

    updates: dict = {}
    keywords = list(dict.fromkeys(term.strip() for term in value.keywords if term.strip()))
    if not keywords and identity.buyer_keywords:
        cap = max(1, 6 // max(1, len(value.sources)))
        keywords = list(dict.fromkeys(term.strip() for term in identity.buyer_keywords if term.strip()))[: min(3, cap)]
        if keywords:
            updates["keywords"] = keywords
    # 新增 hunt_conditions 会在 RadarCreate 里触发“通用模式 + 关键词 + 平台”校验；
    # 不满足条件的输入保持原样，不强行注入。
    can_add_conditions = bool(raw) or (bool(updates.get("keywords")) and value.mode == "general" and bool(value.sources)
                                       and value.collection_policy.time_basis == "published" and not value.collection_policy.include_unknown_dates)
    if changed != conditions and can_add_conditions:
        updates["source_config"] = {**value.source_config, "hunt_conditions": json.dumps(changed, ensure_ascii=False)}

    policy = value.collection_policy
    policy_updates: dict = {}
    if not policy.required_terms and identity.business_match_words:
        policy_updates["required_terms"] = list(dict.fromkeys(word.strip() for word in identity.business_match_words if word.strip()))[:20]
    merged_excluded = list(dict.fromkeys([*policy.excluded_terms, *identity.exclude_words]))[:20]
    if merged_excluded != policy.excluded_terms:
        policy_updates["excluded_terms"] = merged_excluded
    if policy_updates:
        updates["collection_policy"] = policy.model_copy(update=policy_updates)

    if not updates:
        return value
    try:
        return RadarCreate.model_validate({**value.model_dump(), **updates})
    except ValueError as exc:
        raise AppError("IDENTITY_DEFAULTS_INVALID", "身份默认值与本次抓单条件冲突，请检查设置。", 422) from exc


def identity_defaults_for(repo, user_id: str) -> IdentityProfile | None:
    loader = getattr(repo, "get_identity", None)
    return loader(user_id) if loader else None
