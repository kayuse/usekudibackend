#create an authentication service that handles user registration, login, and token generation
from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status
from passlib.context import CryptContext
from jose import JWTError, jwt  

from app.data.user import UserCreate, UserOut, Token
from app.database.index import get_db
from app.models.user import User
from sqlalchemy.orm import Session
import os

class AuthService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret = os.getenv('SECRET_KEY') # Replace with your actual secret key
        self.expire_minutes = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))  # Default to 30 minutes if not set
        self.algorithm = "HS256"
        
    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self.secret, algorithm=self.algorithm)
    
    #decode access token
    def decode_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
    def register_user(self, user_create: UserCreate) -> UserOut:
        hashed_password = self.hash_password(user_create.password)
        db_user = User(
            email=user_create.email,
            firstname=user_create.firstname,
            fullname=f"{user_create.firstname} {user_create.lastname}",
            lastname=user_create.lastname,
            username=user_create.email,  # Assuming username is the email
            is_active=True,
            is_superuser=False,  # Default to False, can be changed later
            hashed_password=hashed_password
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return UserOut(id=db_user.id, email=db_user.email, fullname=db_user.fullname)
    
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = self.db.query(User).filter(User.email == email).first()
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        return user
    
    def login(self, email: str, password: str) -> Token:
        user = self.authenticate_user(email, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=30)
        data: dict = {"sub": user.email, "fullname": user.fullname, "id": user.id}
        # Create access token with expiration
        access_token = self.create_access_token(
            data=data
        )
        return Token(access_token=access_token, token_type="bearer", user=UserOut(
            id=user.id,
            email=user.email,
            fullname=user.fullname
        ))
    
    def get_current_user(self, token: str) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            email: str = payload.get("sub")
            if email is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception
        user = self.db.query(User).filter(User.email == email).first()
        if user is None:
            raise credentials_exception
        return user
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        user = self.db.query(User).filter(User.email == email).first()
        return user if user else None