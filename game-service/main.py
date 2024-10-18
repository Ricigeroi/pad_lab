# game_service.py
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import UserDB


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Добавьте ваш клиентский URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Конфигурация для JWT
SECRET_KEY = "banana"  # Замените на ваш секретный ключ
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Настройка хэширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="game_service/login")

# Временное хранилище пользователей (используйте базу данных в продакшене)
fake_users_db: Dict[str, Dict] = {}

# Модели Pydantic
class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

class UserRegister(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Функции для работы с пользователями и паролями
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

async def get_user(db: AsyncSession, username: str) -> Optional[UserDB]:
    result = await db.execute(select(UserDB).where(UserDB.username == username))
    return result.scalar_one_or_none()

async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[UserDB]:
    user = await get_user(db, username)
    if user and verify_password(password, user.hashed_password):
        return user
    return None


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось аутентифицировать пользователя",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = await get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled
    )


# Зависимость для получения текущего пользователя
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось аутентифицировать пользователя",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled
    )

# Маршрут регистрации
@app.post("/game_service/register", response_model=User)
async def register(user: UserRegister, db: AsyncSession = Depends(get_db)):
    existing_user = await get_user(db, user.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Имя пользователя уже существует")
    hashed_password = get_password_hash(user.password)
    new_user = UserDB(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        disabled=False,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return User(
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        disabled=new_user.disabled
    )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Маршрут логина
@app.post("/game_service/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Неверные имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# Пример защищенного маршрута
@app.get("/game_service/users/me", response_model=User)
async def read_users_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


# Существующие маршруты
SERVICE2_URL = "http://localhost:5002/lobby_service/data"
TIMEOUT = 10  # Set your desired timeout in seconds

@app.get("/game_service/hello", response_class=JSONResponse)
async def hello_game_service():
    """
    Возвращает приветственное сообщение от game_service.
    """
    return {"message": "Hello from game_service"}

@app.get("/game_service/combined", response_class=JSONResponse)
async def get_combined_data():
    """
    Получает данные от Service2 и возвращает комбинированный ответ.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await asyncio.wait_for(client.get(SERVICE2_URL), timeout=TIMEOUT)
            response.raise_for_status()  # Возбуждает исключение для HTTP-ошибок
            service2_data = response.json()
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail="Service2 не отвечает в течение заданного времени")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Service2 недоступен: {exc}")
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"Ошибка от Service2: {exc}")

    combined_response = {
        "service1_message": "Hello from Service1",
        "service2_data": service2_data
    }
    return combined_response
