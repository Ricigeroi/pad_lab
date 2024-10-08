from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

app = FastAPI()

SERVICE2_URL = "http://localhost:5002/lobby_service/data"

@app.get("/game_service/hello", response_class=JSONResponse)
async def hello_game_service():
    """
    Возвращает приветственное сообщение от game_service.
    """
    return {"message": "Hello from game_service"}

@app.get("/game_service/combined", response_class=JSONResponse)
async def get_combined_data():
    """
    Получает данные от Service2 и возвращает комбинированный ответ.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(SERVICE2_URL)
            response.raise_for_status()  # Возбуждает исключение для HTTP-ошибок
            service2_data = response.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Service2 недоступен: {exc}")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"Ошибка от Service2: {exc}")

    combined_response = {
        "service1_message": "Hello from Service1",
        "service2_data": service2_data
    }
    return combined_response