from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.data.ai_models import AnalysisRequest, FaceRequest
from app.database.index import get_db
from app.services.face_verification_service import FaceVerificationService
from app.services.file_upload_service import FileUploadService

router = APIRouter()


def get_service(db: Session = Depends(get_db)):
    return FaceVerificationService(db_session=db)

def get_file_service():
    return FileUploadService()


@router.post('/api/face/upload', status_code=status.HTTP_201_CREATED)
async def upload(blink_file: UploadFile = File(...),
                 smile_file: UploadFile = File(...),
                 key: str = Form(...),
                 service: FileUploadService = Depends(get_file_service)):
    files: List[UploadFile] = [blink_file, smile_file]
    response = service.upload(files)
    if response is None:
        raise HTTPException(status_code=400, detail="Could Not Schedule An AI Analysis")
    return response


@router.post("/api/face/verify", status_code=status.HTTP_201_CREATED)
async def verify(blink_file: str = Form(...),
                 smile_file: str = Form(...),
                 original_image: str = Form(...),
                 key: str = Form(...),
                 service: FaceVerificationService = Depends(get_service)):
    response = await service.run(blink_file, smile_file, original_image, key)
    if response is None:
        raise HTTPException(status_code=400, detail="Could Not Schedule An AI Analysis")
    return response


@router.get("/users/{username}", tags=["users"])
async def read_user(username: str):
    return {"username": username}
