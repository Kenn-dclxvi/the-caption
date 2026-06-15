import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

# .envファイルを読み込む
load_dotenv(dotenv_path=BASE_DIR / ".env")

def run_test_email():
    print("--- Gmail Send Test ---")

    # 設定の読み込み
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    to_addr = os.getenv("SMTP_TO")

    # 設定チェック
    if not all([user, password, to_addr]):
        print("エラー: .envファイルに SMTP_USER, SMTP_PASS, SMTP_TO が設定されていません。")
        return

    print(f"送信元: {user}")
    print(f"送信先: {to_addr}")

    # メール作成
    msg = MIMEMultipart()
    msg['Subject'] = "【テスト】Finance REPORT 接続確認"
    msg['From'] = user
    msg['To'] = to_addr
    body = "これはMac miniからのテスト送信です。\nこのメールが届けば、設定は完了しています。"
    msg.attach(MIMEText(body, 'plain'))

    # 送信処理
    try:
        print("サーバーに接続中...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user, password)
            server.send_message(msg)
        print("✅ 送信成功！受信トレイを確認してください。")
    except Exception as e:
        print(f"❌ 送信失敗: {e}")
        print("ヒント: アプリパスワードが正しいか、または2段階認証が有効か確認してください。")

if __name__ == "__main__":
    run_test_email()
