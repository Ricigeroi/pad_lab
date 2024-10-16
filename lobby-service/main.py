import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

TIMEOUT_SECONDS = 5  # Set your desired timeout duration here

@app.get("/lobby_service/hello", response_class=JSONResponse)
async def hello_lobby_service():
    """
    Возвращает приветственное сообщение от lobby_service.
    """
    try:
        return await asyncio.wait_for(_hello_lobby_service(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Request Timeout")

async def _hello_lobby_service():
    return {"message": "Hello from lobby_service"}

@app.get("/lobby_service/data", response_class=JSONResponse)
async def get_service2_data():
    """
    Возвращает некоторые данные от Service2.
    """
    try:
        return await asyncio.wait_for(_get_service2_data(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Request Timeout")

async def _get_service2_data():
    data = {
        "data": "This is some data from Service2",
        "random": random.randint(0, 100)
    }
    return data