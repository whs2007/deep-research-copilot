# 多阶段构建：第一阶段安装依赖，第二阶段只复制运行所需
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# 优雅关闭：SIGTERM 触发 uvicorn 的 graceful shutdown
STOPSIGNAL SIGTERM
CMD ["uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
