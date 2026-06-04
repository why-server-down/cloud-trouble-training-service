#!/usr/bin/env python3
"""
환경 변수 로드 검증 스크립트
Backend 서버가 .env 파일을 올바르게 읽는지 확인
"""

import sys
from pathlib import Path

# Backend 앱 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings


def main():
    print("=" * 80)
    print("  Backend Environment Variables Verification")
    print("=" * 80)
    print()
    
    print("📊 Database Configuration:")
    print(f"  DATABASE_URL: {settings.DATABASE_URL}")
    print(f"  SECRET_KEY: {settings.SECRET_KEY[:20]}... (masked)")
    print()
    
    print("🎮 Mission System Configuration:")
    print(f"  CHAOS_BACKEND: {settings.CHAOS_BACKEND}")
    print(f"  VALIDATION_BACKEND: {settings.VALIDATION_BACKEND}")
    print(f"  MOCK_VALIDATION_AUTO_PASS: {settings.MOCK_VALIDATION_AUTO_PASS}")
    print(f"  PROMETHEUS_URL: {settings.PROMETHEUS_URL}")
    print()
    
    print("🤖 AI Backend Configuration:")
    print(f"  AI_BACKEND: {settings.AI_BACKEND}")
    print()
    
    if settings.AI_BACKEND == "openai" or settings.OPENAI_API_KEY:
        print("  OpenAI Configuration:")
        api_key_status = "✓ Set" if settings.OPENAI_API_KEY else "✗ Not Set"
        print(f"    OPENAI_API_KEY: {api_key_status}")
        if settings.OPENAI_API_KEY:
            print(f"      (Key: {settings.OPENAI_API_KEY[:10]}... - length: {len(settings.OPENAI_API_KEY)})")
        print(f"    OPENAI_MODEL: {settings.OPENAI_MODEL}")
        print(f"    SCENARIO_MODEL: {settings.SCENARIO_MODEL}")
        print(f"    TUTOR_MODEL: {settings.TUTOR_MODEL}")
        print(f"    EMBEDDING_MODEL: {settings.EMBEDDING_MODEL}")
        print()
    
    if settings.AI_BACKEND == "gemini" or settings.GEMINI_API_KEY:
        print("  Gemini Configuration:")
        api_key_status = "✓ Set" if settings.GEMINI_API_KEY else "✗ Not Set"
        print(f"    GEMINI_API_KEY: {api_key_status}")
        if settings.GEMINI_API_KEY:
            print(f"      (Key: {settings.GEMINI_API_KEY[:10]}... - length: {len(settings.GEMINI_API_KEY)})")
        print(f"    GEMINI_MODEL: {settings.GEMINI_MODEL}")
        print(f"    GEMINI_EMBEDDING_MODEL: {settings.GEMINI_EMBEDDING_MODEL}")
        print()
    
    print("🔍 RAG System Configuration:")
    print(f"  QDRANT_URL: {settings.QDRANT_URL}")
    qdrant_key_status = "✓ Set" if settings.QDRANT_API_KEY else "✗ Not Set (OK for local)"
    print(f"  QDRANT_API_KEY: {qdrant_key_status}")
    print(f"  KNOWLEDGE_BASE_DIR: {settings.KNOWLEDGE_BASE_DIR}")
    print()
    
    print("=" * 80)
    print("  Verification Result")
    print("=" * 80)
    print()
    
    # 검증
    issues = []
    
    if settings.AI_BACKEND == "gemini" and not settings.GEMINI_API_KEY:
        issues.append("⚠️  GEMINI_API_KEY is not set but AI_BACKEND=gemini")
    
    if settings.AI_BACKEND == "openai" and not settings.OPENAI_API_KEY:
        issues.append("⚠️  OPENAI_API_KEY is not set but AI_BACKEND=openai")
    
    if settings.GEMINI_MODEL != "gemini-2.5-flash-lite":
        issues.append(f"⚠️  GEMINI_MODEL should be 'gemini-2.5-flash-lite', got '{settings.GEMINI_MODEL}'")
    
    if settings.GEMINI_EMBEDDING_MODEL != "models/gemini-embedding-001":
        issues.append(f"⚠️  GEMINI_EMBEDDING_MODEL should be 'models/gemini-embedding-001', got '{settings.GEMINI_EMBEDDING_MODEL}'")
    
    if issues:
        print("❌ Issues Found:")
        for issue in issues:
            print(f"  {issue}")
        print()
        return 1
    else:
        print("✅ All environment variables are correctly configured!")
        print()
        print("Next steps:")
        print("  1. Start Qdrant server: docker run -p 6333:6333 qdrant/qdrant")
        print("  2. Ingest knowledge base: cd ../ai-data && python scripts/ingest_knowledge.py")
        print("  3. Start backend server: uvicorn app.main:app --reload")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
