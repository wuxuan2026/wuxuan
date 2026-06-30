"""
生成 demo 数据(CSV),包含有意制造的质量问题,方便看到规则引擎工作。

用法:
    python scripts/generate_demo_data.py           # 生成全部数据集
    python scripts/generate_demo_data.py orders    # 只生成 orders
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

# —— 配置 ——
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "generated"

random.seed(42)  # 固定随机种子,每次生成的"问题"位置一样,便于回归对比

# 订单状态白名单(与 orders_rules.yaml ord_007 一致)
ORDER_STATUSES = ["pending", "paid", "shipped", "delivered", "cancelled"]


# ============================================================
# 工具函数:在数据中"种植"质量问题
# ============================================================
def inject_nulls(series: pd.Series, rate: float) -> pd.Series:
    """把 series 中 rate 比例的值随机置空。"""
    n = len(series)
    idx = random.sample(range(n), k=int(n * rate))
    series = series.copy()
    series.iloc[idx] = ""
    return series


def inject_bad_email(series: pd.Series, rate: float) -> pd.Series:
    """把 series 中 rate 比例的邮箱改成非法格式。"""
    n = len(series)
    idx = random.sample(range(n), k=int(n * rate))
    series = series.copy()
    bad_samples = ["not-an-email", "missing@", "@no-local.com", "user@@double.com", "spaces in@email.com"]
    for i in idx:
        series.iloc[i] = random.choice(bad_samples)
    return series


def inject_bad_enum(series: pd.Series, rate: float) -> pd.Series:
    """把 series 中 rate 比例的值改成不在白名单的脏值。"""
    n = len(series)
    idx = random.sample(range(n), k=int(n * rate))
    series = series.copy()
    bad = ["unknown", "PENDING", "shipped_again", "退款中", "..."]
    for i in idx:
        series.iloc[i] = random.choice(bad)
    return series


def inject_duplicates(series: pd.Series, count: int) -> pd.Series:
    """把 series 前 count 行的值复制到后面 count 行,造成重复。"""
    series = series.copy()
    n = len(series)
    for i in range(count):
        # 找前 1/3 的行复制到后面
        src = random.randint(0, n // 3)
        dst = n - 1 - i  # 最后几行
        if dst > src:
            series.iloc[dst] = series.iloc[src]
    return series


# ============================================================
# 三个数据集的生成器
# ============================================================
def gen_orders(n: int = 200) -> pd.DataFrame:
    """生成电商订单数据,故意混入各种质量问题。"""
    rows = []
    today = date.today()

    for i in range(1, n + 1):
        order_id = f"ORD{i:05d}"
        customer_id = f"C{random.randint(1, 80):04d}"
        order_date = today - timedelta(days=random.randint(0, 10))  # 0~10 天前
        order_amount = round(random.uniform(50, 5000), 2)
        discount = round(random.uniform(0, min(50, order_amount / 2)), 2)

        # 大部分订单 paid + refund == order_amount,小部分故意破坏(ord_009)
        if random.random() < 0.08:  # 8% 不平
            paid_amount = round(order_amount + random.uniform(10, 100), 2)
            refund_amount = 0.0
        else:
            paid_amount = order_amount
            refund_amount = 0.0

        rows.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_email": f"user{random.randint(1, 80)}@example.com",
            "order_date": order_date.isoformat(),
            "order_status": random.choice(ORDER_STATUSES),
            "order_amount": order_amount,
            "discount": discount,
            "paid_amount": paid_amount,
            "refund_amount": refund_amount,
        })

    df = pd.DataFrame(rows)

    # —— 故意制造质量问题 ——
    # ord_001 / ord_002 not_null: 3% order_id 空、5% customer_id 空
    df["order_id"] = inject_nulls(df["order_id"], 0.03)
    df["customer_id"] = inject_nulls(df["customer_id"], 0.05)

    # ord_003 range: 3% 订单金额超出 [0, 100000] —— 注入负数
    neg_idx = random.sample(range(n), k=int(n * 0.03))
    df.loc[neg_idx, "order_amount"] = [round(random.uniform(-50, -1), 2) for _ in neg_idx]

    # ord_004 / ord_005 主键重复: 复制 5 个 order_id
    df["order_id"] = inject_duplicates(df["order_id"], 5)

    # ord_006 email 格式: 12% 邮箱非法
    df["customer_email"] = inject_bad_email(df["customer_email"], 0.12)

    # ord_007 enum: 8% 状态不在白名单
    df["order_status"] = inject_bad_enum(df["order_status"], 0.08)

    # ord_008 date 类型: 5% 写成 "2024/13/40" 这种坏日期
    bad_date_idx = random.sample(range(n), k=int(n * 0.05))
    df.loc[bad_date_idx, "order_date"] = "2024/13/40"

    # ord_011 跨字段: 4% discount > order_amount
    high_disc_idx = random.sample(range(n), k=int(n * 0.04))
    df.loc[high_disc_idx, "discount"] = df.loc[high_disc_idx, "order_amount"] + 50

    # ord_012 freshness: 6% 订单日期很老(超过 30 天前)
    stale_idx = random.sample(range(n), k=int(n * 0.06))
    for i in stale_idx:
        df.loc[i, "order_date"] = (today - timedelta(days=random.randint(30, 60))).isoformat()

    return df


def gen_customers(n: int = 100) -> pd.DataFrame:
    """生成客户维度表,故意混入质量问题。"""
    rows = []
    for i in range(1, n + 1):
        customer_id = f"C{i:04d}"
        name = f"用户{i:03d}"
        phone = f"1{random.randint(3, 9)}{random.randint(100000000, 999999999)}"
        register_date = (date.today() - timedelta(days=random.randint(0, 365))).isoformat()
        rows.append({
            "customer_id": customer_id,
            "name": name,
            "phone": phone,
            "register_date": register_date,
        })

    df = pd.DataFrame(rows)

    # —— 故意制造质量问题 ——
    # cus_001 not_null: 4% 客户号为空
    df["customer_id"] = inject_nulls(df["customer_id"], 0.04)

    # cus_002 主键重复: 5 个客户号复制
    df["customer_id"] = inject_duplicates(df["customer_id"], 5)

    # cus_003 date 类型: 8% 注册日期写成中文/非日期
    bad_idx = random.sample(range(n), k=int(n * 0.08))
    bad_samples = ["未知", "2024年5月", "N/A", "昨天", "2024-13-40"]
    for i in bad_idx:
        df.loc[i, "register_date"] = random.choice(bad_samples)

    return df


def gen_arrivals(n: int = 120) -> pd.DataFrame:
    """生成人员信息表(对应 人员信息 规则集),高频缺值场景。"""
    channels = ["BOSS直聘", "智联", "猎聘", "内部推荐", "校招", "其他"]
    stages = ["简历筛选", "初试", "复试", "终试", "已发offer", "已入职"]

    rows = []
    for i in range(1, n + 1):
        rows.append({
            "JR工号": f"JR{i:04d}",
            "姓名": f"候选人{i:03d}",
            "入职时间": (date.today() - timedelta(days=random.randint(0, 30))).isoformat(),
            "人员阶段": random.choice(stages),
            "招聘渠道": random.choice(channels),
            "通关交接时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    df = pd.DataFrame(rows)

    # —— 故意制造质量问题(高频缺值)——
    # arr_001 入职时间: 15% 空
    df["入职时间"] = inject_nulls(df["入职时间"], 0.15)

    # arr_002 JR工号: 5% 空(否则 cus_001 也算通过)
    df["JR工号"] = inject_nulls(df["JR工号"], 0.05)

    # arr_003 人员阶段: 10% 空
    df["人员阶段"] = inject_nulls(df["人员阶段"], 0.10)

    # arr_004 招聘渠道: 12% 空
    df["招聘渠道"] = inject_nulls(df["招聘渠道"], 0.12)

    # arr_005 通关交接时间: 18% 空
    df["通关交接时间"] = inject_nulls(df["通关交接时间"], 0.18)

    return df


# ============================================================
# 入口
# ============================================================
GENERATORS = {
    "orders": gen_orders,
    "customers": gen_customers,
    "arrivals": gen_arrivals,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="生成数据质量 demo 数据(包含故意制造的问题)")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="all",
        help="要生成的数据集名: orders / customers / arrivals,默认 all",
    )
    parser.add_argument("--n", type=int, default=None, help="每张表的行数(默认 orders=200 / customers=100 / arrivals=120)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = list(GENERATORS.keys()) if args.dataset == "all" else [args.dataset]
    for name in targets:
        if name not in GENERATORS:
            print(f"[ERROR] 未知数据集: {name},可选: {list(GENERATORS.keys())}")
            continue

        df = GENERATORS[name]()

        # 写 UTF-8 with BOM,Excel 打开中文不乱码
        out_path = OUTPUT_DIR / f"{name}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")

        # 统计一下质量问题数量,打印出来(用 [OK] 替代 ✓,兼容 Windows GBK 终端)
        null_count = (df.astype(str) == "").sum().sum()
        dup_rows = df.duplicated().sum()
        rel = out_path.relative_to(PROJECT_ROOT)
        print(f"[OK] {name}.csv: {len(df)} rows, nulls={null_count}, dup_rows={dup_rows} -> {rel}", flush=True)

    print("\nNext:", flush=True)
    print("  python run.py                # start web UI", flush=True)
    print("  python -m app.cli check orders   # run check via CLI", flush=True)
    print("  pytest -q                   # run tests", flush=True)


if __name__ == "__main__":
    main()