from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/lobby_service/hello", response_class=JSONResponse)
async def hello_lobby_service():
    """
    Возвращает приветственное сообщение от lobby_service.
    """
    return {"message": "Hello from lobby_service"}
