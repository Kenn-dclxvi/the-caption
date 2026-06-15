from unittest.mock import patch

from src.infra.knowledge_manager import KnowledgeManager


def _write_kb(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestKnowledgeManagerWeeklyExtraction:

    def test_extract_weekly_insights_skips_invalid_calendar_dates(self, tmp_path):
        kb_file = tmp_path / "knowledge_bank.md"
        _write_kb(
            str(kb_file),
            "\n\n".join(
                [
                    "## 2026-03-03\n- **Theme**: A\n- **Overview**: OA\n- **Insight**: IA\n- **Shield**: SA",
                    "## 2026-13-40\n- **Theme**: B\n- **Overview**: OB\n- **Insight**: IB\n- **Shield**: SB",
                    "## 2026-03-04\n- **Theme**: C\n- **Overview**: OC\n- **Insight**: IC\n- **Shield**: SC",
                ]
            ),
        )

        with patch.object(KnowledgeManager, "_KnowledgeManager__KNOWLEDGE_FILE", str(kb_file)):
            manager = KnowledgeManager()
            result = manager.extract_weekly_insights("2026-W10")

        assert [r["date"] for r in result] == ["2026-03-03", "2026-03-04"]

    def test_extract_weekly_insights_returns_empty_for_non_matching_week(self, tmp_path):
        kb_file = tmp_path / "knowledge_bank.md"
        _write_kb(
            str(kb_file),
            "## 2026-03-03\n- **Theme**: A\n- **Overview**: OA\n- **Insight**: IA\n- **Shield**: SA",
        )

        with patch.object(KnowledgeManager, "_KnowledgeManager__KNOWLEDGE_FILE", str(kb_file)):
            manager = KnowledgeManager()
            result = manager.extract_weekly_insights("2026-W11")

        assert result == []

    def test_record_insight_writes_archive_context_lines(self, tmp_path):
        kb_file = tmp_path / "knowledge_bank.md"
        with patch.object(KnowledgeManager, "_KnowledgeManager__KNOWLEDGE_FILE", str(kb_file)):
            manager = KnowledgeManager()
            result = manager.record_insight(
                "2026-04-24",
                {
                    "display_context": {
                        "state": "WATCH",
                        "primary": "NYFANG / -0.54pt",
                        "policy": "WATCH / ADEQUATE / HIGH",
                        "shield": "NEUTRAL",
                    },
                    "archive_context": {
                        "causal_vector": "TECH_DRIVEN",
                        "market_regime": "CALM",
                        "fx_effect": "MINOR",
                        "vix_band": "CALM",
                        "monthly_tags": ["TECH_CONCENTRATION", "LOW_VIX"],
                        "short_note": "月次用の短い因果メモ",
                    },
                    "theme": "T",
                    "overview": "O",
                    "implication": "I",
                    "shield_evaluation": "S",
                },
            )

        assert result is True
        content = kb_file.read_text(encoding="utf-8")
        assert "- **State**: WATCH | NYFANG / -0.54pt | WATCH / ADEQUATE / HIGH | NEUTRAL" in content
        assert "- **Archive**: TECH_DRIVEN | CALM | MINOR | CALM | TECH_CONCENTRATION,LOW_VIX" in content
        assert "- **Archive Note**: 月次用の短い因果メモ" in content
