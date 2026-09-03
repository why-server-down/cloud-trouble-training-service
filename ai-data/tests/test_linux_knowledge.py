import json
import re
from pathlib import Path

from config import AISettings
from ingest import attach_chunk_metadata, load_all_documents
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag_service import RAGService


AI_DATA_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = AI_DATA_DIR / "knowledge-base"
LINUX_DIR = KNOWLEDGE_BASE_DIR / "08-linux"
EVAL_DATASET = AI_DATA_DIR / "evals" / "linux_retrieval_questions.json"
REQUIRED_FAULT_TYPES = {
    "linux_oom", "disk_io_stress", "zombie_process",
    "orphan_process", "service_failure",
}
PRODUCTION_FAULT_TYPES = {
    "linux_disk_pressure", "linux_cpu_saturation", "linux_process_flood",
}
REQUIRED_SECTIONS = (
    "## Symptoms", "## Observations", "## Hypotheses", "## Safe commands",
    "## Recovery validation", "## Hint-level concepts",
    "## Sandbox safety boundary",
)


def _linux_documents():
    return [
        document
        for document in load_all_documents(KNOWLEDGE_BASE_DIR)
        if document.metadata["environments"] == ["linux"]
    ]


def _shell_commands(content: str) -> list[str]:
    blocks = re.findall(r"```bash\n(.*?)```", content, flags=re.DOTALL)
    return [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_seven_linux_documents_cover_required_faults():
    documents = _linux_documents()
    covered_faults = {
        fault for document in documents for fault in document.metadata["fault_types"]
    }

    assert len(documents) == 7
    assert REQUIRED_FAULT_TYPES <= covered_faults
    assert PRODUCTION_FAULT_TYPES <= covered_faults
    assert all(document.metadata["version"] == "2026-08-29" for document in documents)


def test_each_document_has_learning_structure_and_primary_source():
    for document in _linux_documents():
        for section in REQUIRED_SECTIONS:
            assert section in document.page_content
        assert any(
            source in document.page_content
            for source in ("https://docs.kernel.org/", "https://man7.org/", "https://www.freedesktop.org/")
        )


def test_examples_are_read_only_capability_gated_commands():
    allowed_commands = {
        "ps -eo pid,ppid,stat,comm", "free -m", "df -h",
        "du -sh /workspace", "ss -lnt",
    }
    for document in _linux_documents():
        assert "capability" in document.page_content
        for command in _shell_commands(document.page_content):
            assert command in allowed_commands
            assert not command.startswith(("sudo", "kill", "pkill", "mount", "sysctl"))


def test_optional_tools_are_not_claimed_as_unconditional():
    combined = "\n".join(document.page_content for document in _linux_documents())

    assert "systemd가 없을 수 있으므로" in combined
    assert "capability에 명시된 경우에만" in combined
    assert "호스트 PID namespace는 노출하지 않는다" in combined


def test_linux_eval_has_twenty_questions_and_all_faults():
    payload = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))
    questions = payload["questions"]

    assert payload["environment"] == "linux"
    assert len(questions) >= 20
    assert len({question["id"] for question in questions}) == len(questions)
    assert {question["fault_type"] for question in questions} == REQUIRED_FAULT_TYPES
    assert all(question["query"] and question["expected_source_id"] for question in questions)


def test_eval_expected_sources_exist_in_linux_manifest():
    source_ids = {document.metadata["source_id"] for document in _linux_documents()}
    questions = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))["questions"]

    assert {question["expected_source_id"] for question in questions} <= source_ids


def test_linux_retrieval_recall_at_five_meets_target():
    documents = _linux_documents()
    chunks = attach_chunk_metadata(
        RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(
            documents
        )
    )
    rag = RAGService(
        collection_name="linux_knowledge_eval",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock", RAG_MIN_SIMILARITY=0),
    )
    rag.ingest_documents(chunks)
    questions = json.loads(EVAL_DATASET.read_text(encoding="utf-8"))["questions"]

    hits = 0
    for question in questions:
        results = rag.search_knowledge(
            question["query"],
            environment="linux",
            fault_type=question["fault_type"],
            top_k=5,
            min_similarity=0,
        )
        hits += question["expected_source_id"] in {
            result.metadata.get("source_id") for result in results
        }

    assert hits / len(questions) >= 0.85
