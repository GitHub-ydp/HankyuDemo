"""Step2 客户 profile 包。

当前轮次 (T-B4) 仅实现 Customer A。CustomerProfileRegistry + identify_customer
将在 T-B8 交付。Customer B/E/Nitori 的 stub 将在 T-B8 同步补齐（本轮不创建）。
"""
from app.services.step2_bidding.customer_profiles.customer_a import CustomerAProfile

__all__ = ["CustomerAProfile"]
