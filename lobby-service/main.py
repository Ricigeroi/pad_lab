# lobby_service/main.py
import asyncio
import json
import logging
import random
import uuid
from typing import List, Dict, Optional, Union

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from jose import JWTError, jwt
from pydantic import BaseModel
from sudoku import Sudoku

# Импорты для работы с базой данных
from databases import Database
import sqlalchemy
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, ForeignKeyConstraint
from sqlalchemy.sql import func
from sqlalchemy.future import select  # Используем future.select для совместимости с SQLAlchemy 1.4+
from datetime import datetime
from contextlib import asynccontextmanager

import redis.asyncio as redis

import board_generator
from board_generator import export_as_list, generate_sudoku_board

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Конфигурация базы данных
DATABASE_URL = "postgresql://postgres:admin@localhost:5432/pad_gameHistory"  # Замените на ваш фактический URL базы данных

database = Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Определение таблиц базы данных
users_table = sqlalchemy.Table(
    'users',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('username', String, unique=True),
    Column('created_at', DateTime, server_default=func.now()),
)

games_table = sqlalchemy.Table(
    'games',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('lobby_id', String, unique=True),
    Column('game_id', String),
    Column('start_time', DateTime),
    Column('end_time', DateTime, nullable=True),
    Column('winner', String, nullable=True),
)

game_players_table = sqlalchemy.Table(
    'game_players',
    metadata,
    Column('game_id', Integer, ForeignKey('games.id')),
    Column('player_id', Integer, ForeignKey('users.id')),
    sqlalchemy.PrimaryKeyConstraint('game_id', 'player_id'),
)

chat_messages_table = sqlalchemy.Table(
    'chat_messages',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('game_id', Integer, nullable=False),
    Column('lobby_id', String, nullable=True),  # Можно удалить, если не нужен
    Column('sender', String),
    Column('message', String),
    Column('timestamp', DateTime, server_default=func.now()),
    ForeignKeyConstraint(['game_id'], ['games.id'], ondelete='CASCADE')
)

# Конфигурация для JWT
SECRET_KEY = "banana"  # Должен совпадать с SECRET_KEY в game-service
ALGORITHM = "HS256"

# Semaphore для ограничения количества одновременных задач
MAX_CONCURRENT_TASKS = 20
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

async def limit_concurrent_tasks():
    async with semaphore:
        yield

# In-memory хранилище для лобби и игр
lobbies: Dict[str, Dict] = {}
games: Dict[str, Dict] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code executed before the application starts
    # Initialize Redis
    app.state.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    logger.info("Redis подключен.")

    # Connect to the database
    await database.connect()
    logger.info("База данных подключена.")

    # For initial setup; in production, use migrations
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)
    logger.info("Таблицы базы данных созданы.")

    yield  # Application is running

    # Code executed after the application shuts down
    await app.state.redis.close()
    logger.info("Redis отключен.")
    await database.disconnect()
    logger.info("База данных отключена.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Замените на ваш клиентский URL в продакшене
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TIMEOUT_SECONDS = 5  # Установите желаемую длительность таймаута

# Модели Pydantic
class LobbyRequest(BaseModel):
    gameId: str

class Player(BaseModel):
    player_id: str
    name: str
    color: str  # Добавлено поле цвета

class Cell(BaseModel):
    value: int
    owner: Optional[str] = None  # Имя пользователя, который заполнил клетку

class LobbyResponse(BaseModel):
    lobbyId: str
    message: str

class LobbyDetailsResponse(BaseModel):
    lobbyId: str
    gameId: str
    players: List[Player]
    board: List[List[Union[int, Cell]]]  # Разрешает int или Cell в каждой клетке
    scores: Dict[str, int]  # Счётчики очков игроков

class MoveRequest(BaseModel):
    type: str  # "move" или "erase" или "chat"
    player: str  # Имя пользователя
    row: Optional[int] = None
    col: Optional[int] = None
    value: Optional[int] = None
    message: Optional[str] = None

class TokenData(BaseModel):
    username: Optional[str] = None

class ChatMessageResponse(BaseModel):
    id: int
    game_id: int
    sender: str
    message: str
    timestamp: datetime

class GameResultResponse(BaseModel):
    id: int
    lobby_id: str
    game_id: str
    start_time: datetime
    end_time: Optional[datetime]
    winner: Optional[str]

# Функции для проверки токена
def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

# Зависимость для получения текущего пользователя
async def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ")[1]
    username = verify_token(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Проверяем, существует ли пользователь в базе данных
    query = select(users_table).where(users_table.c.username == username)
    user = await database.fetch_one(query)
    if user is None:
        # Вставляем нового пользователя
        query = users_table.insert().values(username=username)
        await database.execute(query)
        logger.info(f"Новый пользователь добавлен: {username}")
    return username

# Класс для управления соединениями WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.players: Dict[str, Dict[str, WebSocket]] = {}  # Хранит роли игроков и их имена

    async def connect(self, lobby_id: str, websocket: WebSocket, username: str) -> bool:
        await websocket.accept()
        logger.info(f"Попытка подключения пользователя {username} к лобби {lobby_id}")

        # Проверяем, существует ли лобби
        if lobby_id not in lobbies:
            await websocket.send_text(json.dumps({"type": "error","error": "Lobby not found"}))
            await websocket.close(code=1008)  # Policy Violation
            logger.warning(f"Лобби {lobby_id} не найдено. Соединение отклонено для пользователя {username}.")
            return False

        # Проверяем, не заполнено ли лобби
        if lobby_id not in self.active_connections:
            self.active_connections[lobby_id] = []
            self.players[lobby_id] = {}

        if len(self.active_connections[lobby_id]) >= 2:
            await websocket.send_text(json.dumps({"type": "error", "error": "Lobby is full"}))
            await websocket.close()
            logger.warning(f"Лобби {lobby_id} заполнено. Подключение отклонено пользователем {username}.")
            return False

        self.active_connections[lobby_id].append(websocket)
        # Определяем роль игрока
        player_role = "player1" if len(self.active_connections[lobby_id]) == 1 else "player2"
        self.players[lobby_id][player_role] = websocket

        # Назначаем цвет игроку
        player_color = "red" if player_role == "player1" else "blue"

        # Создаем объект Player и добавляем его в список игроков лобби
        player = Player(
            player_id=str(uuid.uuid4()),
            name=username,  # Используем имя пользователя
            color=player_color
        )
        lobbies[lobby_id]["players"].append(player)
        lobbies[lobby_id]["scores"][username] = 0  # Инициализируем счёт игрока
        logger.info(f"{player.name} подключён к лобби {lobby_id} с цветом {player.color}")

        # Добавляем игрока в игру в базе данных
        # Получаем игру из базы данных
        query = select(games_table).where(games_table.c.lobby_id == lobby_id)
        game = await database.fetch_one(query)
        if game:
            # Получаем user ID
            query = select(users_table).where(users_table.c.username == username)
            user = await database.fetch_one(query)
            if user:
                # Проверяем, есть ли игрок уже в игре
                query = select(game_players_table).where(
                    (game_players_table.c.game_id == game['id']) &
                    (game_players_table.c.player_id == user['id'])
                )
                existing_player = await database.fetch_one(query)
                if existing_player is None:
                    # Вставляем в game_players_table
                    query = game_players_table.insert().values(game_id=game['id'], player_id=user['id'])
                    await database.execute(query)
                    logger.info(f"Пользователь {username} добавлен в игру {game['id']}.")

        # Отправляем сообщение о подключении с реальным именем пользователя и его цветом
        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"{player.name} подключился к лобби.",
            "color": player.color  # Если цвет необходим на фронтенде, иначе можно удалить
        }))


        if len(self.active_connections[lobby_id]) == 2:
            await self.broadcast(lobby_id, json.dumps({
                "type": "system",
                "message": "Оба игрока подключены. Игра начинается!"
            }))

            logger.info(f"Оба игрока подключены к лобби {lobby_id}. Игра начинается!")

        return True

    def disconnect(self, lobby_id: str, websocket: WebSocket):
        if lobby_id in self.active_connections:
            if websocket in self.active_connections[lobby_id]:
                self.active_connections[lobby_id].remove(websocket)
                logger.info(f"WebSocket удалён из лобби {lobby_id}")

                # Определение отключившегося игрока и удаление его из списка игроков
                disconnected_player = None
                for player in lobbies[lobby_id]["players"]:
                    if player.name and websocket in self.active_connections[lobby_id]:
                        disconnected_player = player
                        break
                if disconnected_player:
                    lobbies[lobby_id]["players"].remove(disconnected_player)
                    del lobbies[lobby_id]["scores"][disconnected_player.name]
                    logger.info(f"{disconnected_player.name} отключился от лобби {lobby_id}")

            if not self.active_connections[lobby_id]:
                del self.active_connections[lobby_id]
                del self.players[lobby_id]
                del lobbies[lobby_id]
                logger.info(f"Лобби {lobby_id} пусто и удалено.")

    async def broadcast(self, lobby_id: str, message: str):
        if lobby_id in self.active_connections:
            logger.info(f"Отправка сообщения в лобби {lobby_id}: {message}")
            for connection in self.active_connections[lobby_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения: {e}")

manager = ConnectionManager()

def get_username_from_websocket(lobby_id: str, websocket: WebSocket) -> Optional[str]:
    for player in lobbies[lobby_id]["players"]:
        if player.name and websocket in manager.active_connections[lobby_id]:
            return player.name
    return None

# Маршруты
@app.get("/lobby_service/hello", response_class=JSONResponse)
async def hello_lobby_service(dependency: str = Depends(limit_concurrent_tasks), current_user: str = Depends(get_current_user)):
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
async def get_service2_data(dependency: str = Depends(limit_concurrent_tasks), current_user: str = Depends(get_current_user)):
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

@app.post("/lobbies", response_model=LobbyResponse)
async def create_lobby(request: LobbyRequest, username: str = Depends(get_current_user)):
    """
    Создает новое лобби и генерирует доску Sudoku.
    """
    lobby_id = str(uuid.uuid4())
    board = generate_sudoku_board()
    lobbies[lobby_id] = {
        "gameId": request.gameId,
        "players": [],
        "board": board,
        "scores": {}
    }
    logger.info(f"Создано новое лобби {lobby_id} для игры пользователем {username}")

    # Вставляем новую игру в базу данных и получаем ее ID
    query = games_table.insert().values(
        lobby_id=lobby_id,
        game_id=request.gameId,
        start_time=datetime.utcnow(),
    )
    game_id = await database.execute(query)
    logger.info(f"Игра {game_id} добавлена в базу данных с lobby_id {lobby_id}.")

    # Сохраняем game_id в памяти для использования в WebSocket
    games[request.gameId] = {
        "lobby_id": lobby_id,
        "game_id": game_id  # Сохраняем game_id
    }

    return LobbyResponse(lobbyId=lobby_id, message="Lobby created.")

@app.get("/lobbies/{lobbyId}", response_model=LobbyDetailsResponse)
async def get_lobby_details(lobbyId: str, dependency: str = Depends(limit_concurrent_tasks), username: str = Depends(get_current_user)):
    """
    Получает детали конкретного лобби вместе с текущей доской.
    """
    logger.info(f"Пользователь {username} запрашивает детали лобби {lobbyId}")
    lobby = lobbies.get(lobbyId)
    if not lobby:
        logger.warning(f"Лобби {lobbyId} не найдено пользователем {username}")
        raise HTTPException(status_code=404, detail="Lobby not found")
    return LobbyDetailsResponse(
        lobbyId=lobbyId,
        gameId=lobby["gameId"],
        players=lobby["players"],
        board=update_board(lobby["board"]),  # Преобразуем доску перед отправкой
        scores=lobby["scores"]
    )

@app.get("/lobbies", response_model=List[LobbyDetailsResponse])
async def get_all_lobbies(dependency: str = Depends(limit_concurrent_tasks), username: str = Depends(get_current_user)):
    """
    Получает детали всех открытых лобби.
    """
    all_lobbies = []
    for lobby_id, lobby in lobbies.items():
        all_lobbies.append(
            LobbyDetailsResponse(
                lobbyId=lobby_id,
                gameId=lobby["gameId"],
                players=lobby["players"],
                board=update_board(lobby["board"]),  # Преобразуем доску перед отправкой
                scores=lobby["scores"]
            )
        )
    logger.info(f"Пользователь {username} запросил все лобби.")
    return all_lobbies

# WebSocket Endpoint with Authentication
@app.websocket("/ws/lobby/{lobbyId}")
async def websocket_endpoint(
    websocket: WebSocket,
    lobbyId: str,
    token: str = Query(...),
    dependency: str = Depends(limit_concurrent_tasks),
):
    # Verify the token and get the username
    username = verify_token(token)
    if username is None:
        await websocket.accept()  # Accept the connection to send a message
        await websocket.send_text(json.dumps({"type": "error","error": "Invalid token"}))
        await websocket.close(code=1008)  # Policy Violation
        logger.warning("Попытка подключения с недействительным токеном.")
        return

    logger.info(f"User {username} is connecting to WebSocket lobby {lobbyId}")
    success = await manager.connect(lobbyId, websocket, username)
    if not success:
        logger.info(f"Connection to lobby {lobbyId} failed (lobby is full or not found)")
        return

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from {username} in lobby {lobbyId}: {data}")

            # Process the received message
            try:
                data = json.loads(data)
                redis_client = app.state.redis  # Get the Redis client

                if data.get("type") == "chat":
                    # Handle chat messages
                    query = select(games_table).where(games_table.c.lobby_id == lobbyId)
                    game = await database.fetch_one(query)
                    if game:
                        # Insert chat message into the database
                        query = chat_messages_table.insert().values(
                            game_id=game['id'],
                            sender=data['player'],
                            message=data['message'],
                            timestamp=datetime.utcnow()
                        )
                        await database.execute(query)
                        logger.info(f"Сообщение от {data['player']} в игре {game['id']}: {data['message']}")

                        # Invalidate chat history cache
                        cache_key = f"game:{game['id']}:chat_history"
                        await redis_client.delete(cache_key)
                        logger.debug(f"Кэш истории чата {cache_key} очищен.")

                    # Broadcast the chat message to all participants with separate player and message fields
                    await manager.broadcast(
                        lobbyId,
                        json.dumps({
                            "type": "chat",
                            "player": data['player'],
                            "message": data['message']
                        })
                    )




                elif data.get("type") in ["move", "erase"]:
                    move_request = MoveRequest(**data)
                    current_board = lobbies[lobbyId]["board"]

                    # Проверяем, что row и col присутствуют
                    if move_request.row is None or move_request.col is None:
                        await websocket.send_text(json.dumps({"type": "error","error": "Row and column are required."}))
                        continue

                    if data.get("type") == "move":
                        # Проверяем наличие value для хода
                        if move_request.value is None:
                            await websocket.send_text(json.dumps({"type": "error","error": "Value is required for move."}))
                            continue

                        valid, message = is_valid_move(
                            current_board,
                            move_request.row,
                            move_request.col,
                            move_request.value
                        )
                        if valid:
                            current_board[move_request.row][move_request.col] = {
                                "value": move_request.value,
                                "owner": username
                            }

                            # Увеличиваем счет игрока
                            lobbies[lobbyId]["scores"][username] += 1
                            logger.info(
                                f"Move accepted: {move_request.player} placed {move_request.value} at "
                                f"position ({move_request.row}, {move_request.col})"
                            )

                            game_over, game_message = check_game_over(current_board)
                            if game_over:
                                # Определяем победителя
                                scores = lobbies[lobbyId]["scores"]
                                winner = max(scores, key=scores.get) if scores else None

                                # Обновляем end_time и winner в базе данных
                                query = games_table.update().where(
                                    games_table.c.lobby_id == lobbyId
                                ).values(
                                    end_time=datetime.utcnow(),
                                    winner=winner
                                )
                                await database.execute(query)
                                logger.info(f"Игра в лобби {lobbyId} завершена. Победитель: {winner}")

                                # Invalidate game history cache for all players
                                redis_client = app.state.redis
                                for player in lobbies[lobbyId]["players"]:
                                    player_username = player.name
                                    cache_key = f"user:{player_username}:games"
                                    await redis_client.delete(cache_key)
                                    logger.debug(f"Кэш истории игр {cache_key} очищен.")

                                # Broadcast game over message
                                await manager.broadcast(
                                    lobbyId,
                                    json.dumps({
                                        "type": "game_over",
                                        "message": game_message,
                                        "board": jsonable_encoder(update_board(current_board)),
                                        "scores": lobbies[lobbyId]["scores"],
                                        "winner": winner
                                    })
                                )
                                logger.info(f"Игра в лобби {lobbyId} окончена: {game_message}")
                            else:
                                # Broadcast the move to all participants
                                await manager.broadcast(
                                    lobbyId,
                                    json.dumps({
                                        "type": "move",
                                        "message": f"{move_request.player} сделал ход.",
                                        "board": jsonable_encoder(update_board(current_board)),
                                        "scores": lobbies[lobbyId]["scores"]
                                    })
                                )

                        else:
                            # Send error message to the player who made the invalid move
                            await websocket.send_text(json.dumps({"type": "error","error": message}))

                    elif data.get("type") == "erase":
                        # Обработка стирания клетки
                        cell = current_board[move_request.row][move_request.col]
                        if isinstance(cell, dict) and cell.get("owner") == username:
                            current_board[move_request.row][move_request.col] = 0
                            # Уменьшаем счет игрока
                            lobbies[lobbyId]["scores"][username] -= 1

                            logger.info(
                                f"{move_request.player} стер клетку на позиции ({move_request.row}, {move_request.col})"
                            )

                            # Broadcast the erase action to all participants
                            await manager.broadcast(
                                lobbyId,
                                json.dumps({
                                    "type": "erase",
                                    "message": f"{move_request.player} стер свою клетку.",
                                    "board": jsonable_encoder(update_board(current_board)),
                                    "scores": lobbies[lobbyId]["scores"]
                                })
                            )
                        else:
                            await websocket.send_text(json.dumps({"type": "error","error": "You can only erase your own filled cells."}))
                else:
                    await websocket.send_text(json.dumps({"type": "error","error": "Invalid message type."}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error","error": "Invalid JSON format."}))
            except Exception as e:
                logger.error(f"Error processing message from {username} in lobby {lobbyId}: {e}")
                await websocket.send_text(json.dumps({"type": "error","error": f"Invalid move data: {e}"}))
                continue

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from lobby {lobbyId} by user {username}")
        manager.disconnect(lobbyId, websocket)
        await manager.broadcast(
            lobbyId,
            json.dumps({"type": "system", "message": f"{username} покинул лобби."})
        )
    except Exception as e:
        logger.error(f"Error in WebSocket connection with lobby {lobbyId}: {e}")
        await manager.broadcast(lobbyId, json.dumps({"type": "error", "error": "An error occurred"}))

def check_game_over(board: List[List[Union[int, Dict]]]) -> (bool, str):
    """
    Проверяет, завершена ли игра (доска заполнена корректно).
    """
    for row in range(9):
        for col in range(9):
            cell = board[row][col]
            if cell == 0 or (isinstance(cell, dict) and cell.get("value") == 0):
                return False, ""
    # Дополнительно можно проверить, является ли доска валидной
    # Здесь предполагается, что все ходы были валидны, поэтому доска корректна
    return True, "Игра окончена: пазл Sudoku решен!"


def is_valid_move(board: List[List[Union[int, Dict]]], row: int, col: int, value: int) -> (bool, str):
    """
    Проверяет валидность хода в Sudoku.
    """
    # Проверка диапазона значений
    if not (0 <= row < 9 and 0 <= col < 9 and 1 <= value <= 9):
        return False, "Неверный номер строки, столбца или значение."

    cell = board[row][col]
    if isinstance(cell, dict):
        cell_value = cell.get("value", 0)
    else:
        cell_value = cell

    # Проверка, что клетка пустая
    if cell_value != 0:
        return False, "Клетка уже заполнена."

    # Проверка строки
    for c in range(9):
        current_cell = board[row][c]
        if isinstance(current_cell, dict):
            if current_cell.get("value") == value:
                return False, "Значение уже существует в строке."
        else:
            if current_cell == value:
                return False, "Значение уже существует в строке."

    # Проверка столбца
    for r in range(9):
        current_cell = board[r][col]
        if isinstance(current_cell, dict):
            if current_cell.get("value") == value:
                return False, "Значение уже существует в столбце."
        else:
            if current_cell == value:
                return False, "Значение уже существует в столбце."

    # Проверка 3x3 подблока
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for r in range(start_row, start_row + 3):
        for c in range(start_col, start_col + 3):
            current_cell = board[r][c]
            if isinstance(current_cell, dict):
                if current_cell.get("value") == value:
                    return False, "Значение уже существует в 3x3 блоке."
            else:
                if current_cell == value:
                    return False, "Значение уже существует в 3x3 блоке."

    return True, "Валидный ход."

def update_board(board: List[List[Union[int, Dict]]]) -> List[List[Union[int, dict]]]:
    """
    Преобразует доску для отправки клиенту, заменяя объекты Cell на словари.
    """
    processed_board = []
    for row in board:
        processed_row = []
        for cell in row:
            if isinstance(cell, dict):
                # Если клетка заполнена игроком
                processed_row.append({
                    "value": cell["value"],
                    "owner": cell["owner"]
                })
            else:
                # Предзаполненная клетка или пустая клетка
                processed_row.append(cell)
        processed_board.append(processed_row)
    return processed_board

# Endpoint для получения истории игр пользователя
@app.get("/users/{username}/games", response_model=List[GameResultResponse])
async def get_user_games(username: str, current_user: str = Depends(get_current_user)):
    if username != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to view other user's game history")

    redis_client = app.state.redis
    cache_key = f"user:{username}:games"

    # Try to get data from cache
    cached_data = await redis_client.get(cache_key)
    print(cached_data)
    if cached_data:
        games_list = json.loads(cached_data)
        logger.info(f"Данные игр пользователя {username} получены из кэша.")
        return [GameResultResponse(**game) for game in games_list]

    # Fetch from database
    query = select(users_table).where(users_table.c.username == username)
    user = await database.fetch_one(query)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    query = select(games_table).join(
        game_players_table, games_table.c.id == game_players_table.c.game_id
    ).where(game_players_table.c.player_id == user['id'])
    games_list = await database.fetch_all(query)
    games_data = [GameResultResponse(**dict(game)) for game in games_list]

    # Use jsonable_encoder to handle datetime serialization
    games_data_jsonable = jsonable_encoder(games_data)

    # Store in cache
    await redis_client.set(cache_key, json.dumps(games_data_jsonable), ex=300)
    logger.info(f"Данные игр пользователя {username} сохранены в кэше.")

    return games_data

# Endpoint для получения истории чата конкретной игры
@app.get("/games/{game_id}/chat_history", response_model=List[ChatMessageResponse])
async def get_game_chat_history(game_id: int, current_user: str = Depends(get_current_user)):
    # Проверяем, что пользователь участвовал в этой игре
    query = select(games_table).where(games_table.c.id == game_id)
    game = await database.fetch_one(query)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Получаем user ID
    query = select(users_table).where(users_table.c.username == current_user)
    user = await database.fetch_one(query)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Проверяем, участвует ли пользователь в этой игре
    query = select(game_players_table).where(
        (game_players_table.c.game_id == game['id']) &
        (game_players_table.c.player_id == user['id'])
    )
    participation = await database.fetch_one(query)
    if participation is None:
        raise HTTPException(status_code=403, detail="Not authorized to view this game's chat history")

    redis_client = app.state.redis
    cache_key = f"game:{game_id}:chat_history"

    # Try to get data from cache
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        messages = json.loads(cached_data)
        logger.info(f"История чата игры {game_id} получена из кэша.")
        return [ChatMessageResponse(**message) for message in messages]

    # Fetch from database
    query = select(chat_messages_table).where(chat_messages_table.c.game_id == game_id).order_by(chat_messages_table.c.timestamp)
    messages = await database.fetch_all(query)
    messages_data = [ChatMessageResponse(**dict(message)) for message in messages]

    # Use jsonable_encoder to handle datetime serialization
    messages_data_jsonable = jsonable_encoder(messages_data)

    # Store in cache
    await redis_client.set(cache_key, json.dumps(messages_data_jsonable), ex=300)
    logger.info(f"История чата игры {game_id} сохранена в кэше.")

    return messages_data
