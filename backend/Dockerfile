# 使用官方 Python 3.12 镜像作为基础（通过国内镜像源拉取）
FROM m.daocloud.io/docker.io/library/python:3.12-slim

# 设置工作目录
WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .

# 配置 pip 国内镜像源，加速依赖安装
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

# 安装依赖（增加超时时间和重试次数，防止网络波动导致失败）
RUN pip install --no-cache-dir --timeout 600 --retries 10 -r requirements.txt

# 复制应用代码
COPY . .

# 暴露服务端口
EXPOSE 8000

# 启动命令：热重载模式，适合开发
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
