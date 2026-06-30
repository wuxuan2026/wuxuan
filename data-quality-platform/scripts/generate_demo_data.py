"""生成 demo 电商数据：3 张表（orders / customers / arrivals），订单表故意包含各类质量问题。

质量问题注入比例（可演示出非 100 分）：
- 完整性：少量 order_id 为空、重复、order_amount 超范围
- 规范性：邮箱格式错、order_status 枚举违规、order_date 类型错
- 一致性：discount > order_amount、customer_id 引用不存在的客户（外键失败）
- 时效性：让一部分订单日期比"今天"早很多天（freshness 失败）、让一部分 arrivals 实际时间延迟
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

random.seed(42)

# 以今天为基准，模拟"已过期"的订单
TODAY = datetime(2026, 6, 29)


def gen_customers(n: int = 200) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "customer_id": f"C{i:05d}",
            "customer_name": random.choice(["张", "李", "王", "赵", "陈", "林", "黄", "周"]) + "**",
            "register_date": (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 600))).date().isoformat(),
        })
    return pd.DataFrame(rows)


def _bad_email() -> str:
    forms = ["noatsign.com", "double@@at.com", "@no-local.com", "spaces in@addr.com", "plainname"]
    return random.choice(forms)


def _bad_status() -> str:
    return random.choice(["refund_pending", "unknown", "PROCESSING", "已发货"])


def gen_orders(n: int = 500) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        order_id = f"O{i:06d}"
        # ~2% 概率：order_id 缺失（设空字符串）
        if random.random() < 0.02:
            order_id = ""
        # ~1% 概率：与前面的订单号重复
        elif i > 1 and random.random() < 0.01:
            order_id = f"O{i - 1:06d}"

        # 大部分订单日期在最近几天，但 ~10% 在 30 天前（freshness 失败）
        if random.random() < 0.10:
            order_date = (TODAY - timedelta(days=random.randint(15, 60))).date().isoformat()
        else:
            order_date = (TODAY - timedelta(days=random.randint(0, 4))).date().isoformat()

        order_amount = round(random.uniform(10, 5000), 2)
        discount = round(random.uniform(0, 50), 2)
        # ~3% 概率：discount > order_amount（cross_field 失败）
        if random.random() < 0.03:
            discount = round(order_amount + random.uniform(10, 500), 2)
        # ~2% 概率：order_amount 超出 100000（range 失败）
        if random.random() < 0.02:
            order_amount = round(random.uniform(100001, 200000), 2)

        order_status = random.choice(["pending", "paid", "shipped", "delivered", "cancelled"])
        # ~3% 概率：枚举违规
        if random.random() < 0.03:
            order_status = _bad_status()

        customer_id = f"C{random.randint(1, 200):05d}"
        # ~2% 概率：引用不存在的客户（外键失败）
        if random.random() < 0.02:
            customer_id = f"C{random.randint(900, 999):05d}"

        customer_email = f"user{random.randint(1, 200)}@example.com"
        # ~5% 概率：邮箱格式错
        if random.random() < 0.05:
            customer_email = _bad_email()

        # ~1% 概率：order_date 是乱字符串（type 失败）
        if random.random() < 0.01:
            order_date = "not-a-date"

        # 业务字段：paid = amount - discount（仅当 discount <= amount 时）
        if discount <= order_amount:
            paid_amount = round(order_amount - discount, 2)
        else:
            paid_amount = 0.0  # discount 异常时不再计算 paid
        # ~2% 概率：refund 不为零（一般在 0），构造 sum_check 失败
        refund_amount = 0.0
        if random.random() < 0.02:
            refund_amount = round(random.uniform(1, 50), 2)
            # 同时让 paid 少扣这块（破坏 paid + refund = amount）
            paid_amount = max(0.0, paid_amount - refund_amount)

        rows.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "order_date": order_date,
            "order_amount": order_amount,
            "discount": discount,
            "paid_amount": paid_amount,
            "refund_amount": refund_amount,
            "order_status": order_status,
            "customer_email": customer_email,
        })
    return pd.DataFrame(rows)


def gen_arrivals(orders: pd.DataFrame) -> pd.DataFrame:
    """数据到达记录：按 order_date + 2:00 期望到达，但 ~10% 延迟 2~12 小时。"""
    rows = []
    for _, o in orders.iterrows():
        # 跳过 order_id 为空的行（避免无效 join）
        if not o["order_id"]:
            continue
        try:
            od = datetime.fromisoformat(o["order_date"])
        except Exception:
            od = TODAY - timedelta(days=1)
        expected = od.replace(hour=2, minute=0, second=0)
        # ~10% 概率：实际到达延迟
        if random.random() < 0.10:
            actual = expected + timedelta(minutes=random.randint(120, 720))  # 2-12 小时延迟
        else:
            actual = expected + timedelta(minutes=random.randint(-5, 20))
        rows.append({
            "order_id": o["order_id"],
            "expected_arrival": expected.strftime("%Y-%m-%d %H:%M:%S"),
            "actual_arrival": actual.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return pd.DataFrame(rows)


def main() -> None:
    customers = gen_customers()
    orders = gen_orders()
    arrivals = gen_arrivals(orders)

    customers.to_csv(OUT / "customers.csv", index=False, encoding="utf-8-sig")
    orders.to_csv(OUT / "orders.csv", index=False, encoding="utf-8-sig")
    arrivals.to_csv(OUT / "arrivals.csv", index=False, encoding="utf-8-sig")

    print(f"已生成 demo 数据（含质量问题）到 {OUT}")
    print(f"  customers.csv: {len(customers)} 行")
    print(f"  orders.csv:    {len(orders)} 行")
    print(f"  arrivals.csv:  {len(arrivals)} 行")


if __name__ == "__main__":
    main()