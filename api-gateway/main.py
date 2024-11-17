import os 
import httpx
from itertools import cycle
from fastapi import FastAPI, HTTPException, Response, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiobreaker import CircuitBreaker, CircuitBreakerError
from datetime import timedelta
import asyncio

app = FastAPI()

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

# Список URL-адресов для инстанций lobby-service
LOBBY_SERVICE_INSTANCES = [
    os.getenv("LOBBY_SERVICE1_URL", "http://lobby_service1:5002/"),
    os.getenv("LOBBY_SERVICE2_URL", "http://lobby_service2:5002/"),
    os.getenv("LOBBY_SERVICE3_URL", "http://lobby_service3:5002/")
]

# Итераторы для round-robin
game_service_iterator = cycle(GAME_SERVICE_INSTANCES)
lobby_service_iterator = cycle(LOBBY_SERVICE_INSTANCES)

# Создаем Circuit Breakers для каждого инстанса game_service
game_service_circuit_breakers = {
    service_url: CircuitBreaker(
        fail_max=3,
        timeout_duration=timedelta(seconds=10),  # Пониженный таймаут для проверки восстановления
        name=f'cb_{service_url}'
    )
    for service_url in GAME_SERVICE_INSTANCES
}

# Создаем Circuit Breakers для каждого инстанса lobby_service
lobby_service_circuit_breakers = {
    service_url: CircuitBreaker(
        fail_max=3,
        timeout_duration=timedelta(seconds=10),
        name=f'cb_{service_url}'
    )
    for service_url in LOBBY_SERVICE_INSTANCES
}

# Индексы для round-robin
current_game_index = 0
current_lobby_index = 0

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
            print(f"Circuit breaker is open for {service_url}, skipping.")
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
            print(f"Circuit breaker open for {service_url}, skipping.")
        except Exception as exc:
            print(f"Unhandled error for {service_url}: {exc}")

    raise HTTPException(status_code=503, detail="All Game Service instances are unavailable.")

@app.api_route("/lobby_service/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_lobby_service(request: Request, path: str):
    global current_lobby_index
    num_instances = len(LOBBY_SERVICE_INSTANCES)
    tried_instances = set()  # Отслеживаем проверенные инстансы

    while len(tried_instances) < num_instances:
        # Получаем текущий инстанс по round-robin
        service_url = LOBBY_SERVICE_INSTANCES[current_lobby_index]
        current_lobby_index = (current_lobby_index + 1) % num_instances  # Сдвиг индекса циклически

        if service_url in tried_instances:
            continue
        tried_instances.add(service_url)

        circuit_breaker = lobby_service_circuit_breakers[service_url]  # Circuit Breaker для текущего инстанса

        # Проверяем, открыт ли Circuit Breaker
        if circuit_breaker.current_state == "open":
            print(f"Circuit breaker is open for {service_url}, skipping.")
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
            print(f"Circuit breaker open for {service_url}, skipping.")
        except Exception as exc:
            print(f"Unhandled error for {service_url}: {exc}")

    raise HTTPException(status_code=503, detail="All Lobby Service instances are unavailable.")

async def attempt_requests_with_retries(service_url: str, path: str, request: Request, circuit_breaker, max_retries: int) -> httpx.Response:
    """
    Делает до max_retries попыток запроса к одному инстансу через Circuit Breaker.
    """
    for attempt in range(1, max_retries + 1):
        # Если Circuit Breaker уже открыт, пропускаем оставшиеся попытки
        if circuit_breaker.current_state == "open":
            print(f"Circuit breaker is open for {service_url}, skipping retries.")
            raise CircuitBreakerError

        try:
            print(f"Attempt {attempt} for {service_url}")
            # Попытка выполнить запрос через Circuit Breaker
            return await circuit_breaker.call_async(async_request_to_service, service_url, path, request)
        except CircuitBreakerError:
            # Circuit Breaker открылся во время этой попытки
            print(f"Circuit breaker is now open for {service_url}, skipping further retries.")
            raise
        except httpx.RequestError as exc:
            print(f"Attempt {attempt} failed for {service_url}: {exc}")
        except Exception as exc:
            print(f"Unhandled exception on attempt {attempt} for {service_url}: {exc}")

        # Если запрос не удался, ждем перед повторной попыткой
        await asyncio.sleep(1)

    # Если все попытки исчерпаны, сообщаем об ошибке
    raise HTTPException(status_code=503, detail=f"Service {service_url} failed after {max_retries} attempts.")

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
            print(f"HTTP error from {service_url}: {exc.response.status_code} - {exc.response.text}")
            raise
        except httpx.RequestError as exc:
            print(f"Request error while contacting {service_url}: {exc}")
            raise

# Пример WebSocket проксирования (опционально, если требуется)
# Если вам нужно проксировать WebSocket соединения для lobby_service, добавьте следующий код:

@app.websocket("/ws/lobby/{lobby_id}")
async def proxy_websocket_to_lobby_service(websocket: WebSocket, lobby_id: str):
    """
    Прокси WebSocket соединений для lobby_service.
    """
    # Выберите инстанс lobby_service (например, по round-robin или другому алгоритму)
    service_url = next(lobby_service_iterator)
    ws_url = f"{service_url}/ws/lobby/{lobby_id}?token={websocket.query_params.get('token')}"

    async with httpx.AsyncClient() as client:
        try:
            # Установить соединение с целевым WebSocket сервисом
            async with client.stream("GET", ws_url) as ws_response:
                if ws_response.status_code != 101:
                    await websocket.close(code=1002)
                    raise HTTPException(
                        status_code=ws_response.status_code,
                        detail="Failed to connect to Lobby WebSocket service"
                    )

                # Двунаправленное перенаправление сообщений
                async def receive_from_client():
                    try:
                        while True:
                            message = await websocket.receive_text()
                            await ws_response.send_text(message)
                    except WebSocketDisconnect:
                        await ws_response.aclose()
                    except Exception as e:
                        await ws_response.aclose()

                async def receive_from_service():
                    try:
                        async for message in ws_response.aiter_text():
                            await websocket.send_text(message)
                    except WebSocketDisconnect:
                        await websocket.close()
                    except Exception as e:
                        await websocket.close()

                await asyncio.gather(receive_from_client(), receive_from_service())

        except Exception as exc:
            print(f"Error proxying WebSocket to {service_url}: {exc}")
            await websocket.close(code=1011)