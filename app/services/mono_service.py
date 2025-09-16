#create a service to handle mono api calls
import os
from typing import List
from uuid import uuid4  

from dotenv import load_dotenv
import requests
from app.data.mono import MonoAccountBalanceResponse, MonoAccountLinkResponse, MonoAuthResponse
from app.data.account import AccountExchangeCreate, AccountExchangeOut, AccountLinkData
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
            raise ValueError("Failed to authenticate with Mono API")
        return data
    
    def disable(self, account_id: str) -> bool:
        headers = MonoService.get_header()
        response = requests.post(f'{self.mono_api_base_url}/accounts/{account_id}/unlink', headers=headers)
        print(response.text)
        if response.status_code != 200:
            raise ValueError("Failed to disable account")
        return True
    
    def get_transactions(self, account_id: str, start_date: str = None, end_date: str = None, realtime = False) -> List[dict]:
        headers = MonoService.get_header()
        if realtime:
            headers['x-realtime'] = 'true'
        url = f'{self.mono_api_base_url}/accounts/{account_id}/transactions'
        params = {'paginate': 'false'}  # Adjust pagination as needed
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise ValueError("Failed to fetch transactions")
        return response.json().get('data', []) or []
    
    def get_institutions(self) -> List[dict]:
        headers = MonoService.get_header()
        response = requests.get('https://api.withmono.com/v3/institutions', headers=headers)
        if response.status_code != 200:
            raise ValueError("Failed to fetch institutions")
        return response.json().get('data', [])
    
    def link_account(self, data: AccountExchangeCreate) -> AccountExchangeOut:
        headers = MonoService.get_header()
        response = requests.post(f'{self.mono_api_base_url}/accounts', json=data.dict(), headers=headers)
        if response.status_code != 200:
            raise ValueError("Failed to link account")
        response_data = response.json()
        return AccountExchangeOut(**response_data)
    
    def initiate_account_linking(self, data: AccountLinkData) -> MonoAccountLinkResponse:
        headers = MonoService.get_header()
        data = {
            'customer' : {'email': data.customer_email, 'name': data.customer_name},
            'scope': 'auth',
            'institution':{
                'id': data.institution_id,
                'auth_method': data.institution_auth_method
            },
            # 'meta_ref': data.meta_ref,
            'redirect_url': data.redirect_url,
        }
        response = requests.post(f'{self.mono_api_base_url}/accounts/initiate', json=data, headers=headers)
        print(response.text)
        if response.status_code != 200:
            raise ValueError("Failed to initiate account linking")
        response_data = response.json()
        print(f"Response from Account Linking Mono API: {response_data}")
        return MonoAccountLinkResponse(**response_data)