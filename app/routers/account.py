# create routes for authentication and user management
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.data.mono import AccountMonoData, MonoAccountLinkData, MonoAccountLinkResponse
from app.services.account_service import AccountService

from app.data.account import AccountCreate, AccountCreateOut, AccountExchangeOut, AccountLinkData, AccountOut, \
    AccountExchangeCreate, BankOut, BankCreate, BankCreateMultiple
from app.data.user import UserCreate, UserLogin, UserOut, Token
from app.database.index import get_db, decode_user

from app.services.auth_service import AuthService
from app.models.user import User
from fastapi.security import OAuth2PasswordBearer

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.post("/add", response_model=AccountCreateOut, status_code=status.HTTP_201_CREATED)
async def add(account: AccountCreate, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = await service.create_account(user, account)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while creating the account ")


@router.post("/exchange", response_model=AccountExchangeOut, status_code=status.HTTP_201_CREATED)
async def add(data: AccountExchangeCreate, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = service.establish_exchange(data)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{id}/sync", response_model=AccountOut, status_code=status.HTTP_200_OK)
async def sync(id: int, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = service.sync_account(id, user.id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# disable account
@router.put("/{id}/disable", response_model=AccountOut, status_code=status.HTTP_200_OK)
async def disable_account(id: int, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        account = service.disable_account(id, user.id)
        return account
    except ValueError as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# list all banks
@router.get("/banks", response_model=list[BankOut], status_code=status.HTTP_200_OK)
async def get_banks(db: Session = Depends(get_db)):
    service = AccountService(db_session=db)
    banks = service.get_banks()
    if not banks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No banks found")
    
    return [BankOut(bank_id=bank.id, bank_name=bank.bank_name, image_url=bank.image_url, bank_account_type=bank.bank_account_type, bank_code=bank.bank_code, institution_id=bank.institution_id) for bank in banks]

@router.post("/initiate-sync/{id}", response_model=AccountMonoData, status_code=status.HTTP_200_OK)
async def initiate_sync(id: int, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = await service.initiate_account_linking(id, user.id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# get account details
@router.get("/user", response_model=List[AccountOut], status_code=status.HTTP_200_OK)
async def get_account_by_user(user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        data = service.get_accounts_by_user(user.id)

        return data
    except ValueError as e:
        print(e.args)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# delete account
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(id: int, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        service.delete_account(id, user.id)
        return {"detail": "Account deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/link-account", response_model=AccountMonoData, status_code=status.HTTP_200_OK)
async def link_account(data: AccountLinkData, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = await service.link_account(data, user.id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# write an endpoint to get session id from cache and find out whether the session is active or not
@router.get("/session/{session_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_session_status(session_id: str, db: Session = Depends(get_db)):
    try:
        service = AccountService(db_session=db)
        response = await service.get_session_status(session_id)
        if not response:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or inactive")
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while fetching session status")
