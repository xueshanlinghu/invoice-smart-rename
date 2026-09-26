from __future__ import annotations

import json

from dotenv import dotenv_values

from app.config import ROOT_DIR, settings
from app.storage import SqliteTaskStore


DEFAULT_MODEL_CHOICES = [
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
]
DEFAULT_TEMPLATE = "{date}-{category}-{amount}"
DEFAULT_CATEGORY_MAPPING: dict[str, list[str]] = {
    # 顺序即优先级，保持与 .env.example 初始配置一致
    "餐饮": ["餐饮服务", "糕点"],
    "技术服务": ["研发和技术服务", "信息系统增值服务"],
    "会员订阅": ["会员订阅"],
    "信息技术培训费": ["信息技术培训费", "非学历教育服务"],
}

ENV_PATH = ROOT_DIR / ".env"
settings_store = SqliteTaskStore()


def _parse_models(raw: str | None) -> list[str]:
    values = [item.strip() for item in (raw or "").split(",") if item.strip()]
    if not values:
        return DEFAULT_MODEL_CHOICES.copy()
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _parse_mapping(raw: str | None) -> dict[str, list[str]]:
    if raw is None or raw == "":
        return DEFAULT_CATEGORY_MAPPING.copy()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_CATEGORY_MAPPING.copy()
    if not isinstance(parsed, dict):
        return DEFAULT_CATEGORY_MAPPING.copy()

    cleaned: dict[str, list[str]] = {}
    for key, value in parsed.items():
        category = str(key).strip()
        if not category or category == "其他":
            continue
        if isinstance(value, list):
            keywords = [str(item).strip() for item in value if str(item).strip()]
        else:
            keywords = []
        cleaned[category] = keywords
    return cleaned


def _normalize_template(template: str | None) -> str:
    value = (template or "").strip()
    if not value:
        return DEFAULT_TEMPLATE
    value = value.replace("{ext}", "").replace("{EXT}", "")
    value = value.rstrip(" .-_")
    return value or DEFAULT_TEMPLATE


def load_runtime_settings() -> dict:
    values = dotenv_values(ENV_PATH)
    persisted = settings_store.load_settings()

    persisted_models = persisted.get("siliconflow_models")
    models = (
        [str(item) for item in persisted_models]
        if isinstance(persisted_models, list)
        else _parse_models(values.get("SILICONFLOW_MODELS") or settings.siliconflow_models)
    )
    model = str(
        persisted.get("siliconflow_model")
        or values.get("SILICONFLOW_MODEL")
        or settings.siliconflow_model
        or models[0]
    ).strip()
    if model not in models:
        models = [model, *models]

    api_key = str(
        persisted.get("siliconflow_api_key")
        or values.get("SILICONFLOW_API_KEY")
        or settings.siliconflow_api_key
    ).strip()
    base_url = str(
        persisted.get("siliconflow_base_url")
        or values.get("SILICONFLOW_BASE_URL")
        or settings.siliconflow_base_url
    ).strip()
    template = _normalize_template(
        str(persisted.get("filename_template") or values.get("FILENAME_TEMPLATE") or settings.filename_template)
    )
    persisted_mapping = persisted.get("category_mapping")
    mapping = (
        _parse_mapping(json.dumps(persisted_mapping, ensure_ascii=False))
        if isinstance(persisted_mapping, dict)
        else _parse_mapping(values.get("CATEGORY_MAPPING_JSON"))
    )

    return {
        "siliconflow_base_url": base_url or "https://api.siliconflow.cn/v1",
        "siliconflow_model": model,
        "siliconflow_models": models,
        "siliconflow_api_key": api_key,
        "api_key_configured": bool(api_key),
        "filename_template": template,
        "category_mapping": mapping,
    }


def save_runtime_settings(
    *,
    siliconflow_base_url: str | None = None,
    siliconflow_model: str | None = None,
    siliconflow_models: list[str] | None = None,
    siliconflow_api_key: str | None = None,
    filename_template: str | None = None,
    category_mapping: dict[str, list[str]] | None = None,
) -> dict:
    updates: dict[str, object] = {}
    if siliconflow_base_url is not None:
        updates["siliconflow_base_url"] = siliconflow_base_url.strip() or "https://api.siliconflow.cn/v1"
    if siliconflow_model is not None:
        updates["siliconflow_model"] = siliconflow_model.strip()
    if siliconflow_models is not None:
        models = [item.strip() for item in siliconflow_models if item.strip()]
        if not models:
            models = DEFAULT_MODEL_CHOICES.copy()
        updates["siliconflow_models"] = models
    if siliconflow_api_key is not None:
        updates["siliconflow_api_key"] = siliconflow_api_key.strip()
    if filename_template is not None:
        updates["filename_template"] = _normalize_template(filename_template)
    if category_mapping is not None:
        mapping = {}
        for key, value in category_mapping.items():
            category = str(key).strip()
            if not category or category == "其他":
                continue
            mapping[category] = [str(item).strip() for item in value if str(item).strip()]
        updates["category_mapping"] = mapping

    if updates:
        settings_store.save_settings(updates)

    return load_runtime_settings()


def infer_category(item_name: str | None, filename: str, mapping: dict[str, list[str]]) -> str:
    source = f"{item_name or ''}\n{filename}".lower()
    # 按映射顺序匹配：命中首个类别后立即返回
    for category, keywords in mapping.items():
        for keyword in keywords:
            token = keyword.strip().lower()
            if token and token in source:
                return category
    return "其他"
