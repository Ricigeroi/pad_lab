from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/game_service/hello", response_class=JSONResponse)
async def hello_game_service():
    """
    Возвращает приветственное сообщение от game_service.
    """
    return {"message": "Hello from game_service"}
