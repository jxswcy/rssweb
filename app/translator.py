from typing import Optional
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

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
    chunks = split_text(text)
    translated_chunks = []
    for chunk in chunks:
        try:
            translated = await _translate_chunk(chunk, provider, api_key, target_lang)
            translated_chunks.append(translated)
        except Exception:
            return text  # 任意 chunk 失败则返回整段原文
    return "".join(translated_chunks)


async def _translate_chunk(
    text: str,
    provider: str,
    api_key: str,
    target_lang: str,
) -> str:
    prompt = (
        f"Please translate the following text to {target_lang}. "
        f"Return only the translated text, no explanations.\n\n{text}"
    )

    if provider == "openai":
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    elif provider == "claude":
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    else:
        raise ValueError(f"Unknown AI provider: {provider}")
