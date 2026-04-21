"""测试不同 IMAP 服务器地址"""
import imaplib
import ssl

EMAIL = "zdx@hcctc.cn"
PASSWORD = "buzhidao@123"

# 阿里云企业邮箱常见 IMAP 地址
SERVERS = [
    ("imap.qiye.aliyun.com", 993),
    ("imap.mxhichina.com", 993),
    ("imap.aliyun.com", 993),
]

for host, port in SERVERS:
    print(f"尝试连接 {host}:{port} ... ", end="", flush=True)
    try:
        mail = imaplib.IMAP4_SSL(host, port)
        print(f"连接成功! ", end="")
        try:
            mail.login(EMAIL, PASSWORD)
            print("登录成功!")
            # 列出所有文件夹
            status, folders = mail.list()
            if status == "OK":
                print("  邮箱文件夹:")
                for f in folders:
                    print(f"    {f.decode()}")
            mail.logout()
        except Exception as e:
            print(f"登录失败: {e}")
            mail.logout()
    except Exception as e:
        print(f"连接失败: {e}")
    print()
