# lobby_service.py
import random
import asyncio
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import logging
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Замените на ваш клиентский URL в продакшене
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
TIMEOUT_SECONDS = 5  # Установите желаемую длительность таймаута

# Конфигурация для JWT
SECRET_KEY = "banana1"  # Должен совпадать с SECRET_KEY в game-service
ALGORITHM = "HS256"

# In-memory storage for lobbies
lobbies = {}
games = {}

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
async def hello_lobby_service(current_user: str = Depends(get_current_user)):
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
async def get_service2_data(current_user: str = Depends(get_current_user)):
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
    Creates a new lobby and generates a Sudoku board.
    """
    lobby_id = str(uuid.uuid4())
    board = generate_sudoku_board()
    lobbies[lobby_id] = {
        "gameId": request.gameId,
        "players": [],
        "board": board
    }
    games[request.gameId] = {
        "lobby_id": lobby_id,
        "board": board
    }
    logger.info(f"Создано новое лобби {lobby_id} для игры пользователем {username}")
    return LobbyResponse(lobbyId=lobby_id, message="Lobby created.", board=board)

@app.get("/lobbies/{lobbyId}", response_model=LobbyDetailsResponse)
async def get_lobby_details(lobbyId: str, username: str = Depends(get_current_user)):
    """
    Fetches the details of a specific lobby along with the current board.
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
async def get_all_lobbies(username: str = Depends(get_current_user)):
    """
    Fetches the details of all open lobbies.
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
async def websocket_endpoint(websocket: WebSocket, lobbyId: str, token: str = Query(...)):
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
                    # Это сообщение чата, отправьте его всем игрокам
                    await manager.broadcast(lobbyId, json.dumps({"message": f"{data['player']}: {data['message']}"}))
                elif data.get("type") == "move":
                    # Это ход игры, обработайте его
                    move_request = MoveRequest(**data)
                    current_board = lobbies[lobbyId]["board"]
                    valid, message = is_valid_move(current_board, move_request.row, move_request.col, move_request.value)
                    if valid:
                        current_board[move_request.row][move_request.col] = move_request.value
                        logger.info(f"Ход принят: {move_request.player} поставил {move_request.value} на позицию ({move_request.row}, {move_request.col})")
                        game_over, game_message = check_game_over(current_board)
                        if game_over:
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

# Pre-generated Sudoku boards
sudoku_boards = [
    [
        [8, 0, 0, 0, 0, 0, 7, 6, 0],
        [0, 4, 1, 0, 9, 6, 2, 0, 8],
        [7, 0, 0, 0, 0, 0, 0, 0, 0],
        [9, 0, 4, 1, 0, 2, 8, 3, 6],
        [5, 1, 8, 0, 0, 4, 7, 0, 2],
        [0, 6, 3, 0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 8, 7, 5, 0, 1],
        [1, 0, 9, 0, 2, 3, 6, 8, 7],
        [0, 8, 0, 6, 1, 0, 0, 2, 0]
    ],
    # Добавьте дополнительные доски Sudoku здесь, если необходимо
]

def generate_sudoku_board():
    """
    Возвращает случайно выбранную предгенерированную доску Sudoku из списка.
    """
    return random.choice(sudoku_boards)

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
