#create a service to handle mono api calls
import os
from typing import List
from uuid import uuid4  

from dotenv import load_dotenv
import requests
from app.data.mono import MonoAccountBalanceResponse, MonoAuthResponse
from app.data.account import AccountExchangeCreate, AccountExchangeOut
from app.models.account import Account, Bank, FetchMethod
from sqlalchemy.orm import Session
from app.database.index import get_db

load_dotenv()
class MonoService:
    def __init__(self):
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')
    
    @staticmethod
    def get_header() -> dict:
        return { 
            'Content-Type': 'application/json',
            'mono-sec-key':  f'{os.getenv("MONO_API_SECRET")}'
        }

    def fetch_account_balance(self, account_id : str) -> MonoAccountBalanceResponse:
        headers = MonoService.get_header()
        response = requests.get(f'{self.mono_api_base_url}/accounts/{account_id}/balance', headers=headers)
        data : MonoAccountBalanceResponse = MonoAccountBalanceResponse(**response.json())
        if response.status_code != 200:
            raise Exception("Failed to authenticate with Mono API")
        return data