from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from typing import List
from sqlalchemy.orm import Session

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut
from app.data.session import SessionCreate, SessionOut, AccountExchangeSessionCreate, SessionAccountOut, IncomeFlowOut
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.budget_service import BudgetService
from app.workers.session_tasks import analyze_transactions
from app.services.session_service import SessionService
from app.services.session_transaction_service import SessionTransactionService
from app.services.transaction_service import TransactionService  # Adjust import paths as needed

router = APIRouter(
    prefix="/api/session",
    tags=["session"]
)


@router.post("/start", response_model=SessionOut)
def start(data: SessionCreate, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        return service.start(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/process/statements")
async def upload_file(files: list[UploadFile] = File(...),
                      bank_ids: List[int] = Form(...),
                      session_id: str = Form(...), db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        result = await service.process_statements(session_id, files, bank_ids)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/analyze/{id}")
async def analyze(id: str):
    try:
        await analyze_transactions.delay(id)
        return {"result": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/account/create", response_model=SessionAccountOut, status_code=status.HTTP_201_CREATED)
async def add(account: AccountExchangeSessionCreate, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        response = service.exchange_account_session(account)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while creating the account ")


@router.get("/income-flow/{session_id}", response_model=IncomeFlowOut, status_code=status.HTTP_200_OK)
async def add(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionTransactionService(db=db)
        response = service.get_income_flow(session_id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while creating the account ")


@router.get("/user", response_model=List[TransactionOut])
def get_transactions_for_user_skip(
        skip: int = 0,
        limit: int = 200,
        start_date: str = None,
        end_date: str = None,
        category_id: int = None,
        search_text: str = None,
        account_id: int = None,
        user: UserOut = Depends(decode_user),
        db: Session = Depends(get_db)
):
    start_date_data = datetime.strptime(start_date,
                                        "%Y-%m-%dT%H:%M:%S.%fZ") if start_date else datetime.now() - timedelta(days=7)
    end_date_data = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ") if end_date else datetime.now()
    transaction_search = TransactionSearch(
        start_date=start_date_data,
        end_date=end_date_data,
        account_id=account_id,
        text=search_text,
        category_id=category_id,
        skip=skip,
        limit=limit
    )
    service = TransactionService(db_session=db)
    transactions = service.search(user_id=user.id, params=transaction_search)
    return transactions


@router.get("/institutions")
async def get_institutions(db: Session = Depends(get_db)):
    service = TransactionService(db_session=db)
    institutions = await service.get_institutions()
    if not institutions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No institutions found")
    return institutions
