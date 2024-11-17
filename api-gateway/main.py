import os
import httpx
from itertools import cycle
from fastapi import FastAPI, HTTPException, Response, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiobreaker import CircuitBreaker, CircuitBreakerError
from datetime import timedelta
import asyncio
import json
import logging
import websockets

app = FastAPI()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ограничьте список при необходимости
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Список URL-адресов для инстанций game-service
GAME_SERVICE_INSTANCES = [
    os.getenv("GAME_SERVICE1_URL", "http://game_service1:5001/"),
    os.getenv("GAME_SERVICE2_URL", "http://game_service2:5001/"),
    os.getenv("GAME_SERVICE3_URL", "http://game_service3:5001/")
]

# URL для lobby_service
LOBBY_SERVICE_URL = os.getenv("LOBBY_SERVICE_URL", "http://lobby_service:5002/")

# Итераторы для round-robin
game_service_iterator = cycle(GAME_SERVICE_INSTANCES)

# Создаем Circuit Breakers для каждого инстанса game_service
game_service_circuit_breakers = {
    service_url: CircuitBreaker(
        fail_max=3,
        timeout_duration=timedelta(seconds=10),  # Пониженный таймаут для проверки восстановления
        name=f'cb_{service_url}'
    )
    for service_url in GAME_SERVICE_INSTANCES
}

# Индексы для round-robin
current_game_index = 0

# Существующий маршрут для game_service
@app.api_route("/game_service/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_game_service(request: Request, path: str):
    global current_game_index
    num_instances = len(GAME_SERVICE_INSTANCES)
    tried_instances = set()  # Отслеживаем проверенные инстансы

    while len(tried_instances) < num_instances:
        # Получаем текущий инстанс по round-robin
        service_url = GAME_SERVICE_INSTANCES[current_game_index]
        current_game_index = (current_game_index + 1) % num_instances  # Сдвиг индекса циклически

        if service_url in tried_instances:
            continue
        tried_instances.add(service_url)

        circuit_breaker = game_service_circuit_breakers[service_url]  # Circuit Breaker для текущего инстанса

        # Проверяем, открыт ли Circuit Breaker
        if circuit_breaker.current_state == "open":
            logger.info(f"Circuit breaker is open for {service_url}, skipping.")
            continue

        try:
            # Пробуем сделать до 3 запросов к текущему инстансу
            response = await attempt_requests_with_retries(
                service_url, path, request, circuit_breaker, max_retries=3
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except CircuitBreakerError:
            logger.info(f"Circuit breaker open for {service_url}, skipping.")
        except Exception as exc:
            logger.error(f"Unhandled error for {service_url}: {exc}")

    raise HTTPException(status_code=503, detail="All Game Service instances are unavailable.")

# Вспомогательная функция для game_service с использованием Circuit Breaker
async def attempt_requests_with_retries(service_url: str, path: str, request: Request, circuit_breaker, max_retries: int) -> httpx.Response:
    """
    Делает до max_retries попыток запроса к одному инстансу через Circuit Breaker.
    """
    for attempt in range(1, max_retries + 1):
        # Если Circuit Breaker уже открыт, пропускаем оставшиеся попытки
        if circuit_breaker.current_state == "open":
            logger.info(f"Circuit breaker is open for {service_url}, skipping retries.")
            raise CircuitBreakerError

        try:
            logger.info(f"Attempt {attempt} for {service_url}")
            # Попытка выполнить запрос через Circuit Breaker
            return await circuit_breaker.call_async(async_request_to_service, service_url, path, request)
        except CircuitBreakerError:
            # Circuit Breaker открылся во время этой попытки
            logger.info(f"Circuit breaker is now open for {service_url}, skipping further retries.")
            raise
        except httpx.RequestError as exc:
            logger.error(f"Attempt {attempt} failed for {service_url}: {exc}")
        except Exception as exc:
            logger.error(f"Unhandled exception on attempt {attempt} for {service_url}: {exc}")

        # Если запрос не удался, ждем перед повторной попыткой
        await asyncio.sleep(1)

    # Если все попытки исчерпаны, сообщаем об ошибке
    raise HTTPException(status_code=503, detail=f"Service {service_url} failed after {max_retries} attempts.")

# Вспомогательная функция для выполнения HTTP-запросов
async def async_request_to_service(service_url: str, path: str, request: Request) -> httpx.Response:
    """
    Выполняет запрос к сервису. Исключение здесь фиксируется Circuit Breaker'ом.
    """
    method = request.method
    headers = dict(request.headers)
    body = await request.body()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=method,
                url=f"{service_url}{path}",
                headers=headers,
                content=body,
                timeout=10.0
            )
            response.raise_for_status()  # Вызывает исключение для 4xx/5xx ответов
            return response
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error from {service_url}: {exc.response.status_code} - {exc.response.text}")
            raise
        except httpx.RequestError as exc:
            logger.error(f"Request error while contacting {service_url}: {exc}")
            raise

# Новый маршрут для проксирования lobby_service (HTTP)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_lobby_service(request: Request, path: str):
    """
    Проксирует все запросы к lobby_service.
    JWT токен и другие заголовки передаются без изменений.
    """
    lobby_service_url = LOBBY_SERVICE_URL
    url = f"{lobby_service_url}{path}"

    method = request.method
    headers = dict(request.headers)
    body = await request.body()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
                timeout=10.0  # Установите подходящий таймаут
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except httpx.RequestError as exc:
            logger.error(f"Request error while contacting lobby_service: {exc}")
            raise HTTPException(status_code=503, detail="Lobby Service is unavailable.")
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error from lobby_service: {exc.response.status_code} - {exc.response.text}")
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)

# Новый маршрут для проксирования WebSocket соединений с lobby_service
@app.websocket("/ws/lobby/{lobbyId}")
async def websocket_proxy_lobby_service(websocket: WebSocket, lobbyId: str, token: str):
    """
    Проксирует WebSocket соединения к lobby_service.
    JWT токен передается как параметр запроса.
    """
    await websocket.accept()

    # Построение URL для WebSocket соединения с lobby_service
    lobby_service_ws_url = f"ws://{LOBBY_SERVICE_URL.replace('http://', '').replace('https://', '')}ws/lobby/{lobbyId}?token={token}"

    try:
        # Устанавливаем соединение с lobby_service WebSocket
        async with websockets.connect(lobby_service_ws_url) as service_ws:
            logger.info(f"Connected to lobby_service WebSocket at {lobby_service_ws_url}")

            async def forward_client_to_service():
                try:
                    while True:
                        message = await websocket.receive_text()
                        await service_ws.send(message)
                except WebSocketDisconnect:
                    await service_ws.close()
                except Exception as e:
                    logger.error(f"Error forwarding client to service: {e}")
                    await service_ws.close()

            async def forward_service_to_client():
                try:
                    async for message in service_ws:
                        await websocket.send_text(message)
                except websockets.exceptions.ConnectionClosed:
                    await websocket.close()
                except Exception as e:
                    logger.error(f"Error forwarding service to client: {e}")
                    await websocket.close()

            # Запускаем задачи для двунаправленного пересылки сообщений
            client_to_service = asyncio.create_task(forward_client_to_service())
            service_to_client = asyncio.create_task(forward_service_to_client())

            done, pending = await asyncio.wait(
                [client_to_service, service_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

    except Exception as e:
        logger.error(f"Failed to connect to lobby_service WebSocket: {e}")
        await websocket.close()

# Для WebSocket проксирования необходимо установить библиотеку `websockets`
# Добавьте её в requirements.txt или установите через pip:
# pip install websockets

