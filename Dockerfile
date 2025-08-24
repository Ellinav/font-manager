# 使用一个轻量的官方Python镜像作为基础
FROM python:3.11-slim

# 在容器内创建一个工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖 (这样做可以利用Docker的缓存机制，加快构建速度)
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目的所有其他文件
COPY . .

# 声明容器将要监听的端口 (Hugging Face Spaces 默认使用 7860)
EXPOSE 7860

# 容器启动时运行的命令
CMD ["uvicorn", "font_manager_server:app", "--host", "0.0.0.0", "--port", "7860"]