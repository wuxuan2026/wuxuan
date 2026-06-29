# 数据质量监测平台

> 学习 / Demo 项目：对 CSV / Excel 数据做 **完整性、规范性、一致性、时效性** 四维度质量检测，输出 0-100 分报告与历史趋势。

## ✨ 特性

- 📊 **四维度质量检测**：完整性 / 规范性 / 一致性 / 时效性
- 🧩 **配置驱动的规则引擎**：规则实例用 YAML 声明，规则类型用 Python 类实现，工业界主流做法（参考 Great Expectations / Soda）
- 🎯 **0-100 评分模型**：按维度权重 + 严重等级加权汇总
- 🌐 **Web 界面**：FastAPI + Jinja2，无需构建步骤
- 💾 **历史持久化**：SQLite 存每次检测，支持趋势查看
- 🛠️ **Web 上传 / 规则在线编辑**：所见即所得的演示体验

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 生成 demo 数据（含质量问题，方便看到非 100 分）
python scripts/generate_demo_data.py

# 3. 启动服务
python run.py
# → 打开 http://127.0.0.1:8000
```

## 🧪 运行测试

```bash
pytest -q
```

## 🗂️ 目录结构

```
data-quality-platform/
├── app/
│   ├── loaders/          # CSV / Excel 数据加载
│   ├── engine/           # 规则引擎（base / registry / runner / loader_yaml）
│   ├── detectors/        # 4 维度的具体规则实现
│   ├── scoring.py        # 0-100 评分模型
│   ├── reporting.py      # 报告汇总
│   ├── services/         # check_service / history_service
│   ├── routers/          # FastAPI 路由
│   ├── templates/        # Jinja2 模板
│   ├── database.py       # SQLAlchemy + SQLite
│   ├── main.py           # FastAPI 入口
│   └── cli.py            # 命令行入口：python -m app.cli check orders
├── data/
│   ├── generated/        # demo CSV
│   ├── rulesets/         # YAML 规则集
│   ├── uploads/          # 用户上传（gitignore）
│   └── quality.db        # SQLite 历史（gitignore）
├── scripts/generate_demo_data.py
├── tests/                # pytest 单测
└── run.py                # 启动入口
```

## 🧠 规则引擎设计

| 层 | 文件 | 角色 |
|---|---|---|
| **配置** | `data/rulesets/*.yaml` | 用户面：声明规则实例（id / type / column / params） |
| **类型** | `app/detectors/*.py` | 开发者面：每个 `@register("xxx")` 是一个规则类 |
| **引擎** | `app/engine/` | `Rule` 抽象基类、`REGISTRY`、`RuleRunner`、`load_ruleset` |

**新增规则类型只需 3 步**：

1. 在 `app/detectors/` 写一个继承 `Rule` 的类，实现 `evaluate(ctx) -> RuleResult`
2. 加 `@register("xxx")` 装饰器
3. 在 YAML 中用 `type: xxx` 引用

## 📝 已注册规则类型

| 类型 | 维度 | 说明 |
|---|---|---|
| `not_null` | completeness | 列非空 |
| `no_duplicates` | completeness | 列组合无重复 |
| `range` | completeness | 数值/日期值域（min/max） |
| `type` | conformity | 类型检查（int/float/date/datetime/str） |
| `regex` | conformity | 正则匹配 |
| `enum` | conformity | 枚举值白名单 |
| `cross_field` | consistency | 跨字段表达式（pandas eval） |
| `primary_key` | consistency | 主键唯一非空 |
| `foreign_key` | consistency | 外键引用（需在 ctx.tables 加载关联表） |
| `freshness` | timeliness | 最新一条不超过 max_age_days |
| `arrival` | timeliness | 数据按时到达（容忍 N 分钟延迟） |

## 🎯 评分模型

```
单规则通过率 = 1 - failure_rate
维度分       = 该维度下规则 pass_rate 按 severity 加权平均（blocker=3 / major=2 / minor=1）
总分         = 4 维度加权：completeness 0.35 / consistency 0.25 / conformity 0.25 / timeliness 0.15
```

分级：**≥90 优秀 / 75-89 良好 / 60-74 合格 / <60 不合格**

## 🌐 Web 页面

| 路径 | 功能 |
|---|---|
| `/` | 首页：数据集列表 + 最近检测 |
| `/upload` | 上传 CSV/Excel 或加载 demo 数据并检测 |
| `/rulesets` | 浏览/编辑 YAML 规则集 |
| `/rulesets/{name}/edit` | 编辑规则集（保存时校验 YAML） |
| `/report/{run_id}` | 单次检测报告（总分 + 维度分 + 规则明细） |
| `/report/{run_id}/rule/{rule_id}` | 单条规则的失败样本详情 |
| `/history` | 历史列表 + 总分趋势图（纯 SVG） |

## 🧪 命令行

```bash
# 查看已注册规则类型
python -m app.cli rules

# 对 orders 数据集跑一次检测，输出 JSON 报告
python -m app.cli check orders
```

## ⚙️ 配置（`.env`）

```ini
DATA_DIR=data
UPLOAD_DIR=data/uploads
GENERATED_DIR=data/generated
RULESET_DIR=data/rulesets
SAMPLE_LIMIT=50
```

## 📌 已知边界 / TODO

- 规则编辑保存时只做 YAML 语法校验，不校验字段合法性（提交后下次检测可能失败）
- 历史趋势图只画总分，未画维度分（后续可加）
- 上传文件目前只用文件主名匹配规则集，不支持用户输入规则集 id

## 📄 License

仅供学习演示使用。