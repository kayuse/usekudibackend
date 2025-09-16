from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut, \
    BudgetInsightOut
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.budget_service import BudgetService
from app.services.transaction_service import TransactionService  # Adjust import paths as needed

router = APIRouter(
    prefix="/api/budget",
    tags=["budget"]
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


@router.get("/insight", response_model=list[BudgetInsightOut], status_code=status.HTTP_200_OK)
async def add(user: UserOut = Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = BudgetService(db_session=db)
        today = datetime.today()
        first_day = today.replace(day=1)
        if today.month == 12:  # December case
            last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

        response = service.get_budget_insights(first_day, last_day, user)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Something went wrong while fetching the insight ")


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
