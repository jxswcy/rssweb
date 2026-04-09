import logging
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000

# 各提供方的 API base URL（None 表示使用 SDK 默认值）
PROVIDER_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}

# 各提供方默认模型
PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "openrouter": "openai/gpt-4o-mini",
    "claude": "claude-3-5-haiku-20241022",
}

# 各提供方推荐模型列表（按翻译质量从高到低）
PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "openrouter": [
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash",
        "deepseek/DeepSeek-V3",
    ],
    "claude": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
}


def split_text(text: str) -> list[str]:
    """按 CHUNK_SIZE 切分文本"""
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE
    return chunks


async def translate_text(
    text: str,
    provider: str,
    api_key: str,
    model: str | None = None,
    target_lang: str = "zh-CN",
) -> str:
    """翻译文本，失败则返回原文。model 为 None 时使用该提供方默认模型。"""
    if not text:
        return text

    resolved_model = model or PROVIDER_DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    # 创建客户端（复用连接池）
    if provider in PROVIDER_BASE_URLS:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS[provider],
        )
    elif provider == "claude":
        client = AsyncAnthropic(api_key=api_key)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")

    chunks = split_text(text)
    translated_chunks = []
    for chunk in chunks:
        try:
            translated = await _translate_chunk(chunk, provider, client, resolved_model, target_lang)
            translated_chunks.append(translated)
        except Exception as exc:
            logger.warning("Translation failed for chunk, returning original. Error: %s", exc)
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
        f"Please translate the following text to {target_lang}. "
        f"Return only the translated text, no explanations.\n\n{text}"
    )

    if provider in PROVIDER_BASE_URLS:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    else:  # provider == "claude"
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
