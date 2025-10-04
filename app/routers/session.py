from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from typing import List
from sqlalchemy.orm import Session

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut
from app.data.session import SessionCreate, SessionOut, AccountExchangeSessionCreate, SessionAccountOut, IncomeFlowOut
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.budget_service import BudgetService
from app.workers.session_tasks import analyze_transactions, analyze_payments
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
                      session_id: str = Form(...),
                      passwords: List[str] = Form(...),
                      is_password: List[bool] = Form(...),
                      db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        result = await service.process_statements(session_id, files, passwords, is_password, bank_ids)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/analyze/{session_id}")
def analyze(session_id: str):
    try:
        analyze_transactions.delay(session_id)
        return {"result": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/analyze-payments/{session_id}")
def analyze(session_id: str):
    try:
        analyze_payments.delay(session_id)
        return {"result": True}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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


@router.get('/{session_id}')
async def session(session_id: str, db: Session = Depends(get_db), response_model=SessionOut):
    try:
        service = SessionService(db=db)
        response = service.get_session(session_id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while creating the account ")
