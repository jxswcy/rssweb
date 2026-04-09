from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SETTING_KEYS = [
    "openai_api_key",
    "claude_api_key",
    "deepseek_api_key",
    "openrouter_api_key",
    "translate_target_lang",
]


def _get_settings(db: Session) -> dict:
    rows = db.query(Setting).filter(Setting.key.in_(SETTING_KEYS)).all()
    return {r.key: r.value for r in rows}


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    current = _get_settings(db)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "openai_key_set": bool(current.get("openai_api_key")),
            "claude_key_set": bool(current.get("claude_api_key")),
            "deepseek_key_set": bool(current.get("deepseek_api_key")),
            "openrouter_key_set": bool(current.get("openrouter_api_key")),
            "translate_target_lang": current.get("translate_target_lang", "zh-CN"),
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
    translate_target_lang: str = Form("zh-CN"),
    db: Session = Depends(get_db),
):
    updates = {}
    if translate_target_lang.strip():
        updates["translate_target_lang"] = translate_target_lang.strip()
    if openai_api_key.strip():
        updates["openai_api_key"] = openai_api_key.strip()
    if claude_api_key.strip():
        updates["claude_api_key"] = claude_api_key.strip()
    if deepseek_api_key.strip():
        updates["deepseek_api_key"] = deepseek_api_key.strip()
    if openrouter_api_key.strip():
        updates["openrouter_api_key"] = openrouter_api_key.strip()

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
            "openai_key_set": bool(current.get("openai_api_key")),
            "claude_key_set": bool(current.get("claude_api_key")),
            "deepseek_key_set": bool(current.get("deepseek_api_key")),
            "openrouter_key_set": bool(current.get("openrouter_api_key")),
            "translate_target_lang": current.get("translate_target_lang", "zh-CN"),
            "saved": True,
        },
    )
