import os
from pathlib import Path

from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).resolve().parents[2]
KEY_FILE = BASE_DIR / "secret.key"
ENV_FILE = BASE_DIR / ".env"
ENC_FILE = BASE_DIR / ".env.enc"


def generate_key():
    """鍵を生成して保存"""
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    print(f"[SUCCESS] Key generated: {KEY_FILE.name}")
    return key


def load_key():
    """鍵を読み込む"""
    with open(KEY_FILE, "rb") as key_file:
        return key_file.read()


def encrypt_env():
    # 1. 鍵の準備
    if not os.path.exists(KEY_FILE):
        key = generate_key()
    else:
        with open(KEY_FILE, "rb") as f:
            key = f.read()

    fernet = Fernet(key)

    # 2. .envの読み込み
    if not os.path.exists(ENV_FILE):
        print(f"[ERROR] {ENV_FILE} not found.")
        return

    with open(ENV_FILE, "rb") as file:
        original = file.read()

    # 3. 暗号化
    encrypted = fernet.encrypt(original)

    # 4. 書き出し
    with open(ENC_FILE, "wb") as file:
        file.write(encrypted)
    
    print(f"[SUCCESS] Encrypted {ENV_FILE.name} -> {ENC_FILE.name}")
    print("---------------------------------------------------")
    print("【重要】")
    print(f"1. {ENC_FILE.name} が生成されました。")
    print(f"2. {KEY_FILE.name} は絶対に他人に見せないでください。")
    print("3. 動作確認後、元の .env は削除または退避してください。")


if __name__ == "__main__":
    encrypt_env()
