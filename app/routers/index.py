from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Request
from sqlalchemy.orm import Session

from app.database.index import get_db
from app.services.account_service import AccountService
from app.services.file_upload_service import FileUploadService
from app.workers.account_tasks import auto_fetch_transactions
from app.workers.transaction_tasks import generate_transaction_embeddings

router = APIRouter()



def get_file_service():
    return FileUploadService()



@router.get("/users/{username}", tags=["users"])
async def read_user(username: str):
    return {"username": username}

@router.get('/run')
async def run_cron():
    generate_transaction_embeddings.delay()

@router.get('/complete', tags=["authentication"])
async def complete_authentication(request: Request):
    """
    Endpoint to complete the authentication process.
    This is a placeholder and should be replaced with actual logic.
    """
    return {"message": "Authentication completed successfully."}

# write a webhook callback endpoint to handle the response from Mono
@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook_callback(data: dict, db: Session = Depends(get_db)):
    try:
        print(f"Received webhook data: {data}")
        if(data.get('event') == 'mono.events.account_connected'):
            account_data = data.get('data', {})
            account_service = AccountService(db_session=db)
            account = await account_service.sync_account_id_with_account(account_data)
            print(f"Account synced: {account}")
        elif(data.get('event') == 'mono.events.account_unlinked'):
            print(f"Account disabled: {account}")
        return {"detail": "Webhook processed successfully", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Something went wrong while processing the webhook")