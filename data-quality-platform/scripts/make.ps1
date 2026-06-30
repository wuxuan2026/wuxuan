# 数据质量监测平台 —— PowerShell 快捷命令
# 用法: .\scripts\make.ps1 dev
# 或:   .\scripts\make.ps1 check -Dataset orders

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter()]
    [string]$Dataset = "orders"
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "数据质量监测平台 - PowerShell 快捷命令" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法: .\scripts\make.ps1 <command> [-Dataset <name>]" -ForegroundColor Gray
    Write-Host ""
    Write-Host "命令列表:" -ForegroundColor Yellow
    Write-Host "  help            显示本帮助"
    Write-Host "  install         安装依赖"
    Write-Host "  dev             启动开发服务器(热重载)"
    Write-Host "  demo            生成 demo 数据"
    Write-Host "  test            运行测试"
    Write-Host "  test-cov        运行测试并生成覆盖率报告"
    Write-Host "  rules           列出已注册的规则类型"
    Write-Host "  check           对指定数据集跑一次检测(默认 orders)"
    Write-Host "  clean           清理缓存和生成文件"
    Write-Host "  docker-build    构建 Docker 镜像"
    Write-Host "  docker-up       启动容器"
    Write-Host "  docker-down     停止容器"
    Write-Host "  docker-demo     在容器里生成 demo 数据"
    Write-Host "  docker-logs     查看容器日志"
}

switch ($Command) {
    "help"     { Show-Help }
    "install"  { pip install -r requirements.txt }
    "dev"      { python run.py }
    "demo"     { python scripts/generate_demo_data.py }
    "test"     { python -m pytest -q }
    "test-cov" { python -m pytest --cov=app --cov-report=term-missing }
    "rules"    { python -m app.cli rules }
    "check"    { python -m app.cli check $Dataset }
    "clean" {
        Write-Host "清理 __pycache__ ..." -ForegroundColor Yellow
        Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
        Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
        if (Test-Path .pytest_cache) { Remove-Item -Recurse -Force .pytest_cache }
        Write-Host "✓ 清理完成" -ForegroundColor Green
    }
    "docker-build" { docker build -t data-quality-platform:latest . }
    "docker-up"    { docker compose up --build }
    "docker-down"  { docker compose down }
    "docker-demo"  { docker compose exec web python scripts/generate_demo_data.py }
    "docker-logs"  { docker compose logs -f web }
    default {
        Write-Host "未知命令: $Command" -ForegroundColor Red
        Write-Host "运行 '.\scripts\make.ps1 help' 查看可用命令" -ForegroundColor Gray
        exit 1
    }
}