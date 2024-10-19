import asyncio
import json
import logging
import random
import uuid
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sudoku import Sudoku

# Импорты для работы с базой данных
from databases import Database
import sqlalchemy
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, ForeignKeyConstraint
from sqlalchemy.sql import func
from sqlalchemy.future import select  # Используем future.select для совместимости с SQLAlchemy 1.4+
from datetime import datetime
from contextlib import asynccontextmanager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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
lobbies = {}
games = {}

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
    Column('lobby_id', String),
    Column('game_id', String),
    Column('start_time', DateTime),
    Column('end_time', DateTime, nullable=True),
    Column('winner', String, nullable=True),
    Column('board', JSON),
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

# Создаем приложение FastAPI с использованием lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код при запуске
    await database.connect()
    # Для первоначальной настройки; в продакшене используйте миграции
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)
    yield
    # Код при завершении работы
    await database.disconnect()

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

class LobbyResponse(BaseModel):
    lobbyId: str
    message: str
    board: list

class LobbyDetailsResponse(BaseModel):
    lobbyId: str
    gameId: str
    players: List[Player]
    board: list

class MoveRequest(BaseModel):
    type: str  # "move" или "chat"
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
    board: List[List[int]]

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
    return username

# Класс для управления соединениями WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.players: Dict[str, Dict[str, WebSocket]] = {}  # Хранит роли игроков и их имена

    async def connect(self, lobby_id: str, websocket: WebSocket, username: str):
        await websocket.accept()
        logger.info(f"Попытка подключения пользователя {username} к лобби {lobby_id}")

        if lobby_id not in self.active_connections:
            self.active_connections[lobby_id] = []
            self.players[lobby_id] = {}
            # Инициализируем лобби с пустым списком игроков и доской
            lobbies[lobby_id] = {
                "gameId": "sudoku",  # Можно динамически получать из запроса
                "players": [],
                "board": generate_sudoku_board()
            }
            logger.info(f"Создано новое лобби {lobby_id}")

        if len(self.active_connections[lobby_id]) >= 2:
            await websocket.send_text(json.dumps({"error": "Lobby is full"}))
            await websocket.close()
            logger.warning(f"Лобби {lobby_id} заполнено. Подключение отклонено пользователем {username}.")
            return False

        self.active_connections[lobby_id].append(websocket)
        # Определяем роль игрока (не используется в сообщениях)
        player_role = "player1" if len(self.active_connections[lobby_id]) == 1 else "player2"
        self.players[lobby_id][player_role] = websocket

        # Создаем объект Player и добавляем его в список игроков лобби
        player = Player(
            player_id=str(uuid.uuid4()),
            name=username  # Используем имя пользователя вместо "Player 1"
        )
        lobbies[lobby_id]["players"].append(player)
        logger.info(f"{player.name} подключён к лобби {lobby_id}")

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

        # Отправляем сообщение о подключении с реальным именем пользователя
        await websocket.send_text(json.dumps({"message": f"{player.name} подключился к лобби."}))

        if len(self.active_connections[lobby_id]) == 2:
            await self.broadcast(lobby_id, json.dumps({"message": "Оба игрока подключены. Игра начинается!"}))
            logger.info(f"Оба игрока подключены к лобби {lobby_id}. Игра начинается!")

        return True

    def disconnect(self, lobby_id: str, websocket: WebSocket):
        if lobby_id in self.active_connections:
            if websocket in self.active_connections[lobby_id]:
                self.active_connections[lobby_id].remove(websocket)
                logger.info(f"WebSocket удалён из лобби {lobby_id}")

                # Определение отключившегося игрока и удаление его из списка игроков
                for player in lobbies[lobby_id]["players"]:
                    if player.name == get_username_from_websocket(lobby_id, websocket):
                        lobbies[lobby_id]["players"].remove(player)
                        logger.info(f"{player.name} отключился от лобби {lobby_id}")
                        break

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

def get_username_from_websocket(lobby_id: str, websocket: WebSocket) -> Optional[str]:
    for player in lobbies[lobby_id]["players"]:
        if player.name and websocket in manager.active_connections[lobby_id]:
            return player.name
    return None

manager = ConnectionManager()

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
        "board": board
    }
    logger.info(f"Создано новое лобби {lobby_id} для игры пользователем {username}")

    # Вставляем новую игру в базу данных и получаем ее ID
    query = games_table.insert().values(
        lobby_id=lobby_id,
        game_id=request.gameId,
        start_time=datetime.utcnow(),
        board=board
    )
    game_id = await database.execute(query)

    # Сохраняем game_id в памяти для использования в WebSocket
    games[request.gameId] = {
        "lobby_id": lobby_id,
        "board": board,
        "game_id": game_id  # Сохраняем game_id
    }

    return LobbyResponse(lobbyId=lobby_id, message="Lobby created.", board=board)

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
        board=lobby["board"]
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
                board=lobby["board"]
            )
        )
    return all_lobbies

# WebSocket Endpoint with Authentication
@app.websocket("/ws/lobby/{lobbyId}")
async def websocket_endpoint(websocket: WebSocket, lobbyId: str, token: str = Query(...), dependency: str = Depends(limit_concurrent_tasks)):
    # Проверка токена
    username = verify_token(token)
    if username is None:
        await websocket.send_text(json.dumps({"error": "Invalid token"}))
        await websocket.close(code=1008)  # Policy Violation
        return

    logger.info(f"Пользователь {username} подключается к WebSocket лобби {lobbyId}")
    success = await manager.connect(lobbyId, websocket, username)
    if not success:
        logger.info(f"Подключение к лобби {lobbyId} не удалось (лобби заполнено)")
        return
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Получено сообщение от {username} в лобби {lobbyId}: {data}")
            # Обработка сообщений
            try:
                data = json.loads(data)
                if data.get("type") == "chat":
                    # Получаем game_id из базы данных по lobby_id
                    query = select(games_table).where(games_table.c.lobby_id == lobbyId)
                    game = await database.fetch_one(query)
                    if game:
                        # Вставляем сообщение чата в базу данных с game_id
                        query = chat_messages_table.insert().values(
                            game_id=game['id'],
                            sender=data['player'],
                            message=data['message'],
                            timestamp=datetime.utcnow()
                        )
                        await database.execute(query)
                    # Отправляем сообщение всем участникам лобби
                    await manager.broadcast(lobbyId, json.dumps({"message": f"{data['player']}: {data['message']}"}))
                elif data.get("type") == "move":
                    # Это ход игры, обработайте его
                    move_request = MoveRequest(**data)
                    current_board = lobbies[lobbyId]["board"]
                    valid, message = is_valid_move(current_board, move_request.row, move_request.col, move_request.value)
                    if valid:
                        current_board[move_request.row][move_request.col] = move_request.value

                        # Обновляем доску в базе данных
                        query = games_table.update().where(games_table.c.lobby_id == lobbyId).values(board=current_board)
                        await database.execute(query)

                        logger.info(f"Ход принят: {move_request.player} поставил {move_request.value} на позицию ({move_request.row}, {move_request.col})")
                        game_over, game_message = check_game_over(current_board)
                        if game_over:
                            # Обновляем end_time и winner в базе данных
                            query = games_table.update().where(games_table.c.lobby_id == lobbyId).values(
                                end_time=datetime.utcnow(),
                                winner=move_request.player
                            )
                            await database.execute(query)

                            await manager.broadcast(lobbyId, json.dumps({
                                "message": game_message,
                                "board": current_board
                            }))
                            logger.info(f"Игра в лобби {lobbyId} завершена: {game_message}")
                        else:
                            await manager.broadcast(lobbyId, json.dumps({
                                "message": f"{move_request.player} сделал ход.",
                                "board": current_board
                            }))
                    else:
                        await websocket.send_text(json.dumps({"error": message}))
                else:
                    await websocket.send_text(json.dumps({"error": "Invalid message type."}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format."}))
            except Exception as e:
                await websocket.send_text(json.dumps({"error": f"Invalid move data: {e}"}))
                continue

    except WebSocketDisconnect:
        logger.info(f"WebSocket отключён от лобби {lobbyId} пользователем {username}")
        manager.disconnect(lobbyId, websocket)
        await manager.broadcast(lobbyId, json.dumps({"message": f"{username} покинул лобби."}))
    except Exception as e:
        logger.error(f"Ошибка в WebSocket-соединении с лобби {lobbyId}: {e}")
        await manager.broadcast(lobbyId, json.dumps({"error": "An error occurred"}))

def check_game_over(board):
    """
    Проверяет, завершена ли игра (доска заполнена корректно).
    """
    for row in range(9):
        for col in range(9):
            if board[row][col] == 0:
                return False, ""
    # Дополнительно можно проверить, является ли доска валидной
    # Здесь предполагается, что все ходы были валидны, поэтому доска корректна
    return True, "Game Over: The Sudoku puzzle is completed!"

def generate_sudoku_board(difficulty=0.05):
    """
    Возвращает случайно выбранную предгенерированную доску Sudoku с заданной сложностью.
    """
    puzzle = Sudoku(3).difficulty(difficulty)
    return export_as_list(puzzle)

def is_valid_move(board, row, col, value):
    """
    Проверяет валидность хода в Sudoku.
    """
    # Проверка диапазона значений
    if not (0 <= row < 9 and 0 <= col < 9 and 1 <= value <= 9):
        return False, "Invalid row, column, or value."

    # Проверка, что клетка пустая
    if board[row][col] != 0:
        return False, "Cell is already filled."

    # Проверка строки
    if value in board[row]:
        return False, "Value already exists in the row."

    # Проверка столбца
    for r in range(9):
        if board[r][col] == value:
            return False, "Value already exists in the column."

    # Проверка 3x3 подблока
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for r in range(start_row, start_row + 3):
        for c in range(start_col, start_col + 3):
            if board[r][c] == value:
                return False, "Value already exists in the 3x3 block."

    return True, "Valid move."

def export_as_list(puzzle, flat=False):
    """
    Экспортирует доску Sudoku в виде списка списков.
    """
    board = puzzle.board
    if flat:
        return [cell if cell is not None else 0 for row in board for cell in row]
    return [[cell if cell is not None else 0 for cell in row] for row in board]

# Endpoint для получения истории игр пользователя
@app.get("/users/{username}/games", response_model=List[GameResultResponse])
async def get_user_games(username: str, current_user: str = Depends(get_current_user)):
    if username != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to view other user's game history")
    # Получаем user ID
    query = select(users_table).where(users_table.c.username == username)
    user = await database.fetch_one(query)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Получаем игры, в которых пользователь участвовал
    query = select(games_table).join(
        game_players_table, games_table.c.id == game_players_table.c.game_id
    ).where(game_players_table.c.player_id == user['id'])
    games_list = await database.fetch_all(query)
    return [GameResultResponse(**dict(game)) for game in games_list]

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

    query = select(game_players_table).where(
        (game_players_table.c.game_id == game_id) &
        (game_players_table.c.player_id == user['id'])
    )
    participation = await database.fetch_one(query)
    if participation is None:
        raise HTTPException(status_code=403, detail="Not authorized to view this game's chat history")

    # Получаем историю чата для данной игры
    query = select(chat_messages_table).where(chat_messages_table.c.game_id == game_id).order_by(chat_messages_table.c.timestamp)
    messages = await database.fetch_all(query)
    return [ChatMessageResponse(**dict(message)) for message in messages]
