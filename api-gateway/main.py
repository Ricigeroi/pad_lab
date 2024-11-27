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

# Logging setup
logging.basicConfig(
    level=logging.INFO,  # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Limit the list if necessary
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# List of URLs for game-service instances
GAME_SERVICE_INSTANCES = [
    os.getenv("GAME_SERVICE1_URL", "http://game_service1:5001/"),
    os.getenv("GAME_SERVICE2_URL", "http://game_service2:5001/"),
    os.getenv("GAME_SERVICE3_URL", "http://game_service3:5001/")
]

# URL for lobby_service
LOBBY_SERVICE_URL = os.getenv("LOBBY_SERVICE_URL", "http://lobby_service:5002/")

# Iterators for round-robin
game_service_iterator = cycle(GAME_SERVICE_INSTANCES)

# Create Circuit Breakers for each game_service instance
game_service_circuit_breakers = {
    service_url: CircuitBreaker(
        fail_max=3,
        timeout_duration=timedelta(seconds=60),  # Reduced timeout for recovery checks
        name=f'cb_{service_url}'
    )
    for service_url in GAME_SERVICE_INSTANCES
}

# Global Circuit Breaker
global_circuit_breaker = CircuitBreaker(
    fail_max=1,
    timeout_duration=timedelta(seconds=300),  # Adjust the timeout as needed
    name='global_cb'
)

# Indices for round-robin
current_game_index = 0

# Maximum number of reroutes (instances to try)
MAX_REROUTES = 3

# Existing route for game_service
@app.api_route("/game_service/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_game_service(request: Request, path: str):
    global current_game_index
    num_instances = len(GAME_SERVICE_INSTANCES)
    max_instances_to_try = min(num_instances, MAX_REROUTES)
    tried_instances = set()  # Track tried instances

    # Check if the global circuit breaker is open
    if global_circuit_breaker.current_state.name == "open":
        logger.info("Global circuit breaker is open, failing fast.")
        raise HTTPException(status_code=503, detail="Game Service is temporarily unavailable.")

    try:
        # Use the global circuit breaker to wrap the entire request logic
        return await global_circuit_breaker.call_async(
            attempt_to_proxy_request, request, path, max_instances_to_try, num_instances, tried_instances
        )
    except CircuitBreakerError:
        if global_circuit_breaker.current_state.name == "open":
            logger.info("Global circuit breaker is open, failing fast.")
        else:
            logger.info("Global circuit breaker open due to repeated failures.")
        raise HTTPException(status_code=503, detail="Game Service is temporarily unavailable.")


async def attempt_to_proxy_request(request: Request, path: str, max_instances_to_try: int, num_instances: int, tried_instances: set):
    global current_game_index

    while len(tried_instances) < max_instances_to_try:
        # Get the current instance in a round-robin fashion
        service_url = GAME_SERVICE_INSTANCES[current_game_index]
        current_game_index = (current_game_index + 1) % num_instances  # Cyclic index shift

        if service_url in tried_instances:
            continue
        tried_instances.add(service_url)

        circuit_breaker = game_service_circuit_breakers[service_url]  # Circuit Breaker for the current instance

        # Check if the Circuit Breaker is open
        if circuit_breaker.current_state.name == "open":
            logger.info(f"Circuit breaker is open for {service_url}, skipping.")
            continue

        try:
            # Try to make up to 3 requests to the current instance
            response = await attempt_requests_with_retries(
                service_url, path, request, circuit_breaker, max_retries=3
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except CircuitBreakerError:
            logger.info(f"Circuit breaker is now open for {service_url}, skipping.")
        except Exception as exc:
            logger.error(f"Unhandled error for {service_url}: {exc}")

    # If we reach here, all attempts have failed
    logger.error("All attempts to proxy the request have failed.")
    # Manually record a failure in the global circuit breaker
    await global_circuit_breaker._call_failed()
    raise HTTPException(status_code=503, detail="All Game Service instances are unavailable.")

# Helper function for game_service with Circuit Breaker
async def attempt_requests_with_retries(service_url: str, path: str, request: Request, circuit_breaker, max_retries: int) -> httpx.Response:
    """
    Makes up to max_retries attempts to a single instance via Circuit Breaker.
    """
    for attempt in range(1, max_retries + 1):
        # If Circuit Breaker is already open, skip remaining attempts
        if circuit_breaker.current_state.name == "open":
            logger.info(f"Circuit breaker is open for {service_url}, skipping retries.")
            raise CircuitBreakerError

        try:
            logger.info(f"Attempt {attempt} for {service_url}")
            # Attempt to make a request through the Circuit Breaker
            return await circuit_breaker.call_async(async_request_to_service, service_url, path, request)
        except CircuitBreakerError:
            # Circuit Breaker opened during this attempt
            logger.info(f"Circuit breaker is now open for {service_url}, skipping further retries.")
            raise
        except httpx.RequestError as exc:
            logger.error(f"Attempt {attempt} failed for {service_url}: {exc}")
        except Exception as exc:
            logger.error(f"Unhandled exception on attempt {attempt} for {service_url}: {exc}")

        # If the request failed, wait before retrying
        await asyncio.sleep(0.1)

    # If all attempts are exhausted, report an error
    raise HTTPException(status_code=503, detail=f"Service {service_url} failed after {max_retries} attempts.")

# Helper function to perform HTTP requests
async def async_request_to_service(service_url: str, path: str, request: Request) -> httpx.Response:
    """
    Performs a request to the service. Exceptions here are tracked by the Circuit Breaker.
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
            response.raise_for_status()  # Raises exception for 4xx/5xx responses
            return response
        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error from {service_url}: {exc.response.status_code} - {exc.response.text}")
            raise
        except httpx.RequestError as exc:
            logger.error(f"Request error while contacting {service_url}: {exc}")
            raise

# New route to proxy lobby_service (HTTP)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_lobby_service(request: Request, path: str):
    """
    Proxies all requests to lobby_service.
    JWT token and other headers are passed unchanged.
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
                timeout=10.0  # Set appropriate timeout
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

# New route to proxy WebSocket connections with lobby_service
@app.websocket("/ws/lobby/{lobbyId}")
async def websocket_proxy_lobby_service(websocket: WebSocket, lobbyId: str, token: str):
    """
    Proxies WebSocket connections to lobby_service.
    JWT token is passed as a query parameter.
    """
    await websocket.accept()

    # Construct URL for WebSocket connection with lobby_service
    lobby_service_ws_url = f"ws://{LOBBY_SERVICE_URL.replace('http://', '').replace('https://', '')}ws/lobby/{lobbyId}?token={token}"

    try:
        # Establish connection with lobby_service WebSocket
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

            # Run tasks for bidirectional message forwarding
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

