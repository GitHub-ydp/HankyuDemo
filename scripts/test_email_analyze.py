"""测试邮件分析完整链路：索引 → 检索 → AI 时间线汇总"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.email_search_service import index_mock_emails, analyze_emails


def main():
    # 1. 建索引（如果已有则跳过）
    print("=" * 60)
    print("步骤1: 建立邮件索引")
    print("=" * 60)
    t0 = time.time()
    result = index_mock_emails(force=False)
    print(f"索引结果: {result}  耗时: {time.time() - t0:.1f}s")

    # 2. 测试分析
    test_queries = [
        "检索和丰田汽车相关的所有往来邮件，按时间线进行概括汇总",
        "近期有哪些运价变动通知？影响了哪些客户和航线？",
        "三菱电机的入札进展如何？目前到什么阶段了？",
    ]

    for query in test_queries:
        print("\n" + "=" * 60)
        print(f"查询: {query}")
        print("=" * 60)
        t0 = time.time()
        result = analyze_emails(query, top_k=10)
        elapsed = time.time() - t0

        print(f"检索到 {result['count']} 封相关邮件，分析耗时 {elapsed:.1f}s")
        print(f"\n匹配邮件:")
        for e in result["emails"][:5]:
            print(f"  [{e['date'][:10]}] {e['subject']}")
        print(f"\nAI 分析结果:")
        print(result["analysis"])


if __name__ == "__main__":
    main()
