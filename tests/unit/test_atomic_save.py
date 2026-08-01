import json
import pytest
from unittest.mock import patch

import src.infra.context_repository as ctx_mod
import src.infra.chronicle_repository as chr_mod
import src.infra.knowledge_manager as km_mod
from src.infra.context_repository import ContextRepository
from src.infra.chronicle_repository import ChronicleRepository
from src.infra.knowledge_manager import KnowledgeManager


class TestContextRepositoryAtomicSave:

    def test_save_success(self, tmp_path):
        with patch.object(ctx_mod, "DIR_CURRENT", str(tmp_path)):
            repo = ContextRepository()
            data = {"key": "value", "日本語": "テスト"}
            result = repo.save(data, "2026-03-02")
        assert result is True
        saved = tmp_path / "context_20260302.json"
        assert saved.exists()
        assert json.loads(saved.read_text(encoding="utf-8")) == data
        assert list(tmp_path.glob("*.json.tmp")) == []

    def test_save_failure_cleans_up_temp(self, tmp_path):
        with patch.object(ctx_mod, "DIR_CURRENT", str(tmp_path)):
            with patch("src.infra.context_repository.os.replace", side_effect=OSError("replace failed")):
                repo = ContextRepository()
                result = repo.save({"k": "v"}, "2026-03-02")
        assert result is False
        assert list(tmp_path.glob("*.json.tmp")) == []


class TestChronicleRepositoryAtomicSave:

    def test_save_success(self, tmp_path):
        with patch.object(chr_mod, "DIR_CURRENT", str(tmp_path)):
            repo = ChronicleRepository()
            data = {"month": "2026-03", "日本語": "テスト"}
            result = repo.save(data, "2026-03")
        assert result is True
        saved = tmp_path / "chronicle_202603.json"
        assert saved.exists()
        assert json.loads(saved.read_text(encoding="utf-8")) == data
        assert list(tmp_path.glob("*.json.tmp")) == []

    def test_save_failure_cleans_up_temp(self, tmp_path):
        with patch.object(chr_mod, "DIR_CURRENT", str(tmp_path)):
            with patch("src.infra.chronicle_repository.os.replace", side_effect=OSError("replace failed")):
                repo = ChronicleRepository()
                result = repo.save({"k": "v"}, "2026-03")
        assert result is False
        assert list(tmp_path.glob("*.json.tmp")) == []

class TestKnowledgeManagerAtomicSave:

    def test_write_success(self, tmp_path):
        kb_file = tmp_path / "knowledge_bank.md"
        with patch.object(KnowledgeManager, '_KnowledgeManager__KNOWLEDGE_FILE', str(kb_file)):
            manager = KnowledgeManager()
            result = manager.record_insight("2026-03-01", {
                "theme": "BULL", "overview": "Overview",
                "implication": "Insight", "shield_evaluation": "S",
            })
        assert result is True
        assert kb_file.exists()
        assert list(tmp_path.glob("*.md.tmp")) == []

    def test_write_failure_cleans_up_temp(self, tmp_path):
        kb_file = tmp_path / "knowledge_bank.md"
        with patch.object(KnowledgeManager, '_KnowledgeManager__KNOWLEDGE_FILE', str(kb_file)):
            with patch("src.infra.knowledge_manager.os.replace", side_effect=OSError("replace failed")):
                manager = KnowledgeManager()
                manager.record_insight("2026-03-01", {
                    "theme": "BULL", "overview": "Overview",
                    "implication": "Insight", "shield_evaluation": "S",
                })
        assert not kb_file.exists()
        assert list(tmp_path.glob("*.md.tmp")) == []
