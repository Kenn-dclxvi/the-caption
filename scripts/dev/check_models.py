import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.append(str(_PROJECT_ROOT))

import google.generativeai as genai

from src.config.settings import LLM_CONFIG

def main() -> None:
    google_cfg = LLM_CONFIG.get("google", {})
    google_api_key = str(google_cfg.get("api_key") or "")

    # APIキー読み込みチェック
    if not google_api_key:
        print("[ERROR] GOOGLE_API_KEY is not set in .env")
        sys.exit(1)

    genai.configure(api_key=google_api_key)

    print(f"=== Checking Models for API Key ending in ...{google_api_key[-4:]} ===")

    try:
        for m in genai.list_models():
            # テキスト生成(generateContent)に対応しているモデルのみ表示
            if "generateContent" in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"[ERROR] Failed to list models: {e}")


if __name__ == "__main__":
    main()
