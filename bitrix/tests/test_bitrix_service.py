from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ИМПОРТЫ: Замените путь ниже на фактический модуль, где объявлен BitrixService
# Например: from bitrix.services import BitrixService
# Или если класс лежит в handlers/get_employees.py:
# from bitrix.handlers.get_employees import BitrixService

try:
    from bitrix.services import BitrixService
except ImportError:
    # Пример фоллбэка, если класс находится в другом файле
    from bitrix.handlers.get_employees import BitrixService

WEBHOOK_URL = "https://b24-example.bitrix24.ru/rest/1/webhook_key/"


@pytest.mark.asyncio
async def test_get_users_success_with_invited_filter():
    """Проверка успешного получения списка пользователей с фильтром FIRED=N."""
    mock_response_data = {
        "result": [
            {
                "ID": "1",
                "NAME": "Muzaffar",
                "EMAIL": "muzaffar@gmail.com",
                "ACTIVE": True,
            },
            {
                "ID": "2",
                "NAME": "Линус Торвальдс",
                "EMAIL": "linus@gmail.com",
                "ACTIVE": False,
            },
        ]
    }

    # Синхронный MagicMock для HTTP Response (избегает TypeError с корутиной)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        service = BitrixService(WEBHOOK_URL)
        users = await service.get_users(include_invited=True)

        assert len(users) == 2
        assert users[0]["NAME"] == "Muzaffar"
        assert users[1]["EMAIL"] == "linus@gmail.com"

        # Проверяем передачу аргументов в HTTP-клиент
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs.get("params") == {"FILTER[FIRED]": "N"}


@pytest.mark.asyncio
async def test_get_users_bitrix_api_error():
    """Проверка обработки ошибки от Bitrix24 API."""
    mock_error_data = {
        "error": "ACCESS_DENIED",
        "error_description": "Application context required",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_error_data
    mock_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        service = BitrixService(WEBHOOK_URL)

        with pytest.raises(
            ValueError, match="Bitrix24 Error: Application context required"
        ):
            await service.get_users()