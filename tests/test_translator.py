import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.translator import translate_text, split_text, CHUNK_SIZE

def test_split_text_short():
    text = "Hello world"
    chunks = split_text(text)
    assert chunks == ["Hello world"]

def test_split_text_long():
    text = "x" * (CHUNK_SIZE + 100)
    chunks = split_text(text)
    assert len(chunks) == 2
    assert all(len(c) <= CHUNK_SIZE for c in chunks)

@pytest.mark.asyncio
async def test_translate_with_openai():
    with patch("app.translator.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="你好世界"))]
            )
        )
        result = await translate_text(
            text="Hello world",
            provider="openai",
            api_key="sk-test",
            target_lang="zh-CN",
        )
    assert result == "你好世界"

@pytest.mark.asyncio
async def test_translate_with_claude():
    with patch("app.translator.AsyncAnthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=MagicMock(
                content=[MagicMock(text="你好世界")]
            )
        )
        result = await translate_text(
            text="Hello world",
            provider="claude",
            api_key="sk-ant-test",
            target_lang="zh-CN",
        )
    assert result == "你好世界"

@pytest.mark.asyncio
async def test_translate_returns_original_on_error():
    with patch("app.translator.AsyncOpenAI") as MockOpenAI:
        MockOpenAI.return_value.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        result = await translate_text(
            text="Hello world",
            provider="openai",
            api_key="sk-test",
            target_lang="zh-CN",
        )
    assert result == "Hello world"
