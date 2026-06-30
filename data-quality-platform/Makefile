# 数据质量监测平台 —— 快捷命令
# 用法: make help
# Linux / macOS / WSL 适用
# Windows 原生请用 scripts\make.ps1 或 scripts\make.bat

PY      := python
PIP     := pip
APP     := run.py
TESTS   := tests

.DEFAULT_GOAL := help

.PHONY: help
help: ## 显示所有可用命令
	@echo "数据质量监测平台 - 快捷命令"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "提示: Windows 原生请用 scripts\\make.ps1 或 scripts\\make.bat"

.PHONY: install
install: ## 安装依赖
	$(PIP) install -r requirements.txt

.PHONY: dev
dev: ## 启动开发服务器(热重载)
	$(PY) $(APP)

.PHONY: demo
demo: ## 生成 demo 数据(包含质量问题,方便看非 100 分)
	$(PY) scripts/generate_demo_data.py

.PHONY: test
test: ## 运行测试
	$(PY) -m pytest -q

.PHONY: test-cov
test-cov: ## 运行测试并生成覆盖率报告
	$(PY) -m pytest --cov=app --cov-report=term-missing

.PHONY: rules
rules: ## 列出已注册的规则类型
	$(PY) -m app.cli rules

.PHONY: check
check: ## 对指定数据集跑一次检测(用法: make check DATASET=orders)
	$(PY) -m app.cli check $(DATASET)

.PHONY: clean
clean: ## 清理缓存和生成文件
	@echo "清理 __pycache__ ..."
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf .pytest_cache
	@echo "✓ 清理完成"

.PHONY: docker-build
docker-build: ## 构建 Docker 镜像
	docker build -t data-quality-platform:latest .

.PHONY: docker-up
docker-up: ## 启动容器(docker compose up)
	docker compose up --build

.PHONY: docker-down
docker-down: ## 停止容器
	docker compose down

.PHONY: docker-demo
docker-demo: ## 在容器里生成 demo 数据
	docker compose exec web python scripts/generate_demo_data.py

.PHONY: docker-logs
docker-logs: ## 查看容器日志
	docker compose logs -f web