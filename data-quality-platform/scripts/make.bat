@echo off
REM 数据质量监测平台 —— CMD 快捷命令
REM 用法: scripts\make.bat dev
REM 或:   scripts\make.bat check orders

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="install" goto install
if "%1"=="dev" goto dev
if "%1"=="demo" goto demo
if "%1"=="test" goto test
if "%1"=="test-cov" goto testcov
if "%1"=="rules" goto rules
if "%1"=="check" goto check
if "%1"=="clean" goto clean
if "%1"=="docker-build" goto dockerbuild
if "%1"=="docker-up" goto dockerup
if "%1"=="docker-down" goto dockerdown
if "%1"=="docker-demo" goto dockerdemo
if "%1"=="docker-logs" goto dockerlogs

echo [ERROR] 未知命令: %1
echo 运行 'scripts\make.bat help' 查看可用命令
exit /b 1

:help
echo 数据质量监测平台 - CMD 快捷命令
echo.
echo 用法: scripts\make.bat ^<command^> [args]
echo.
echo 命令列表:
echo   help            显示本帮助
echo   install         安装依赖
echo   dev             启动开发服务器(热重载)
echo   demo            生成 demo 数据
echo   test            运行测试
echo   test-cov        运行测试并生成覆盖率报告
echo   rules           列出已注册的规则类型
echo   check           对指定数据集跑一次检测(默认 orders)
echo   clean           清理缓存和生成文件
echo   docker-build    构建 Docker 镜像
echo   docker-up       启动容器
echo   docker-down     停止容器
echo   docker-demo     在容器里生成 demo 数据
echo   docker-logs     查看容器日志
goto :eof

:install
pip install -r requirements.txt
goto :eof

:dev
python run.py
goto :eof

:demo
python scripts\generate_demo_data.py
goto :eof

:test
python -m pytest -q
goto :eof

:testcov
python -m pytest --cov=app --cov-report=term-missing
goto :eof

:rules
python -m app.cli rules
goto :eof

:check
if "%2"=="" (
    python -m app.cli check orders
) else (
    python -m app.cli check %2
)
goto :eof

:clean
echo 清理 __pycache__ ...
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul
if exist .pytest_cache rd /s /q .pytest_cache
echo √ 清理完成
goto :eof

:dockerbuild
docker build -t data-quality-platform:latest .
goto :eof

:dockerup
docker compose up --build
goto :eof

:dockerdown
docker compose down
goto :eof

:dockerdemo
docker compose exec web python scripts\generate_demo_data.py
goto :eof

:dockerlogs
docker compose logs -f web
goto :eof