import base64
import os
import shutil
import traceback
import uuid
from io import BytesIO
from typing import List

from botocore.client import BaseClient
from botocore.exceptions import NoCredentialsError
from confluent_kafka import Producer

from sqlalchemy.orm import Session
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
import boto3

from ..util.errors import CustomError

load_dotenv(override=True)
class FileUploadService:
    conf: dict
    producer: Producer
    KAFKA_COMMUNITY_TOPIC = ''
    bucket_name = ''
    s3_client: BaseClient

    def __init__(self):
        self.upload_file_path = os.getenv('FILE_UPLOAD_PATH')
        self.s3_client = boto3.client('s3', region_name=os.getenv('AWS_DEFAULT_REGION'))
        self.bucket_name = os.getenv('AWS_BUCKET_NAME')

    def upload_base64(self, data):
        try:
            file_data = base64.b64decode(data)
            file_path = str(uuid.uuid4()) + str(
                uuid.uuid4()) + ".png"  # Save as a PNG (or whatever file extension is appropriate)
            with open(file_path, "wb") as f:
                f.write(file_data)

            with open(file_path, "rb") as file_to_upload:
                self.s3_client.upload_fileobj(file_to_upload, self.bucket_name, file_path)

            if os.path.exists(file_path):
                os.remove(file_path)

            return file_path
        except Exception as e:
            raise CustomError("Unable to decode image as an image please check your base64 string")

    async def upload(self, files: List[UploadFile]) -> List[str]:
        responses = []
        try:
            for file in files:
                # Read the file content as bytes
                file_content = await file.read()
                file_name = file.filename + str(uuid.uuid4())
                # Upload file to S3 bucket
                self.s3_client.upload_fileobj(
                    BytesIO(file_content),  # File-like object containing the data
                    self.bucket_name,  # S3 bucket name
                    file_name  # S3 file key (same as original file name here)
                )
                responses.append(file_name)

            return responses

        except NoCredentialsError:
            raise CustomError("Invalid Credentials")

        except Exception as e:
            raise CustomError("Error Uploading File")

    async def upload_to_path(self, files: List[UploadFile]) -> List[str]:
        responses = []
        try:
            for file in files:
                # Read the file content as bytes
                # file_content = await file.read()
                file_name = f"{str(uuid.uuid4())}{file.filename}"
                # Upload file to S3 bucket
                file_path = os.path.join(self.upload_file_path, file_name)

                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                responses.append(file_path)

            return responses

        except NoCredentialsError:
            raise CustomError("Invalid Credentials")

        except Exception as e:
            traceback.print_exc()
            raise CustomError("Error Uploading File")

    def download_file_from_s3(self, file_key):
        try:
            # Download the file from S3 to memory (using BytesIO)
            file_obj = BytesIO()
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_key)
            image_bytes = response['Body'].read()

            return image_bytes

        except NoCredentialsError:
            print("Credentials not available")
            return None

        except Exception as e:
            print(f"Error downloading the file: {str(e)}")
            return None
