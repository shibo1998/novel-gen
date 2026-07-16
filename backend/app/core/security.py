from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

security = HTTPBearer(auto_error=False)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData:
    """Token 数据模型"""
    def __init__(self, user_id: str, exp: datetime):
        self.user_id = user_id
        self.exp = exp


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def _authentication_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_token(token: str) -> TokenData:
    """验证令牌并返回数据"""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type", "access")

        if user_id is None:
            raise _authentication_error("Invalid authentication credentials")

        if token_type != "access":
            raise _authentication_error("Invalid authentication credentials")

        exp_timestamp = payload.get("exp", 0)
        return TokenData(user_id=user_id, exp=datetime.fromtimestamp(exp_timestamp))

    except ExpiredSignatureError:
        raise _authentication_error("Invalid authentication credentials") from None
    except JWTError:
        raise _authentication_error("Invalid authentication credentials") from None


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """从 Authorization Bearer header 解析当前用户。"""
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(creds.credentials)
    return token_data.user_id


async def get_current_active_user(
    current_user_id: str = Depends(get_current_user)
) -> str:
    """获取当前活跃用户（可扩展验证逻辑）"""
    return current_user_id


def decode_refresh_token(token: str) -> TokenData:
    """验证刷新令牌"""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type", "")

        if user_id is None or token_type != "refresh":
            raise _authentication_error("Invalid refresh token")

        exp_timestamp = payload.get("exp", 0)
        return TokenData(user_id=user_id, exp=datetime.fromtimestamp(exp_timestamp))

    except ExpiredSignatureError:
        raise _authentication_error("Invalid refresh token") from None
    except JWTError:
        raise _authentication_error("Invalid refresh token") from None
