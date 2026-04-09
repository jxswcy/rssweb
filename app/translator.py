import logging
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

CHUNK_SIZE = 2000


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
    target_lang: str = "zh-CN",
) -> str:
    """翻译文本，失败则返回原文"""
    if not text:
        return text
    chunks = split_text(text)
    # 在此处创建客户端，复用连接池
    if provider == "openai":
        client = AsyncOpenAI(api_key=api_key)
    elif provider == "claude":
        client = AsyncAnthropic(api_key=api_key)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")

    translated_chunks = []
    for chunk in chunks:
        try:
            translated = await _translate_chunk(chunk, provider, client, target_lang)
            translated_chunks.append(translated)
        except Exception as exc:
            logger.warning("Translation failed for chunk, returning original. Error: %s", exc)
            return text  # 任意 chunk 失败则返回整段原文
    return "".join(translated_chunks)


async def _translate_chunk(
    text: str,
    provider: str,
    client,
    target_lang: str,
) -> str:
    prompt = (
        f"Please translate the following text to {target_lang}. "
        f"Return only the translated text, no explanations.\n\n{text}"
    )

    if provider == "openai":
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    else:  # provider == "claude"
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
