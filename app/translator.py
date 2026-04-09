import logging
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

CHUNK_SIZE = 15000  # 每块最大字符数（按段落边界切）；15000 字符≈3750 输入 token，中文输出约 5000–7000 token，在所有模型 8192 上限内安全
MAX_TOKENS  = 8192  # AI 输出 token 上限；受 Claude 系列最大 8192 输出限制，不可超过此值（OpenAI/DeepSeek 支持更高但统一取最小公约数）

# 各提供方的 API base URL（None 表示使用 SDK 默认值）
PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

# 各提供方默认模型
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "openrouter": "openai/gpt-4o-mini",
    "claude": "claude-3-5-haiku-20241022",
    "gemini": "gemini-2.0-flash",
}

# 各提供方推荐模型列表（按翻译质量从高到低）
PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "deepseek": [
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v3",
    ],
    "openrouter": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/gpt-4.1",
        "anthropic/claude-opus-4",
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.5-haiku",
        "google/gemini-2.5-pro-preview",
        "google/gemini-2.0-flash",
        "deepseek/deepseek-chat",
        "deepseek/deepseek-r1",
        "meta-llama/llama-3.3-70b-instruct",
        "qwen/qwen-2.5-72b-instruct",
    ],
    "claude": [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
}


def split_text(text: str) -> list[str]:
    """按 <p> 段落边界切分 HTML；无段落结构时按字符切分。
    确保不在 HTML 标签中间切断，避免翻译输出截断末尾段落。"""
    if len(text) <= CHUNK_SIZE:
        return [text]

    paras = [str(p) for p in BeautifulSoup(text, "html.parser").find_all("p")]
    if not paras:
        # 无段落结构，退回字符切分
        return [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for p in paras:
        if size + len(p) > CHUNK_SIZE and current:
            chunks.append("\n".join(current))
            current, size = [p], len(p)
        else:
            current.append(p)
            size += len(p)
    if current:
        chunks.append("\n".join(current))
    return chunks


async def translate_text(
    text: str,
    provider: str,
    api_key: str,
    model: str | None = None,
    target_lang: str = "zh-CN",
    base_url: str | None = None,
) -> str:
    """翻译文本，失败则返回原文。model 为 None 时使用该提供方默认模型。
    base_url 非空时覆盖 PROVIDER_BASE_URLS 中的默认值。"""
    if not text:
        return text

    resolved_model = model or PROVIDER_DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    # 创建客户端（复用连接池）
    if provider in PROVIDER_BASE_URLS:
        resolved_base_url = base_url or PROVIDER_BASE_URLS[provider]
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=resolved_base_url,
        )
    elif provider == "claude":
        client = AsyncAnthropic(api_key=api_key, base_url=base_url) if base_url else AsyncAnthropic(api_key=api_key)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")

    chunks = split_text(text)
    translated_chunks = []
    for chunk in chunks:
        try:
            translated = await _translate_chunk(chunk, provider, client, resolved_model, target_lang)
            translated_chunks.append(translated)
        except Exception as exc:
            logger.error(
                "Translation failed for provider=%s model=%s target=%s error=%s",
                provider, resolved_model, target_lang, exc,
                exc_info=True,
            )
            return text
    return "".join(translated_chunks)


async def _translate_chunk(
    text: str,
    provider: str,
    client,
    model: str,
    target_lang: str,
) -> str:
    prompt = (
        f"Translate the following content to {target_lang}. "
        f"If the input contains HTML tags, preserve all tags exactly and only translate the visible text. "
        f"Return only the translated content, no explanations.\n\n{text}"
    )

    if provider in PROVIDER_BASE_URLS:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )
        return response.choices[0].message.content.strip()

    else:  # provider == "claude"
        response = await client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
