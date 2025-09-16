from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session

from app.data.account import TransactionOut, TransactionSearch, TransactionCategoryOut, BudgetCreate, BudgetOut
from app.data.user import UserOut
from app.database.index import decode_user, get_db
from app.services.budget_service import BudgetService
from app.services.transaction_service import TransactionService  # Adjust import paths as needed

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"]
)


# @router.get("/", response_model=List[TransactionRead])
# def list_transactions(account_id: int = None, db: Session = Depends(get_db)):
#     service = TransactionService(db_session=db)
#     transaction = service.get_transactions()
#     query = db.query(Transaction)
#     if account_id:
#         query = query.filter(Transaction.account_id == account_id)
#     return query.all()

@router.get(
    "/summary/category",
    response_model=List[TransactionCategoryOut])
async def get_transaction_categories(
        user: UserOut = Depends(decode_user),
        db: Session = Depends(get_db)):
    try:
        service = TransactionService(db_session=db)
        from_date = datetime.now() - timedelta(days=30)
        to_date = datetime.now()
        response = service.get_transaction_summary(user=user, from_date=from_date, to_date=to_date)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/add", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def add(account: BudgetCreate, user : UserOut= Depends(decode_user), db: Session = Depends(get_db)):
    try:
        service = BudgetService(db_session=db)
        response = await service.create_account(user, account)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Something went wrong while creating the account ")

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
