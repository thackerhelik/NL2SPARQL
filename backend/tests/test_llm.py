import pytest

from src.internal.llm import chat_message, sanitize_structured_response


@pytest.mark.parametrize(
    "llm_output, expected",
    [
        ("JSON: {'a': 1} End", "{'a': 1}"),
        (
            "Some string {'key': 2, 'key2': 3} some random bla bla bla",
            "{'key': 2, 'key2': 3}",
        ),
        (
            """Sure! Here is the JSON you asked for:
    {
        "entities": ["Vaswani", "Attention is all you need"],
        "metadata": {
            "year_start": "2017",
        }
    }
    I hope that helps!""",
            """{
        "entities": ["Vaswani", "Attention is all you need"],
        "metadata": {
            "year_start": "2017",
        }
    }""",
        ),
    ],
)
def test_sanitize_structured_response_success(llm_output, expected):
    """Test that JSON is correctly extracted from surrounding text."""

    result = sanitize_structured_response(llm_output)
    assert result.strip() == expected.strip()


def test_sanitize_structured_response_no_json():
    """Test that a ValueError is raised when no JSON is found"""

    llm_output = "I'm sorry, I couldn't find any information"

    # with pytest.raises(ValueError, match="No JSON object found in the response"):
    #     sanitize_structured_response(llm_output)

    with pytest.raises(ValueError) as excinfo:
        sanitize_structured_response(llm_output)

    assert "No JSON object found in the response" in str(excinfo.value)
    assert excinfo.type is ValueError


@pytest.mark.asyncio
async def test_chat_message_routes_by_model_prefix(monkeypatch):
    calls = {"rwth": None, "ollama": None}

    class FakeOpenAICompletions:
        async def create(self, **kwargs):
            calls["rwth"] = kwargs
            return type(
                "Resp",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Msg",
                                    (),
                                    {
                                        "model_dump": lambda self: {
                                            "role": "assistant",
                                            "content": "rwth",
                                        }
                                    },
                                )()
                            },
                        )()
                    ]
                },
            )()

    class FakeOpenAIClient:
        chat = type(
            "Chat",
            (),
            {"completions": FakeOpenAICompletions()},
        )()

    class FakeOllamaClient:
        async def chat(self, **kwargs):
            calls["ollama"] = kwargs
            return type(
                "Resp",
                (),
                {
                    "message": type(
                        "Msg",
                        (),
                        {
                            "model_dump": lambda self: {
                                "role": "assistant",
                                "content": "ollama",
                            }
                        },
                    )()
                },
            )()

    monkeypatch.setattr("src.internal.llm.OPENAI_CLIENT", FakeOpenAIClient())
    monkeypatch.setattr("src.internal.llm.OLLAMA_CLIENT", FakeOllamaClient())

    rwth = await chat_message(
        model="RWTH-GPT-gpt-oss:120b",
        messages=[{"role": "user", "content": "hi"}],
    )
    ollama = await chat_message(
        model="llama3.3:70b",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert rwth["content"] == "rwth"
    assert ollama["content"] == "ollama"
    assert calls["rwth"]["model"] == "gpt-oss:120b"
    assert calls["ollama"]["model"] == "llama3.3:70b"
