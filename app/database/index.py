from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from jose import jwt, JWTError

from app.data.user import UserOut

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_token(token: str) -> UserOut:
    try:
     
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return UserOut(id=int(user_id), email=payload.get("sub", ""), fullname=payload.get("fullname", ""))
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def decode_user(token: str = Depends(oauth2_scheme)) -> UserOut:
    return verify_token(token)