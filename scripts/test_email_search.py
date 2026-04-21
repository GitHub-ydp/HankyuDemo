"""快速测试邮件检索链路：加载模型 → 建索引 → 搜索"""
import sys
import os
import time

# 将 backend 加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.email_search_service import index_emails, search_emails


def main():
    # 1. 建索引
    print("=" * 60)
    print("步骤1: 建立邮件向量索引")
    print("(首次运行需下载 BGE-M3 模型，约 2GB，请耐心等待)")
    print("=" * 60)
    t0 = time.time()
    result = index_emails(force=True)
    t1 = time.time()
    print(f"索引结果: {result}")
    print(f"耗时: {t1 - t0:.1f}s")

    # 2. 测试检索 — 多个场景
    test_queries = [
        # 跨语言：用中文搜日文邮件
        ("丰田汽车的投标结果", "中文搜日文"),
        # 用中文搜英文邮件
        ("越南胡志明市的运费报价", "中文搜英文"),
        # 日文搜索
        ("航空運賃の見積", "日文搜日文"),
        # 英文搜索
        ("rate increase Europe", "英文搜日文/中文"),
        # 业务场景：查某个客户
        ("三菱电机 中国航线", "查特定客户"),
        # 业务场景：查运价变动
        ("COSCO 运价调整 4月", "查运价变动"),
    ]

    print("\n" + "=" * 60)
    print("步骤2: 检索测试")
    print("=" * 60)

    for query, desc in test_queries:
        print(f"\n--- [{desc}] 查询: \"{query}\" ---")
        t0 = time.time()
        results = search_emails(query, top_k=3)
        t1 = time.time()
        print(f"  耗时: {(t1 - t0) * 1000:.0f}ms, 返回 {len(results)} 条")
        for r in results:
            print(f"  [{r['score']:.3f}] {r['subject']}")
            print(f"         {r['from_name']} | {r['date'][:10]} | {r['language']}")


if __name__ == "__main__":
    main()
