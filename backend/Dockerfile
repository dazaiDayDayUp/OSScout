# 使用官方 Python 3.12 镜像作为基础
FROM python:3.12-slim

# 安装系统级依赖：git（filesystem-mcp 克隆仓库需要）
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .

# 配置 pip 国内镜像源（清华源 + 阿里云双备份，单个失败自动 fallback）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 第一步：先安装轻量依赖（利用缓存层，这部分通常很快）
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
    fastapi uvicorn pydantic pydantic-settings httpx \
    sqlalchemy asyncpg alembic redis \
    python-dotenv structlog pytest pytest-asyncio \
    mcp celery openai chromadb sentence-transformers radon

# 第二步：单独安装 semgrep（包最大，容易卡，单独处理便于重试）
# 如果清华源还是慢，会回退到官方源
RUN pip install --no-cache-dir --timeout 600 --retries 10 semgrep>=1.100.0 \
    || pip install --no-cache-dir --timeout 600 --retries 10 \
       --index-url https://mirrors.aliyun.com/pypi/simple/ \
       semgrep>=1.100.0

# 复制应用代码
COPY . .

# 暴露服务端口
EXPOSE 8000

# 启动命令：热重载模式，适合开发
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
