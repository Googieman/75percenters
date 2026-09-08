import asyncio

import httpx

from srm_tracker.main import create_app


def test_health_endpoint_returns_ok() -> None:
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_has_the_expected_title() -> None:
    assert create_app().title == "SRM Attendance Tracker API"
