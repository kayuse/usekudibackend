import traceback
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from typing import List
from sqlalchemy.orm import Session
from websocket import WebSocket

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut, \
    TransactionWeekCategoryOut, WeeklyTrend
from app.data.mail import EmailTemplateData
from app.data.session import SessionCreate, SessionOut, AccountExchangeSessionCreate, SessionAccountOut, IncomeFlowOut, \
    SessionInsightOut, SessionSwotOut, SpendingProfileOut, FinancialProfileDataIn, SessionSavingsPotentialOut, \
    SessionBeneficiaryOut, SessionTransactionOut
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.budget_service import BudgetService
from app.services.email_services import EmailService
from app.services.session_advice_service import SessionAdviceService
from app.services.session_payment_service import SessionPaymentService
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
                      db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        result = await service.process_statements(session_id, files, bank_ids)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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


@router.get('/insights/{session_id}', response_model=list[SessionInsightOut], status_code=status.HTTP_200_OK)
async def insights(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        insights = service.get_insights(session_id)
        return insights
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/swot/{session_id}', response_model=list[SessionSwotOut], status_code=status.HTTP_200_OK)
async def swot(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        return service.get_swot(session_id)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/financial-position/{session_id}', status_code=status.HTTP_200_OK, response_model=FinancialProfileDataIn)
async def spending_profile(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionTransactionService(db=db)
        return service.calculate_financial_position(session_id)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/savings-potential/{session_id}', status_code=status.HTTP_200_OK,
            response_model=List[SessionSavingsPotentialOut])
async def savings_potential(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        return service.get_savings_potentials(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.post('/regenerate/{session_id}', status_code=status.HTTP_200_OK)
async def regenerate(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionService(db=db)
        result = await service.retry_process_statements(session_id)
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/weekly-trend/{session_id}', status_code=status.HTTP_200_OK, response_model=WeeklyTrend)
async def weekly_income_report(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionTransactionService(db=db)
        return service.calculate_weekly_trend(session_id)
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/beneficiaries/{session_id}', status_code=status.HTTP_200_OK, response_model=list[SessionBeneficiaryOut])
async def beneficiaries(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionTransactionService(db=db)
        return service.get_beneficiaries(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/transfers/{session_id}', status_code=status.HTTP_200_OK, response_model=list[SessionTransactionOut])
async def transfers(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionTransactionService(db=db)
        return service.get_transfers(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get('/recurring-expenses/{session_id}', status_code=status.HTTP_200_OK)
async def recurring_expenses(session_id: str, db: Session = Depends(get_db)):
    try:
        service = SessionAdviceService(db_session=db)
        return service.get_recurring_expenses(session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )


@router.get("/verify-payment/{session_id}/{reference}")
def verify_payment(session_id: str, reference: str, db: Session = Depends(get_db)):
    """Verify payment with Paystack"""
    try:
        service = SessionPaymentService(db=db)
        result = service.verify_payment(session_id, reference)
        if result:
            return {"status": "success", "message": "Payment verified successfully"}
        else:
            return {"status": "failed", "message": "Payment verification failed"}

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, )
