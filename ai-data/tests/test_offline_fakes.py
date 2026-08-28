import json

from tests.fakes import DeterministicFakeEmbeddings, DeterministicFakeOpenAI


def test_fake_embedding_is_deterministic_and_normalized():
    first = DeterministicFakeEmbeddings(dimension=32)
    second = DeterministicFakeEmbeddings(dimension=32)

    assert first.embed_query("Pod CrashLoopBackOff") == second.embed_query(
        "Pod CrashLoopBackOff"
    )
    assert first.embed_query("Pod CrashLoopBackOff") != first.embed_query("service selector")


def test_fake_chat_returns_fixed_text_for_matching_input():
    client = DeterministicFakeOpenAI({"CrashLoop": "로그에서 어떤 종료 원인이 보이나요?"})

    response = client.chat.completions.create(
        model="fake-model",
        messages=[{"role": "user", "content": "CrashLoop 상태입니다"}],
    )

    assert response.choices[0].message.content == "로그에서 어떤 종료 원인이 보이나요?"
    assert response.usage.total_tokens == 20


def test_fake_chat_json_response_can_be_parsed_without_provider():
    expected = {"environment": "docker", "fault_type": "container_oom"}
    client = DeterministicFakeOpenAI({"scenario": expected})

    response = client.chat.completions.create(
        model="fake-model",
        messages=[{"role": "user", "content": "scenario"}],
    )

    assert json.loads(response.choices[0].message.content) == expected
