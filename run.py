"""
一键启动：Docker 依赖检查 → MySQL/Redis/RabbitMQ → FastAPI 服务
用法: python run.py [--port 8002]
"""
import subprocess, sys, time, os
from pathlib import Path

ROOT = Path(__file__).parent
PORT = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8002
CONTAINERS = {
    "deep-research-copilot-mysql-1":  ("mysql:8.0", {"MYSQL_ROOT_PASSWORD": "root"}, 3306, 3309, True),
    "deep-research-copilot-redis-1":  ("redis:7-alpine", {}, 6379, 6379, False),
    "deep-research-copilot-rabbitmq-1": ("rabbitmq:3-management-alpine", {}, 5672, 5672, False),
}

def run(cmd, check=True):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)

def container_running(name):
    r = run(f"docker inspect -f '{{{{.State.Running}}}}' {name}", check=False)
    return r.stdout.strip() == "true"

def ensure_container(name, image, env, internal_port, host_port, need_health):
    if container_running(name):
        print(f"  ✅ {name} 已在运行")
        return True

    # 检查容器是否存在但未运行
    r = run(f"docker ps -a --filter name={name} --format '{{{{.Status}}}}'", check=False)
    if r.stdout.strip():
        print(f"  🔄 {name} 已存在，启动中...")
        run(f"docker start {name}")
    else:
        print(f"  🚀 {name} 创建中...")
        env_args = " ".join(f"-e {k}={v}" for k, v in env.items())
        health = "--health-cmd='mysqladmin ping -h localhost' --health-interval=10s --health-timeout=5s --health-retries=5" if need_health else ""
        run(f"docker run -d --name {name} {env_args} -p {host_port}:{internal_port} {health} {image}")

    # 等待就绪
    for i in range(30):
        time.sleep(2)
        if container_running(name):
            if not need_health or run(f"docker inspect -f '{{{{.State.Health.Status}}}}' {name}", check=False).stdout.strip() == "healthy":
                print(f"  ✅ {name} 就绪 (端口 {host_port})")
                return True
    print(f"  ❌ {name} 启动超时")
    return False

if __name__ == "__main__":
    print("=" * 50)
    print("深度研报 · 一键启动")
    print(f"端口: {PORT}  |  MySQL:3309  |  Redis:6379  |  RabbitMQ:5672")
    print("=" * 50)

    # 检查 Docker
    r = run("docker ps", check=False)
    if r.returncode != 0:
        print("❌ Docker 未运行，请先启动 Docker Desktop")
        sys.exit(1)

    # 启动依赖
    print("\n📦 检查基础设施...")
    all_ok = all(
        ensure_container(name, img, env, iport, hport, health)
        for name, (img, env, iport, hport, health) in CONTAINERS.items()
    )
    if not all_ok:
        print("⚠️  部分基础设施启动失败，服务器将以降级模式运行")

    # 如果 MySQL 刚启动，建表
    time.sleep(2)
    try:
        from app.db.connection import init_db
        init_db()
        print("  ✅ MySQL 表已就绪")
    except Exception as e:
        print(f"  ⚠️  MySQL 建表跳过: {e}")

    # 启动 FastAPI
    print(f"\n🚀 启动 API 服务 (端口 {PORT})...")
    os.chdir(ROOT)
    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=PORT, reload=False, log_level="info")
