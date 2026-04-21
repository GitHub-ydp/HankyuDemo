"""测试 IMAP 邮件拉取"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.services.email_fetcher import fetch_emails


def main():
    print("正在连接阿里云邮箱 (IMAP)...")
    try:
        emails = fetch_emails(limit=30, since_date="2025-01-01")
        print(f"\n成功拉取 {len(emails)} 封邮件！\n")

        for i, e in enumerate(emails[:15], 1):
            date = e["date"][:10] if e["date"] else "?"
            folder = e.get("folder", "?")
            subj = e["subject"][:60]
            from_info = e["from_name"] or e["from"]
            print(f"  {i:2d}. [{date}] [{folder}] {from_info}")
            print(f"      主题: {subj}")
            if e["has_attachment"]:
                print(f"      附件: {', '.join(e['attachment_names'])}")
            print()

    except Exception as ex:
        print(f"连接失败: {ex}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
