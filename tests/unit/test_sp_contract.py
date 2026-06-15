from __future__ import annotations

import io
import runpy
from contextlib import redirect_stdout
from pathlib import Path


SP_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "sp"


def load_sp_namespace():
    return runpy.run_path(str(SP_PATH))


def test_emit_markdown_result_uses_fixed_markdown_layout():
    ns = load_sp_namespace()
    buf = io.StringIO()

    with redirect_stdout(buf):
        ns["emit_markdown_result"](
            "[SP] SUCCESS",
            status="SUCCESS",
            commit="abc123",
            branch="main",
            pr="https://example.invalid/pr/1",
            message="配信処理を完了しました",
        )

    assert buf.getvalue().splitlines() == [
        "[SP] SUCCESS",
        "### 実行結果",
        "- 状態: `SUCCESS`",
        "- コミット: `abc123`",
        "- ブランチ: `main`",
        "- PR: `https://example.invalid/pr/1`",
        "- メッセージ: `配信処理を完了しました`",
    ]


def test_format_failure_message_includes_phase_kind_and_reason():
    ns = load_sp_namespace()
    message = ns["format_failure_message"](
        {"failure_phase": "REMOTE_PUBLICATION", "failure_kind": "PR"},
        RuntimeError("boom"),
    )

    assert message == "工程=REMOTE_PUBLICATION 種別=PR 理由=boom"


def test_result_fields_prefers_merged_commit_then_commit_then_head():
    ns = load_sp_namespace()

    merged = ns["result_fields"](
        {"merged_commit_sha": "merge", "commit_sha": "commit", "head": "head", "work_branch": "feat", "pr_url": "pr"},
        status="SUCCESS",
        message="ok",
    )
    fallback = ns["result_fields"](
        {"head": "head", "base_branch": "main"},
        status="SKIP",
        message="skip",
    )

    assert merged == {
        "status": "SUCCESS",
        "commit": "merge",
        "branch": "feat",
        "pr": "pr",
        "message": "ok",
    }
    assert fallback == {
        "status": "SKIP",
        "commit": "head",
        "branch": "main",
        "pr": "-",
        "message": "skip",
    }
