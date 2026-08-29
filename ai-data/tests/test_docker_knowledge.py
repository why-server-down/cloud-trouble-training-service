import json
import re
from pathlib import Path

from config import AISettings
from ingest import attach_chunk_metadata, load_all_documents
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag_service import RAGService


AI_DATA_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = AI_DATA_DIR / "knowledge-base"
DOCKER_DIR = KNOWLEDGE_BASE_DIR / "07-docker"
EVAL_DATASET = AI_DATA_DIR / "evals" / "docker_retrieval_questions.json"
REQUIRED_FAULT_TYPES = {
    "container_network_disconnect",
    "volume_mount_error",
    "container_oom",
    "container_cpu_throttle",
}
REQUIRED_SECTIONS = (
    "## Symptoms",
    "## Observations",
    "## Hypotheses",
    "## Safe commands",
    "## Recovery validation",
    "## Hint-level concepts",
    "## Sandbox safety boundary",
)


def _docker_documents():
    return [
        document
        for document in load_all_documents(KNOWLEDGE_BASE_DIR)
        if document.metadata["environments"] == ["docker"]
    ]


def _shell_commands(content: str) -> list[str]:
    blocks = re.findall(r"```bash\n(.*?)```", content, flags=re.DOTALL)
    return [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_six_required_docker_documents_are_registered():
    documents = _docker_documents()

    assert len(documents) == 6
    covered_faults = {
        fault_type
        for document in documents
        for fault_type in document.metadata["fault_types"]
    }
    assert REQUIRED_FAULT_TYPES <= covered_faults
    assert all(document.metadata["version"] == "2026-08-29" for document in documents)


def test_each_document_has_learning_and_recovery_structure():
    for document in _docker_documents():
        for section in REQUIRED_SECTIONS:
            assert section in document.page_content, (
                f"{document.metadata['source']}에 {section}가 없습니다"
            )
        assert "https://docs.docker.com/" in document.page_content


def test_command_examples_stay_inside_backend_docker_policy():
    allowed_prefixes = (
        "docker ps", "docker inspect training-app", "docker logs",
        "docker stats", "docker top training-app", "docker port training-app",
        "docker diff training-app", "docker start training-app",
        "docker restart training-app", "docker unpause training-app",
        "docker update", "docker network ls", "docker network inspect training-net",
        "docker network connect training-net training-app", "docker volume ls",
        "docker volume inspect training-data", "docker volume create training-data",
    )
    for document in _docker_documents():
        for command in _shell_commands(document.page_content):
            assert command.startswith(allowed_prefixes), (
                f"backend policy 밖의 예시: {document.metadata['source']}: {command}"
            )
            assert "/var/run/docker.sock" not in command
            assert "--privileged" not in command
            assert not command.startswith(("docker run", "docker exec", "docker -H"))


def test_volume_document_does_not_claim_unsupported_direct_recovery():
    content = (DOCKER_DIR / "storage-troubleshooting.md").read_text(encoding="utf-8")

    assert "복구할 수 없다" in content
    assert "재프로비저닝" in content
    assert "docker run" in content and "차단" in content


def test_docker_eval_has_twenty_questions_and_all_faults():
    payload = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))
    questions = payload["questions"]

    assert payload["environment"] == "docker"
    assert len(questions) >= 20
    assert len({question["id"] for question in questions}) == len(questions)
    assert {question["fault_type"] for question in questions} == REQUIRED_FAULT_TYPES
    assert all(question["query"] and question["expected_source_id"] for question in questions)


def test_eval_expected_sources_exist_in_docker_manifest():
    source_ids = {document.metadata["source_id"] for document in _docker_documents()}
    questions = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))["questions"]

    assert {question["expected_source_id"] for question in questions} <= source_ids


def test_docker_retrieval_recall_at_five_meets_target():
    documents = _docker_documents()
    chunks = attach_chunk_metadata(
        RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(
            documents
        )
    )
    rag = RAGService(
        collection_name="docker_knowledge_eval",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock", RAG_MIN_SIMILARITY=0),
    )
    rag.ingest_documents(chunks)
    questions = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))["questions"]

    hits = 0
    for question in questions:
        results = rag.search_knowledge(
            question["query"],
            fault_type=question["fault_type"],
            top_k=5,
            min_similarity=0,
        )
        source_ids = {result.metadata.get("source_id") for result in results}
        hits += question["expected_source_id"] in source_ids

    assert hits / len(questions) >= 0.85
