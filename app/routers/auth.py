import os

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SECRET_KEY = os.getenv("SECRET_KEY", "rssweb-default-secret-change-me")
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 天
_serializer = URLSafeTimedSerializer(SECRET_KEY)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_password_hash(db: Session) -> str | None:
    row = db.query(Setting).filter(Setting.key == "admin_password_hash").first()
    return row.value if row else None


def verify_session(request: Request) -> bool:
    token = request.cookies.get("session")
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


class _LoginRequired(Exception):
    def __init__(self, redirect_url: str = "/"):
        self.redirect_url = redirect_url


def require_login(request: Request):
    """FastAPI 依赖函数：验证登录状态，未登录则抛出 _LoginRequired"""
    if not verify_session(request):
        raise _LoginRequired(str(request.url.path))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", redirect: str = ""):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error, "redirect": redirect}
    )


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    password: str = Form(...),
    redirect: str = Form(""),
    db: Session = Depends(get_db),
):
    pwd_hash = _get_password_hash(db)
    if pwd_hash and _pwd_context.verify(password, pwd_hash):
        token = _serializer.dumps("admin")
        target_url = redirect if redirect else "/"
        resp = RedirectResponse(url=target_url, status_code=303)
        resp.set_cookie(
            "session", token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return resp
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "密码错误", "redirect": redirect},
        status_code=200,
    )


@router.post("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("session")
    return resp
