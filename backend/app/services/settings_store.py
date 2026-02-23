from __future__ import annotations

import json

from dotenv import dotenv_values, set_key

from app.config import ROOT_DIR, settings


DEFAULT_MODEL_CHOICES = [
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3-VL-30B-A3B-Instruct",
]
DEFAULT_TEMPLATE = "{date}-{category}-{amount}"
DEFAULT_CATEGORY_MAPPING: dict[str, list[str]] = {
    "餐饮": ["餐饮", "餐饮服务", "糕点", "餐费", "餐厅"],
    "培训/服务": ["培训", "技术培训", "服务费", "信息技术", "信息服务"],
    "交通": ["交通", "打车", "机票", "高铁", "火车", "出行"],
    "办公": ["办公", "办公用品", "文具", "耗材"],
    "住宿": ["住宿", "酒店", "宾馆"],
}

ENV_PATH = ROOT_DIR / ".env"


def _ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.write_text("", encoding="utf-8")


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

    models = _parse_models(values.get("SILICONFLOW_MODELS") or settings.siliconflow_models)
    model = (values.get("SILICONFLOW_MODEL") or settings.siliconflow_model or models[0]).strip()
    if model not in models:
        models = [model, *models]

    api_key = (values.get("SILICONFLOW_API_KEY") or settings.siliconflow_api_key).strip()
    base_url = (values.get("SILICONFLOW_BASE_URL") or settings.siliconflow_base_url).strip()
    template = _normalize_template(values.get("FILENAME_TEMPLATE") or settings.filename_template)
    mapping = _parse_mapping(values.get("CATEGORY_MAPPING_JSON"))

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
    _ensure_env_file()

    if siliconflow_base_url is not None:
        set_key(str(ENV_PATH), "SILICONFLOW_BASE_URL", siliconflow_base_url.strip() or "https://api.siliconflow.cn/v1")
    if siliconflow_model is not None:
        set_key(str(ENV_PATH), "SILICONFLOW_MODEL", siliconflow_model.strip())
    if siliconflow_models is not None:
        models = [item.strip() for item in siliconflow_models if item.strip()]
        if not models:
            models = DEFAULT_MODEL_CHOICES.copy()
        set_key(str(ENV_PATH), "SILICONFLOW_MODELS", ",".join(models))
    if siliconflow_api_key is not None:
        set_key(str(ENV_PATH), "SILICONFLOW_API_KEY", siliconflow_api_key.strip())
    if filename_template is not None:
        set_key(str(ENV_PATH), "FILENAME_TEMPLATE", _normalize_template(filename_template))
    if category_mapping is not None:
        mapping = {}
        for key, value in category_mapping.items():
            category = str(key).strip()
            if not category or category == "其他":
                continue
            mapping[category] = [str(item).strip() for item in value if str(item).strip()]
        set_key(str(ENV_PATH), "CATEGORY_MAPPING_JSON", json.dumps(mapping, ensure_ascii=False))

    return load_runtime_settings()


def infer_category(item_name: str | None, filename: str, mapping: dict[str, list[str]]) -> str:
    source = f"{item_name or ''}\n{filename}".lower()
    best_category = "其他"
    best_weight = 0
    for category, keywords in mapping.items():
        weight = 0
        for keyword in keywords:
            token = keyword.strip().lower()
            if token and token in source:
                weight += 1
        if weight > best_weight:
            best_weight = weight
            best_category = category
    return best_category
