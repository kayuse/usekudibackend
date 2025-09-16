from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut, \
    BudgetInsightOut
from app.data.dashboard import DashboardBalanceOut, SpendingInsightOut
from app.data.transaction_insight import ChatCreate
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.advice_service import AdviceService
from app.services.ai_service import AIService
from app.services.budget_service import BudgetService
from app.services.dashboard_service import DashboardService
from app.services.transaction_ai_service import TransactionAIService
from app.services.transaction_service import TransactionService  # Adjust import paths as needed

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)


# @router.get("/", response_model=List[TransactionRead])
# def list_transactions(account_id: int = None, db: Session = Depends(get_db)):
#     service = TransactionService(db_session=db)
#     transaction = service.get_transactions()
#     query = db.query(Transaction)
#     if account_id:
#         query = query.filter(Transaction.account_id == account_id)
#     return query.all()

@router.post("/create", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def start(data: BudgetCreate, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = BudgetService(db_session=db)
        response = service.add_budget(user=user, budget_create=data)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/balance", response_model=DashboardBalanceOut)
async def get_balance(db: Session = Depends(get_db), user: UserOut = Depends(decode_user)):
    try:
        service = DashboardService(db_session=db)
        accounts = service.get_accounts(user=user)
        balance = sum(account.current_balance for account in accounts)
        outflow = service.get_outflow(user=user)
        result = DashboardBalanceOut(total_balance=balance, outflow=outflow)
        return result

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while fetching the insight ")


@router.get("/insight", response_model=SpendingInsightOut, status_code=status.HTTP_200_OK)
async def add(user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = DashboardService(db_session=db)
        outflow = service.get_outflow(user=user)
        last_month_outflow = service.get_total_spent_last_month(user=user)
        daily_average = service.get_daily_average(user=user)
        weekly_average = service.get_weekly_average(user=user)
        result = SpendingInsightOut(outflow=outflow, outflow_last_month=last_month_outflow,
                                    daily_average_in=daily_average.average_in,
                                    daily_average_out=daily_average.average_out,
                                    weekly_average_in=weekly_average.average_in,
                                    weekly_average_out=weekly_average.average_out)
        return result

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while fetching the insight ")


@router.get("/spending-insight", response_model=List)
def get_transactions_for_user_skip(user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    service = TransactionAIService(db_session=db)
    insights = service.generate_insights(user)
    return insights


@router.post("/chat", response_model=object)
def chat(data: ChatCreate, user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    service = AdviceService(db_session=db)
    chat = service.process(user, data.text)
    # response = AIService(db_session=db).generate_response(context='A Chat Response for a financial assistant', prompt=chat)
    return chat


@router.get("/institutions")
async def get_institutions(db: Session = Depends(get_db)):
    service = TransactionService(db_session=db)
    institutions = await service.get_institutions()
    if not institutions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No institutions found")
    return institutions
