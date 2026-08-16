from fastapi import FastAPI, HTTPException, status
from schemas.partner import PartnerCreateSchema, PartnerResponseSchema
from  handlers.add_partner import BitrixService

app = FastAPI(title="Partner Integration API")

@app.post(
    "/api/v1/partners", 
    response_model=PartnerResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление партнёра и импорт его сотрудников из Битрикс24"
)
async def create_partner(payload: PartnerCreateSchema):
    try:
        # 1. Загружаем сотрудников по полученному вебхуку
        employees = await BitrixService.fetch_partner_employees(str(payload.webhook_url))
        
        # 2. Логика сохранения в вашу БД (PostgreSQL / MongoDB)
        # partner = await db.partners.insert({ "name": payload.name, "webhook_url": str(payload.webhook_url) })
        # await db.employees.insert_many([{**emp, "partner_id": partner.id} for emp in employees])
        
        # Заглушка созданной записи
        partner_db_id = 101

        return PartnerResponseSchema(
            id=partner_db_id,
            name=payload.name,
            webhook_url=str(payload.webhook_url),
            employees_count=len(employees),
            employees=employees
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Ошибка обработки запроса: {str(e)}"
        )