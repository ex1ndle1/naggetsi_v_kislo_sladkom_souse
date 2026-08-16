import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

# Импортируйте ваше приложение FastAPI
# from app.main import app 

@pytest.mark.asyncio
async def test_api_get_employees_endpoint(app):
    mock_users = [
        {"ID": "1", "NAME": "Иван", "LAST_NAME": "Тестов", "EMAIL": "test@example.com"}
    ]

    with patch("app.services.bitrix.BitrixService.get_users", new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_users

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/employees")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["EMAIL"] == "test@example.com"