from fastapi import FastAPI
from fastapi.responses import JSONResponse
import random

app = FastAPI()

@app.get("/lobby_service/hello", response_class=JSONResponse)
async def hello_lobby_service():
    """
    Возвращает приветственное сообщение от lobby_service.
    """
    return {"message": "Hello from lobby_service"}


@app.get("/lobby_service/data", response_class=JSONResponse)
async def get_service2_data():
    """
    Возвращает некоторые данные от Service2.
    """
    data = {
        "data": "This is some data from Service2",
        "random": random.randint(0, 100)
    }
    return data