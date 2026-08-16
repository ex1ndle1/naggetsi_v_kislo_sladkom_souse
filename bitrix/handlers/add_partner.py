import httpx
from typing import List, Dict, Any, Optional

class BitrixService:
    @staticmethod
    async def fetch_partner_employees(webhook_url: str) -> List[Dict[str, Any]]:
        """
        Автоматически скачивает всех активных сотрудников 
        с Битрикс24 партнёра с учётом пагинации (по 50 записей).
        """
        # Нормализуем URL вебхука
        base_url = webhook_url.rstrip("/") + "/"
        endpoint = f"{base_url}user.get.json"
        
        all_employees = []
        start = 0
        
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                params = {
                    "FILTER[ACTIVE]": "true",
                    "start": start
                }

                response = await client.get(endpoint, params=params, headers=headers)
                
                if response.status_code != 200:
                    raise ValueError(f"Не удалось подключиться к Битрикс24 API. Статус: {response.status_code}")

                data = response.json()
                
                if "error" in data:
                    raise ValueError(f"Ошибка Битрикс24 API: {data.get('error_description', data['error'])}")

                users = data.get("result", [])

                for u in users:
                    phone = (
                        u.get("WORK_PHONE") 
                        or u.get("PERSONAL_MOBILE") 
                        or u.get("PERSONAL_PHONE")
                    )

                    all_employees.append({
                        "external_bitrix_id": int(u.get("ID")),
                        "email": u.get("EMAIL"),
                        "first_name": u.get("NAME"),
                        "last_name": u.get("LAST_NAME"),
                        "second_name": u.get("SECOND_NAME"),
                        "phone": phone,
                        "position": u.get("WORK_POSITION"),
                        "departments": [int(d) for d in u.get("UF_DEPARTMENT", [])],
                        "is_active": u.get("ACTIVE") == "true"
                    })

                # Если есть следующая страница — запрашиваем её
                if "next" in data:
                    start = data["next"]
                else:
                    break

        return all_employees