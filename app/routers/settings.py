import html as html_module
import traceback

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting
from app.translator import translate_text, PROVIDER_DEFAULT_MODELS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SETTING_KEYS = [
    "openai_api_key",
    "claude_api_key",
    "deepseek_api_key",
    "openrouter_api_key",
    "gemini_api_key",
    "translate_target_lang",
    "openai_base_url",
    "deepseek_base_url",
    "openrouter_base_url",
    "claude_base_url",
    "gemini_base_url",
]


def _get_settings(db: Session) -> dict:
    rows = db.query(Setting).filter(Setting.key.in_(SETTING_KEYS)).all()
    return {r.key: r.value for r in rows}


def _mask_key(key: str | None) -> str:
    """返回部分隐藏的 key，如 sk-ab••••••••cdef；key 为空时返回空字符串"""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return key[:4] + "••••••••" + key[-4:]


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    current = _get_settings(db)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "openai_api_key_masked": _mask_key(current.get("openai_api_key")),
            "claude_api_key_masked": _mask_key(current.get("claude_api_key")),
            "deepseek_api_key_masked": _mask_key(current.get("deepseek_api_key")),
            "openrouter_api_key_masked": _mask_key(current.get("openrouter_api_key")),
            "gemini_api_key_masked": _mask_key(current.get("gemini_api_key")),
            "translate_target_lang": current.get("translate_target_lang", "zh-CN"),
            "openai_base_url": current.get("openai_base_url", ""),
            "deepseek_base_url": current.get("deepseek_base_url", ""),
            "openrouter_base_url": current.get("openrouter_base_url", ""),
            "claude_base_url": current.get("claude_base_url", ""),
            "gemini_base_url": current.get("gemini_base_url", ""),
            "saved": False,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    openai_api_key: str = Form(""),
    claude_api_key: str = Form(""),
    deepseek_api_key: str = Form(""),
    openrouter_api_key: str = Form(""),
    gemini_api_key: str = Form(""),
    translate_target_lang: str = Form("zh-CN"),
    openai_base_url: str = Form(""),
    deepseek_base_url: str = Form(""),
    openrouter_base_url: str = Form(""),
    claude_base_url: str = Form(""),
    gemini_base_url: str = Form(""),
    db: Session = Depends(get_db),
):
    updates = {}
    if translate_target_lang.strip():
        updates["translate_target_lang"] = translate_target_lang.strip()
    # API Key：留空或含掩码字符（未修改）则跳过；有新值则更新
    for field_name, raw_value in [
        ("openai_api_key", openai_api_key),
        ("claude_api_key", claude_api_key),
        ("deepseek_api_key", deepseek_api_key),
        ("openrouter_api_key", openrouter_api_key),
        ("gemini_api_key", gemini_api_key),
    ]:
        v = raw_value.strip()
        if v and "••••" not in v:
            updates[field_name] = v
    # Base URL：留空则保存为空字符串（清除覆盖，恢复默认）；有值则覆盖
    for key, val in [
        ("openai_base_url", openai_base_url),
        ("deepseek_base_url", deepseek_base_url),
        ("openrouter_base_url", openrouter_base_url),
        ("claude_base_url", claude_base_url),
        ("gemini_base_url", gemini_base_url),
    ]:
        updates[key] = val.strip()

    for key, value in updates.items():
        existing = db.query(Setting).filter(Setting.key == key).first()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()

    current = _get_settings(db)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "openai_api_key_masked": _mask_key(current.get("openai_api_key")),
            "claude_api_key_masked": _mask_key(current.get("claude_api_key")),
            "deepseek_api_key_masked": _mask_key(current.get("deepseek_api_key")),
            "openrouter_api_key_masked": _mask_key(current.get("openrouter_api_key")),
            "gemini_api_key_masked": _mask_key(current.get("gemini_api_key")),
            "translate_target_lang": current.get("translate_target_lang", "zh-CN"),
            "openai_base_url": current.get("openai_base_url", ""),
            "deepseek_base_url": current.get("deepseek_base_url", ""),
            "openrouter_base_url": current.get("openrouter_base_url", ""),
            "claude_base_url": current.get("claude_base_url", ""),
            "gemini_base_url": current.get("gemini_base_url", ""),
            "saved": True,
        },
    )


@router.post("/settings/test-translation", response_class=HTMLResponse)
async def test_translation(
    provider: str = Form(...),
    db: Session = Depends(get_db),
):
    """HTMX 翻译测试：用当前保存的 key 和 base_url 翻译一句话，返回结果或详细错误"""
    current = _get_settings(db)
    api_key = current.get(f"{provider}_api_key")
    if not api_key:
        return HTMLResponse(
            f'<span class="test-error">❌ {html_module.escape(provider)} 尚未设置 API Key</span>'
        )

    base_url_raw = current.get(f"{provider}_base_url", "")
    base_url = base_url_raw if base_url_raw else None
    target_lang = current.get("translate_target_lang", "zh-CN")
    test_text = "Artificial intelligence is transforming the world rapidly."

    try:
        result = await translate_text(
            text=test_text,
            provider=provider,
            api_key=api_key,
            model=None,  # 使用默认模型
            target_lang=target_lang,
            base_url=base_url,
        )
        model_used = PROVIDER_DEFAULT_MODELS.get(provider, "默认")
        escaped_result = html_module.escape(result)
        escaped_src = html_module.escape(test_text)
        return HTMLResponse(
            f'<div class="test-ok">'
            f'<div style="font-size:0.78rem;color:#86868b;margin-bottom:0.3rem;">模型：{html_module.escape(model_used)}</div>'
            f'<div style="color:#86868b;font-size:0.82rem;">原文：{escaped_src}</div>'
            f'<div style="color:#1c7c54;font-size:0.9rem;margin-top:0.3rem;">✅ 译文：{escaped_result}</div>'
            f'</div>'
        )
    except Exception as exc:
        detail = html_module.escape(traceback.format_exc())
        short = html_module.escape(str(exc))
        return HTMLResponse(
            f'<div class="test-error">'
            f'<div>❌ 翻译失败：{short}</div>'
            f'<pre style="font-size:0.72rem;color:#86868b;white-space:pre-wrap;margin-top:0.5rem;">{detail}</pre>'
            f'</div>'
        )
