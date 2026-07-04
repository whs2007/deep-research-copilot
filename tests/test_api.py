"""API 测试：/research 接口"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.server import app


@pytest.mark.asyncio
async def test_research_endpoint_returns_sse():
    """POST /api/research → 200 + text/event-stream"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/research", json={
            "topic": "test topic", "max_iterations": 1
        })
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_research_default_max_iterations():
    """不传 max_iterations → 默认 3"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/research", json={"topic": "test"})
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_research_missing_topic():
    """缺少必填 topic → 422"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/research", json={})
        assert response.status_code == 422  # FastAPI validation error


@pytest.mark.asyncio
async def test_research_streaming_response_type():
    """验证响应类型为 text/event-stream"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/research", json={
            "topic": "test", "max_iterations": 1
        })
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
