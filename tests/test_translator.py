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


@pytest.mark.asyncio
async def test_translate_with_deepseek():
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
            provider="deepseek",
            api_key="sk-deepseek-test",
            model="deepseek-chat",
            target_lang="zh-CN",
        )
    assert result == "你好世界"
    # 验证使用了正确的 base_url
    MockOpenAI.assert_called_once_with(
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com",
    )


@pytest.mark.asyncio
async def test_translate_with_openrouter():
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
            provider="openrouter",
            api_key="sk-or-test",
            model="openai/gpt-4o-mini",
            target_lang="zh-CN",
        )
    assert result == "你好世界"
    MockOpenAI.assert_called_once_with(
        api_key="sk-or-test",
        base_url="https://openrouter.ai/api/v1",
    )


@pytest.mark.asyncio
async def test_translate_uses_custom_model():
    """验证 model 参数被正确传给 API"""
    with patch("app.translator.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        create_mock = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="译文"))]
            )
        )
        mock_client.chat.completions.create = create_mock
        await translate_text(
            text="Hello",
            provider="openai",
            api_key="sk-test",
            model="gpt-4o",
            target_lang="zh-CN",
        )
    call_kwargs = create_mock.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
