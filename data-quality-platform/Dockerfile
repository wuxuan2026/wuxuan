# 语法: docker build -t data-quality-platform .
# 运行: docker run --rm -p 8000:8000 -v ${PWD}/data:/app/data data-quality-platform
FROM python:3.12-slim

# 容器内工作目录
WORKDIR /app

# 先拷贝依赖清单 —— 利用 Docker 层缓存,requirements 不变就不重新 pip install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷贝源码(后续代码改动只触发这一层重建,比全量重装快得多)
COPY . .

# 暴露 FastAPI 端口
EXPOSE 8000

# 启动命令 —— 0.0.0.0 让容器外部(浏览器)能访问
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]