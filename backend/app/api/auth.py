from collections import deque
from collections.abc import Callable
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    create_access_token,
    decode_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.domain import User
from app.models.schemas import Token, UserCreate, UserLogin, UserResponse

router = APIRouter(prefix="/api/auth", tags=["认证"])
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-user-password")


class LoginThrottle:
    """Bounded process-local sliding window for failed logins."""

    def __init__(
        self,
        failure_limit: int,
        window_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.failure_limit = max(1, failure_limit)
        self.window_seconds = max(1, window_seconds)
        self.max_entries = max(2, max_entries)
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    @staticmethod
    def _client_key(client: str) -> str:
        return f"client:{client}"

    @staticmethod
    def _account_key(account: str) -> str:
        return f"account:{account.strip().casefold()}"

    def _prune_key_locked(self, key: str, now: float) -> None:
        attempts = self._failures.get(key)
        if attempts is None:
            return
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._failures.pop(key, None)

    def _make_room_locked(self, key: str, now: float) -> None:
        if key in self._failures:
            return
        for existing_key in list(self._failures):
            self._prune_key_locked(existing_key, now)
        while len(self._failures) >= self.max_entries:
            oldest_key = min(
                self._failures,
                key=lambda item: self._failures[item][-1],
            )
            self._failures.pop(oldest_key, None)

    def is_blocked(self, client: str, account: str) -> bool:
        now = self._clock()
        keys = (self._client_key(client), self._account_key(account))
        with self._lock:
            for key in keys:
                self._prune_key_locked(key, now)
            return any(
                len(self._failures.get(key, ())) >= self.failure_limit
                for key in keys
            )

    def record_failure(self, client: str, account: str) -> None:
        now = self._clock()
        keys = (self._client_key(client), self._account_key(account))
        with self._lock:
            for key in keys:
                self._prune_key_locked(key, now)
                self._make_room_locked(key, now)
                self._failures.setdefault(key, deque()).append(now)

    def clear_account(self, account: str) -> None:
        with self._lock:
            self._failures.pop(self._account_key(account), None)

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._failures)


login_throttle = LoginThrottle(
    failure_limit=settings.login_failure_limit,
    window_seconds=settings.login_failure_window_seconds,
    max_entries=settings.login_throttle_max_entries,
)


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """用户注册"""
    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user = User(
        email=user_in.email,
        username=user_in.username,
        password_hash=hash_password(user_in.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return {"message": "User created successfully", "user_id": str(user.id)}


@router.post("/login", response_model=Token)
async def login(
    user_in: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """用户登录"""
    client = request.client.host if request.client else "unknown"
    account = str(user_in.email).strip().casefold()
    if login_throttle.is_blocked(client, account):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(settings.login_failure_window_seconds)},
        )

    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    user = result.scalar_one_or_none()

    password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    password_valid = verify_password(user_in.password, password_hash)
    if not user or not password_valid:
        login_throttle.record_failure(client, account)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_throttle.clear_account(account)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    return Token(access_token=access_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str):
    """刷新访问令牌"""
    token_data = decode_refresh_token(refresh_token)

    access_token = create_access_token(data={"sub": token_data.user_id})

    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户信息"""
    result = await db.execute(
        select(User).where(User.id == current_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user
