#create routes for authentication and user management
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.services.account_service import AccountService

from app.data.account import AccountCreate, AccountExchangeOut,AccountOut, AccountExchangeCreate, BankOut
from app.data.user import UserCreate, UserLogin, UserOut, Token
from app.database.index import get_db,decode_user     

from app.services.auth_service import AuthService
from app.models.user import User
from fastapi.security import OAuth2PasswordBearer

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")



@router.post("/add", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def add(account: AccountCreate, user : UserOut= Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = service.create_account(user, account)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/exchange", response_model=AccountExchangeOut, status_code=status.HTTP_201_CREATED)
async def add(data: AccountExchangeCreate, user : UserOut= Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = service.establish_exchange(data)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(user_create: UserLogin, db: Session = Depends(get_db)):
    auth_service = AuthService(db_session=db)
    token = auth_service.login(user_create.email, user_create.password)
    
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
  
    return token
# list all banks
@router.get("/banks", response_model=list[BankOut], status_code=status.HTTP_200_OK)
async def get_banks(db: Session = Depends(get_db)):
    service = AccountService(db_session=db)
    banks = service.get_banks()
    if not banks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No banks found")
    
    return [BankOut(bank_id=bank.id, bank_name=bank.bank_name, image_url=bank.image_url) for bank in banks]

@router.get("users/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def get_current_user(user : UserOut =Depends(decode_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user

@router.get("users/{user_id}", response_model=UserOut, status_code=status.HTTP_200_OK)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    auth_service = AuthService(db_session=db)
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return UserOut(id=user.id, email=user.email)

@router.get("users/", response_model=list[UserOut], status_code=status.HTTP_200_OK)
async def get_all_users(db: Session = Depends(get_db)):
    auth_service = AuthService(db_session=db)
    users = db.query(User).all()
    
    if not users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No users found")
    
    return [UserOut(id=user.id, email=user.email) for user in users]

@router.delete("users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    auth_service = AuthService(db_session=db)
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    db.delete(user)
    db.commit()
    return {"detail": "User deleted successfully"}

@router.put("users/{user_id}", response_model=UserOut, status_code=status.HTTP_200_OK)
async def update_user(user_id: int, user_update: UserCreate, db: Session = Depends(get_db)):
    auth_service = AuthService(db_session=db)
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    user.email = user_update.email
    user.firstname = user_update.firstname
    user.lastname = user_update.lastname
    user.hashed_password = auth_service.hash_password(user_update.password)
    
    db.commit()
    db.refresh(user)
    
    return UserOut(id=user.id, email=user.email)