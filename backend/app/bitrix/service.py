"""Bitrix24 integration service."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class BitrixService:
    """Bitrix24 API client."""

    @staticmethod
    async def fetch_employees(webhook_url: str) -> list[dict[str, Any]]:
        """Fetch all active employees from Bitrix24 via REST API.

        Args:
            webhook_url: Bitrix24 incoming webhook URL with credentials

        Returns:
            List of employee dicts with fields:
            - external_bitrix_id
            - email
            - first_name, last_name, second_name
            - phone
            - position
            - departments (list[int])
            - is_active
        """
        base_url = webhook_url.rstrip("/") + "/"
        endpoint = f"{base_url}user.get.json"

        all_employees = []
        start = 0

        headers = {
            "User-Agent": "Naggetsi-CorporateBenefits/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params = {"FILTER[ACTIVE]": "true", "start": start}

                try:
                    response = await client.get(endpoint, params=params, headers=headers)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.error("bitrix_fetch_failed", url=endpoint, error=str(exc))
                    raise ValueError(f"Failed to connect to Bitrix24: {exc}")

                data = response.json()

                if "error" in data:
                    error_msg = data.get("error_description", data["error"])
                    logger.error("bitrix_api_error", error=error_msg)
                    raise ValueError(f"Bitrix24 API error: {error_msg}")

                users = data.get("result", [])

                for u in users:
                    phone = u.get("WORK_PHONE") or u.get("PERSONAL_MOBILE") or u.get("PERSONAL_PHONE")

                    all_employees.append(
                        {
                            "external_bitrix_id": int(u.get("ID")),
                            "email": u.get("EMAIL"),
                            "first_name": u.get("NAME"),
                            "last_name": u.get("LAST_NAME"),
                            "second_name": u.get("SECOND_NAME"),
                            "phone": phone,
                            "position": u.get("WORK_POSITION"),
                            "departments": [int(d) for d in u.get("UF_DEPARTMENT", [])],
                            "is_active": u.get("ACTIVE") == "true",
                        }
                    )

                if "next" in data:
                    start = data["next"]
                else:
                    break

        logger.info("bitrix_fetch_success", count=len(all_employees), webhook=webhook_url[:50])
        return all_employees
