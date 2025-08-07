
from http.client import HTTPException
from fastapi import APIRouter, Depends, Request, status
from requests import Session

from app.database.index import get_db
from app.services.message_service import MessageService


router = APIRouter(
    prefix="/api/message",
    tags=["transactions"]
)


@router.post("/process", response_model=dict, status_code=status.HTTP_200_OK)
async def process_message(request : Request, db: Session = Depends(get_db)):
    service = MessageService(db_session=db)
    body = await request.body()
    #break body into dictionary
    body = body.decode('utf-8')
    body = {k: v for k, v in (x.split('=') for x in body.split('&'))}
    result = await service.process(body)
    
    result = {'status': 'success', 'message': 'Message processed successfully'}
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No message sent")
    return result