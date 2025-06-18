import base64
import io
import uuid
from typing import List

from fastapi import Depends

from .file_upload_service import FileUploadService
from ..data.ai_models import FaceRequest
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import tensorflow as tf

from ..models.verification import FaceRequests
from ..util.errors import CustomError

tf.config.set_soft_device_placement(True)


def get_file_service(db: Session = Depends()):
    return FileUploadService()


class FaceVerificationService:
    conf: dict
    producer: None
    KAFKA_COMMUNITY_TOPIC = ''
    db_session: Session
    upload_service: FileUploadService

    def __init__(self, db_session: Session, upload_service: FileUploadService = Depends(get_file_service)):
        self.db_session = db_session
        self.upload_service: FileUploadService = FileUploadService()
        load_dotenv()

    def run_verification(self, request: FaceRequest) -> FaceRequests:
        request = FaceRequests(live_image=request.live_image,
                               to_image=request.to_image)
        score, score_cosine = self.detect(request.live_image, request.to_image)
        request.score_cosine = float(score_cosine)
        request.score = float(score)
        spoofed = self.spoofed(request.live_image)

        self.db_session.add(request)
        self.db_session.commit()
        self.db_session.refresh(request)
        return request

    async def run(self, blink_file: str, smile_file: str, original_image: str, key: str) -> FaceRequests:
        if original_image == "''" or smile_file == "''" or blink_file == "''":
            raise CustomError("Invalid Base64 File")
        base_img = self.upload_service.upload_base64(original_image)
        blink_img = self.upload_service.upload_base64(blink_file)
        smile_img = self.upload_service.upload_base64(smile_file)

        request = FaceRequests(blink_image=blink_img, smile_image=smile_img,
                               base_image=base_img, application_id=1)
        blink_score, blink_score_cosine = self.detect(request.blink_image, request.base_image)
        request.blink_score = float(blink_score)
        request.blink_score_cosine = float(blink_score_cosine)

        smile_score, smile_score_cosine = self.detect(request.smile_image, request.base_image)
        request.smile_score = float(smile_score)
        request.smile_score_cosine = float(smile_score_cosine)

        # request.smile_spoof_score = float(self.spoofed(request.smile_image)[0][0])
        # request.blink_spoof_score = float(self.spoofed(request.blink_image)[0][0])

        self.db_session.add(request)
        self.db_session.commit()
        self.db_session.refresh(request)
        return request

    def process_smile_image(self, request: FaceRequests):
        score, score_cosine = self.detect(request.smile_images, request.base_image)
        return score, score_cosine

    def process_blink_image(self, request: FaceRequests):
        score, score_cosine = self.detect(request.smile_images, request.base_image)
        return score, score_cosine

    def detect(self, live, to):
        return ''

    def get_image_for_keras(self, image_url):
        img_bytes = self.upload_service.download_file_from_s3(image_url)

        # Convert the byte data to a file-like object
        image_obj = io.BytesIO(img_bytes)
        image = Image.open(image_obj)
        image = image.convert('RGB')
        image = image.resize((64, 64))
        image_array = np.array(image)
        image_array = image_array.astype('float32') / 255.0
        image_array = np.expand_dims(image_array, axis=0)  # Add batch dimension

        return image_array

    def get_face(self, image_url, img_type='s3'):
        return 0

    def compare_faces_cosine(self, embedding1, embedding2, threshold=0.6):
        return 0

    def get_embedding(self, model, face):
        return 0
