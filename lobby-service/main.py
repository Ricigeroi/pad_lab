import random
import asyncio
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict
import json
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI()

TIMEOUT_SECONDS = 5  # Установите желаемую длительность таймаута

# In-memory storage for lobbies
lobbies = {}
games = {}

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
    player: str  # "player1" или "player2"
    row: int
    col: int
    value: int

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.players: Dict[str, Dict[str, WebSocket]] = {}  # Хранит роли игроков

    async def connect(self, lobby_id: str, websocket: WebSocket):
        await websocket.accept()
        logger.info(f"Попытка подключения к лобби {lobby_id}")

        if lobby_id not in self.active_connections:
            self.active_connections[lobby_id] = []
            self.players[lobby_id] = {}
            logger.info(f"Создано новое лобби {lobby_id}")

        if len(self.active_connections[lobby_id]) >= 2:
            await websocket.send_text(json.dumps({"error": "Lobby is full"}))
            await websocket.close()
            logger.warning(f"Лобби {lobby_id} заполнено. Подключение отклонено.")
            return False

        self.active_connections[lobby_id].append(websocket)
        player_role = "player1" if len(self.active_connections[lobby_id]) == 1 else "player2"
        self.players[lobby_id][player_role] = websocket

        # Создаем объект Player и добавляем его в список игроков лобби
        player = Player(
            player_id=str(uuid.uuid4()),
            name=f"Player {player_role[-1]}"  # "Player 1" или "Player 2"
        )
        lobbies[lobby_id]["players"].append(player)
        logger.info(f"{player.name} подключён к лобби {lobby_id}")

        await websocket.send_text(json.dumps({"message": f"Connected as {player_role}"}))

        if len(self.active_connections[lobby_id]) == 2:
            await self.broadcast(lobby_id, json.dumps({"message": "Both players connected. Game starts!"}))
            logger.info(f"Оба игрока подключены к лобби {lobby_id}. Игра начинается!")

        return True

    def disconnect(self, lobby_id: str, websocket: WebSocket):
        if lobby_id in self.active_connections:
            self.active_connections[lobby_id].remove(websocket)
            logger.info(f"WebSocket удалён из лобби {lobby_id}")

            # Определение роли отключившегося игрока и удаление его из списка игроков
            for role, ws in list(self.players[lobby_id].items()):
                if ws == websocket:
                    del self.players[lobby_id][role]
                    logger.info(f"{role} отключился от лобби {lobby_id}")

                    # Удаление игрока из списка players лобби
                    players_list = lobbies[lobby_id]["players"]
                    # Предполагается, что player_id соответствует роли (player1, player2)
                    # В реальной ситуации может потребоваться более точная связь
                    players_list = [p for p in players_list if p.name != f"Player {role[-1]}"]
                    lobbies[lobby_id]["players"] = players_list
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

manager = ConnectionManager()

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

@app.post("/lobbies", response_model=LobbyResponse)
async def create_lobby(request: LobbyRequest):
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
    logger.info(f"Создано новое лобби {lobby_id} для игры")
    return LobbyResponse(lobbyId=lobby_id, message="Lobby created.", board=board)


@app.get("/lobbies/{lobbyId}", response_model=LobbyDetailsResponse)
async def get_lobby_details(lobbyId: str):
    """
    Fetches the details of a specific lobby along with the current board.
    """
    logger.info(f"Запрос деталей лобби {lobbyId}")
    lobby = lobbies.get(lobbyId)
    if not lobby:
        logger.warning(f"Лобби {lobbyId} не найдено")
        raise HTTPException(status_code=404, detail="Lobby not found")
    return LobbyDetailsResponse(
        lobbyId=lobbyId,
        gameId=lobby["gameId"],
        players=lobby["players"],
        board=lobby["board"]
    )

@app.get("/lobbies", response_model=List[LobbyDetailsResponse])
async def get_all_lobbies():
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

def generate_sudoku_board():
    """
    Generates a 9x9 Sudoku board with some pre-filled values.
    """
    board = [[0 for _ in range(9)] for _ in range(9)]
    # Simple example: fill some cells with random numbers for demonstration
    # В реальной игре нужно генерировать валидную Sudoku доску
    for _ in range(10):  # Fill 10 cells with random numbers
        row = random.randint(0, 8)
        col = random.randint(0, 8)
        num = random.randint(1, 9)
        if board[row][col] == 0:
            board[row][col] = num
    return board

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

@app.websocket("/ws/lobby/{lobbyId}")
async def websocket_endpoint(websocket: WebSocket, lobbyId: str):
    logger.info(f"Получен запрос на подключение к WebSocket лобби {lobbyId}")
    success = await manager.connect(lobbyId, websocket)
    if not success:
        logger.info(f"Подключение к лобби {lobbyId} не удалось (лобби заполнено)")
        return
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Получено сообщение от {lobbyId}: {data}")
            # Обработка сообщений
            try:
                move = json.loads(data)
                move_request = MoveRequest(**move)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format."}))
                continue
            except Exception as e:
                await websocket.send_text(json.dumps({"error": f"Invalid move data: {e}"}))
                continue

            # Получаем текущую доску
            current_board = lobbies[lobbyId]["board"]

            # Проверка валидности хода
            valid, message = is_valid_move(current_board, move_request.row, move_request.col, move_request.value)
            if valid:
                # Применяем ход
                current_board[move_request.row][move_request.col] = move_request.value
                logger.info(f"Ход принят: {move_request.player} поставил {move_request.value} на позицию ({move_request.row}, {move_request.col})")

                # Проверяем, завершена ли игра
                game_over, game_message = check_game_over(current_board)
                if game_over:
                    await manager.broadcast(lobbyId, json.dumps({
                        "message": game_message,
                        "board": current_board
                    }))
                    logger.info(f"Игра в лобби {lobbyId} завершена: {game_message}")
                    # Здесь можно добавить логику завершения игры, например, удаление лобби
                else:
                    # Отправляем обновленную доску всем игрокам
                    await manager.broadcast(lobbyId, json.dumps({
                        "message": f"{move_request.player} made a move.",
                        "board": current_board
                    }))
            else:
                # Отправляем сообщение об ошибке только отправителю
                await websocket.send_text(json.dumps({"error": message}))
                logger.warning(f"Неверный ход от {move_request.player}: {message}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket отключён от лобби {lobbyId}")
        manager.disconnect(lobbyId, websocket)
        await manager.broadcast(lobbyId, json.dumps({"message": "A player has disconnected"}))
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

