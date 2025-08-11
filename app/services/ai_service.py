import json
from random import random
import string

from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_openai import ChatOpenAI
from requests import Session
from app.data.ai_models import AIMessageResponse, StateResponse
from app.data.user import UserCreate
from app.models.account import Category, Transaction
from langchain.prompts import PromptTemplate
from langchain.output_parsers import ResponseSchema, StructuredOutputParser  # Add this import
from langchain.chains import LLMChain
from openai import OpenAI
import os
from dotenv import load_dotenv
from app.models.user import User
from app.services.advice_service import AdviceService
from app.services.auth_service import AuthService
from app.services.cache_service import get_cache, set_cache

load_dotenv(override=True)


class AIService:
    def __init__(self, db_session=Session):
        self.open_ai_api_key = os.getenv('CHAT_GPT_KEY')  # Replace with your actual OpenAI API key
        self.db_session = db_session
        self.redis = os.getenv('REDIS_URL')
        self.openai_client = OpenAI(api_key=os.getenv('CHAT_GPT_KEY'))
        self.advice_service = AdviceService(
            db_session=db_session)  # Assuming you have an AdviceService to handle advice-related operations
        self.auth_service = AuthService(
            db_session=db_session)  # Assuming you have an AuthService to handle user-related operations

    async def process(self, ownerid: str, body: str) -> AIMessageResponse:
        state = await self.initialize_state(ownerid, message=body)
        if not state.onboarded:
            return AIMessageResponse(
                message=state.message
            )
        user = self.auth_service.get_mobile_user(ownerid)
        intent = self.classify_intent(body, user)
        print(intent)
        message = self.run_action(intent['action'], user, body)
        print(f"Intent classified: {intent}")
        return AIMessageResponse(
            message=self.generate_response(
                context=intent['action'],
                prompt=message.message
            ),
        )

    # generate an embedding for the given text using OpenAI's API vector database pgsql
    def generate_embedding(self, text: str) -> list:
        """
        Generate an embedding for the vector database using OpenAI's API.
        :param text: The text to generate an embedding for.
        :return: The embedding as a list.
        """
        res = self.openai_client.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        )
        return res.data[0].embedding

    def generate_unique_id(self, prefix, length=6):
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        return f"{prefix.upper()}-{random_part}"

    def run_action(self, action: str, user: User, prompt: str) -> AIMessageResponse:
        """
        Run the specified action with the provided data.
        This method can be extended to handle different actions.
        """
        if action == "link_account":
            # Handle account linking logic here
            code = self.generate_unique_id("user_" + user.id)
            data = {"user": user.id}
            set_cache(code, json.dumps(data), 7200)
            return AIMessageResponse(
                message=self.generate_response(
                    context="account_linking",
                    prompt=f"Please click the following link to link your account: {link_url}"
                )
            )
        elif action == "transaction":
            # Handle transaction logic here
            message = self.advice_service.process(user, prompt)
            return AIMessageResponse(
                message=message
            )
        elif action == "account":
            # Handle account logic here
            return AIMessageResponse(
                message="Account details retrieved successfully"
            )
        elif action == "user":
            # Handle user logic here
            return AIMessageResponse(
                message="User details retrieved successfully"
            )
        elif action == "account_resync":
            # Handle account resynchronization logic here
            return AIMessageResponse(
                message="Account resynchronized successfully"
            )
        elif action == "user_resync":
            return AIMessageResponse(message="User resynchronized successfully")
        elif action == "dashboard_request":
            return AIMessageResponse(
                message="Dashboard requests retrieved successfully, Your Dashboard URL is: {dashboard_url}. It Expires after 2 hours. Don't worry you can generate another one.")
        elif action == "error":
            # Handle error logic here
            return AIMessageResponse(
                message='None'
            )
        else:
            return AIMessageResponse(
                message=f"Unknown action: {action}. Please say the introductory message {self.intro_message()}"
            )

    def intro_message(self) -> str:
        return """
        Welcome! Here are the things you can do with this assistant:
        
            1. Link an account
            2. Remove an account
            3. Chat with your transaction data
            4. Resync your account data
            5. Subscribe to the Platform
            6. Cancel Your subscription
            7. You can Request a Link to your Finance Dashboard

       You don't need to select an Option, Just Ask the Assistant what you want
        
        """

    def random_string(self, length=8):
        letters = string.ascii_letters
        return ''.join(random.choice(letters) for _ in range(length))

    async def initialize_state(self, ownerid: str, message: str) -> StateResponse:
        """
        Initialize the state for a user.
        """

        user = self.auth_service.get_mobile_user(ownerid)

        if user:
            return StateResponse(
                state="onboarded",
                onboarded=True,
                message="Welcome back! How can I assist you today?"
            )

        state = {}
        user_data = await self.fetch_user_state_from_prompt(ownerid, message)
        name = user_data.get('name', None)
        email = user_data.get('email', None)
        print(name, email)
        if name and not email:
            state = {
                "mobile": ownerid,
                "state": "ask_email",
                "data": f"name:{name}"
            }
            message = self.generate_response(
                context="onboarding",
                prompt=f"This User does have name and the name is {name} and doesn't have an email, Kindly ask the user to input their email"
            )
        elif email and not name:
            state = {
                "mobile": ownerid,
                "state": "ask_name",
                "data": f"email:{email}"
            }
            message = self.generate_response(
                context="onboarding",
                prompt=f"This User does have an email and the email is {email} but doesn't have a name, Kindly ask the user to input their name"
            )
        elif not name and not email:
            state = {
                "mobile": ownerid,
                "state": "ask_name",
                "data": ""
            }
            message = self.generate_response(
                context="onboarding",
                prompt="This User doesn't have name and an email, Kindly ask the user to input their name and email"
            )
        else:
            state = {
                "mobile": ownerid,
                "state": "onboarded",
                "data": f"name:{name}, email:{email}"
            }
            user_create = UserCreate(
                email=email,
                firstname=name.split()[0] if name else "",
                lastname=name.split()[1] if len(name.split()) > 1 else "",
                mobile=ownerid,
                password='default_password'  # You might want to handle password setting differently
            )
            current_user = self.auth_service.get_user_by_email(email=email)
            if current_user:
                return StateResponse(
                    state="onboarded",
                    onboarded=True,
                    message=self.generate_response(
                        context="onboarding",
                        prompt="This Email already exists, Kindly use another email or login to your account"
                    )
                )

            user = self.auth_service.register_user(user_create=user_create)
            return StateResponse(
                state="onboarded",
                onboarded=True,
                message=self.generate_response(
                    context="onboarding",
                    prompt="This User has signed up successfully, Welcome to Usekudi! How can I assist you today?"
                )
            )
        await set_cache(f"{ownerid}_state", json.dumps(state), 10000)
        return StateResponse(
            state=state['state'],
            onboarded=False,
            message=message
        )

    async def fetch_user_state_from_prompt(self, ownerid: str, prompt: str) -> dict:

        state_data = await get_cache(f"{ownerid}_state")
        state = json.loads(state_data) if state_data else None
        message = prompt.strip()
        if state and state.get("data") != "":
            message += state.get("data")
        response_schemas = [
            ResponseSchema(name="name", description="The user's name, or empty string if missing"),
            ResponseSchema(name="email", description="The user's email, or empty string if missing"),
        ]
        output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        format_instructions = output_parser.get_format_instructions()

        # write a langchain to extract details from the message in email and string
        prompt_template = PromptTemplate(
            input_variables=['user_input'],
            partial_variables={"format_instructions": format_instructions},
            template="""
        You are a financial assistant bot on WhatsApp, Telegram and many chat channels.
            Given this user input: "{user_input}", extract the user's name and email if they are not already set.
            If the user has not provided their name and email, return exactly this format {{ 'name':'', 'email':'' }}
            If the user has provided their name and email, return exactly this format {{'name':str, 'email': str}}.
            return only JSON in this exact format
            {format_instructions}
        """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o", max_tokens=1000, openai_api_key=self.open_ai_api_key)
        chain = LLMChain(llm=llm, prompt=prompt_template)
        response = chain.run({"user_input": message})
        response_data = output_parser.parse(response)
        name = ""
        email = ""
        mobile = ownerid
        if isinstance(response_data, dict):
            name = response_data.get("name")
            email = response_data.get("email")
        return {
            "name": name,
            "email": email,
            "mobile": mobile
        }

    def generate_response(self, context: str, prompt: str) -> str:
        # Placeholder for actual AI response generation logic
        prompt_template = PromptTemplate(
            input_variables=["category_context", "narration", "txn_type"],
            template="""
                    You are a friendly financial assistant bot.  
                    Your job is to turn a short system message idea into a clear, polite, and helpful message for the user.  

                    Category: {context}  
                    Message idea: "{prompt}"  

                    Guidelines:  
                    - Use a friendly and conversational tone.  
                    - Keep it concise.  
                    - Make it feel personal and professional.  
                    - Adapt the style for WhatsApp or chat.  
                    
                    Special case: If the message idea says no data was found or something went wrong, kindly let the user know and politely suggest generating
                     a webpage so they can open the UI and check for themselves.
                     
                    Now rewrite the message idea into the final user-facing message:
        """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, openai_api_key=self.open_ai_api_key)
        chain = LLMChain(llm=llm, prompt=prompt_template)
        response = chain.run({
            "context": context,
            "prompt": prompt
        })
        return response.strip()

    def get_model_info(self) -> str:
        # Placeholder for actual model info retrieval logic
        return None

    def categorize_transaction(self, transaction: Transaction, categories: list[Category]) -> int:
        # Placeholder for actual transaction categorization logic
        # This would typically involve calling an AI model to classify the transaction
        category_context = "\n".join([
            f"[{cat.id}] {cat.name}: {cat.description}" for cat in categories])

        prompt_template = PromptTemplate(
            input_variables=["category_context", "narration", "txn_type"],
            template="""
        You are a financial assistant classifying Nigerian bank transactions.
        Below are possible categories with their ID and descriptions:   
        {category_context}
        Given the narration: "{narration}" and the Transaction Type {txn_type}, return ONLY the category ID (a number) that best matches it.
        Do not explain. Just return the ID.
        """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o", max_tokens=1000, openai_api_key=self.open_ai_api_key)
        chain = LLMChain(llm=llm, prompt=prompt_template)
        narration = transaction.description
        response = chain.run({
            "category_context": category_context,
            "narration": narration,
            "txn_type": transaction.transaction_type
        })
        print(f"AI Response: {response}, {transaction.description}, {transaction.id}")
        category_id = int(response.strip())
        return category_id

    def classify_intent(self, intent: str, user: User) -> dict:
        # Placeholder for actual intent classification logic
        # This would typically involve calling an AI model to classify the intent
        response_schemas = [
            ResponseSchema(name="action", description="The action to be taken based on the intent")
        ]
        chat_history = RedisChatMessageHistory(
            session_id=f"user_{user.id}",  # This is the actual key in Redis
            url=self.redis
        )
        memory = ConversationBufferMemory(
            chat_memory=chat_history,
            memory_key="history"
        )
        output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
        format_instructions = output_parser.get_format_instructions()
        prompt_template = PromptTemplate(
            input_variables=["intent"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                    You are a personal financial assistant classifying intents.  
                    Use the conversation history and user input to decide:  
                    
                    Conversation history:  
                    {history}  
                    
                    Intent: {intent}  
                    
                    Classify the intent into one of these categories:  
                    
                    - Account Linking: Linking or connecting new bank accounts or payment accounts.  
                    - Transaction: Any request related to viewing transaction data — including summaries, breakdowns, spending analysis, filtering by time or category, or getting insights over time.  
                    - Transaction Add: Adding or recording a new transaction or expense.  
                    - Dashboard Request: Requesting to generate, open, or share a webpage/dashboard to review transactions or financial data.  
                    - Account: Managing account details, balances, or account-specific information.  
                    - User: User profile or settings management.  
                    - Account Resync: Re-syncing or refreshing accounts to get latest data.  
                    - Error: Reporting or handling errors/exceptions.  
                    - Show Features: Request to list all available features of the app.  
                    - Other: Anything that does not fit into the above.  
                    
                    Return the classification in this JSON format only:  
                    
                    If Account Linking → {{"action": "link_account"}}  
                    If Transaction → {{"action": "transaction"}}  
                    If Transaction Add → {{"action": "transaction_add"}}  
                    If Dashboard Request → {{"action": "dashboard_request"}}  
                    If Account → {{"action": "account"}}  
                    If User → {{"action": "user"}}  
                    If Account Resync → {{"action": "account_resync"}}  
                    If Error → {{"action": "error"}}  
                    If Show Features → {{"action": "show_features"}}  
                    If Other → {{"action": "other"}}  
                    
                    Do not explain.  
                    Return only JSON in exactly this format: {format_instructions}
"
        """)
        llm = ChatOpenAI(temperature=0, model="gpt-4o", max_tokens=1000, openai_api_key=self.open_ai_api_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, memory=memory)
        response = chain.run({"intent": intent})
        response_data = output_parser.parse(response)
        return response_data if isinstance(response_data, dict) else {"action": "other"}
