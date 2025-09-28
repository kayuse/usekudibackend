from datetime import datetime, timedelta

import pdfplumber
from dotenv import load_dotenv
from langchain.chains.llm import LLMChain
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI
from posthog.ai.openai import OpenAI
from sqlalchemy.orm import Session

from app.data.session import Statement, BankData, FinancialProfileDataIn
from app.data.transaction_insight import Insights, Insight, TransactionSWOTInsight, SavingsPotentials, SavingsPotential
from app.models.session import Session as SessionModel, SessionInsight, SessionSwot, SessionSavingsPotential
from app.models.account import Bank
import os

from app.models.session import SessionTransaction

load_dotenv(override=True)


class SessionAIService:

    def __init__(self, session: Session):
        self.db = session
        self.ai_key = os.environ.get("CHAT_GPT_KEY")

    def read_pdf_statement(self, path) -> Statement:
        print("Reading PDF statement from {}".format(path))
        parser = PydanticOutputParser(pydantic_object=Statement)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a financial assistant. Extract structured fields from a bank statement."),
            ("user", "Here is some text from a bank statement:\n\n{statement_text}\n\n{format_instructions}")
        ])
        full_text = ''
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

        formatted_prompt = prompt.format_messages(
            statement_text=full_text,
            format_instructions=parser.get_format_instructions()
        )
        llm = ChatOpenAI(model='gpt-4.1-mini', temperature=0, api_key=self.ai_key)
        result = llm.invoke(formatted_prompt)
        parsed_data: Statement = parser.parse(result.content)
        return parsed_data

    def get_bank_id(self, bank_name: str) -> int:
        banks = self.db.query(Bank).filter(Bank.active == True).all()
        parser = PydanticOutputParser(pydantic_object=BankData)
        template = """
            You are given a target bank name and a list of banks with their IDs.
            Bank name: {bank_name}
            
            Bank list:
            {bank_list}
            
            Return the name and the ID of the bank that matches the bank name. 
            Pick the most likely match.  
            If no match is found, return "None" as name and 0 as id.
            
            {format_instructions}
        """

        prompt = PromptTemplate.from_template(template)
        final_prompt = prompt.format(
            bank_name=bank_name, bank_list=banks,
            format_instructions=parser.get_format_instructions()
        )
        llm = ChatOpenAI(model='gpt-4o', temperature=0, api_key=self.ai_key)
        result = llm.invoke(final_prompt)
        data: BankData = parser.parse(result.content)

        bank_id = data.bank_id
        print("Bank ID: {}".format(bank_id))
        return bank_id

    def generate_insights(self, session: SessionModel, transactions: list[type[SessionTransaction]],
                          data_in: FinancialProfileDataIn):

        documents = []
        for transaction in transactions:
            if transaction.category_id is None:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.account.currency} {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name},"
                f"Category Description: {transaction.category.description}")
            documents.append(transaction_data)

        parser = PydanticOutputParser(pydantic_object=Insights)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["transaction_documents"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                           You are a financial assistant that analyzes transaction data. 
                           Your goal is to provide clear, personalized insights from a list of transactions. 
                           Always be concise, use simple language, and make the insights actionable.
                           
                           Here is the customer's Income/Outflow Profile
                        
                           Income: {income}
                           Outflow: {outflow}
                           Closing Balance: {closing_balance}
                           Net Income: {net_income}
                        
                           Here is the customer's financial Risk profile data
                           
                           Liquidity Risk: {liquidity_risk}
                           Concentration Risk: {concentration_risk}
                           Expense Risk: {expense_risk}
                           Volatility Risk: {volatility_risk}
                           
                           Here is the Customers Spending Profile
                           
                           Spending Ratio: {spending_ratio}
                           Savings Ratio: {savings_ratio}
                           Budget Conscious Ratio: {budget_ratio}
                           
                           
                           Here is a list of transactions:
    
                           {transaction_documents}
    
                           Based on this data, generate insights including but not limited to:
                           - Total income (credits) and total expenses (debits)
                           - Biggest spending categories or merchants
                           - Any unusual or large transactions
                           - Spending vs saving balance
                           - Suggestions for better financial health
    
                           You may also add any other useful observations, such as:
                           - Spending trends over time
                           - Recurring payments or subscriptions
                           - Changes compared to previous periods
                           - Savings opportunities
                           - Risky or suspicious transactions
    
                           Important output rules:
                           - Each insight must be a JSON object with the following fields:
                             - title (short headline of the insight)
                             - description (short explanation in simple language)
                             - priority (one of: "low", "medium", "high")
                             - type (one of: "recommendation", "alert", "forecast", "spending trend")
                             - action (nullable string, an optional next step for the user, can be null)
                           - Do not add explanations, comments, or any text outside the JSON.
                           - Use only the same currency shown in the transaction documents (e.g., ₦ for Naira).
                           - Do not convert to USD ($) or any other currency.
                           - Return the result strictly as a JSON list of insights using this format:
                           {format_instructions}
                           Each element MUST be an object with exactly these keys: 
                               - "title" (string)
                               - "description" (string)
                               - "priority" (one of "low", "medium", "high")
                               - "type" (one of "recommendation", "alert", "forecast", "spending trend")
                               - "action" (string or null)
                   """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"transaction_documents": documents,
                                 "income": data_in.income_flow.income, "outflow": data_in.income_flow.outflow,
                                 "closing_balance": data_in.income_flow.closing_balance,
                                 "net_income": data_in.income_flow.net_income,
                                 "liquidity_risk": data_in.risk.liquidity_risk,
                                 "concentration_risk": data_in.risk.concentration_risk,
                                 "expense_risk": data_in.risk.expense_risk,
                                 "volatility_risk": data_in.risk.volatility_risk,
                                 "spending_ratio": data_in.spending_profile.spending_ratio,
                                 "savings_ratio": data_in.spending_profile.savings_ratio,
                                 "budget_ratio": data_in.spending_profile.budget_conscious})
        print(response['text'].root)
        data: list[Insight] = response["text"].root

        self.db.query(SessionInsight).filter(SessionInsight.session_id == session.id).update(
            {"is_latest": False})
        self.db.commit()

        insights = [SessionInsight(session_id=session.id, title=record.title, priority=record.priority,
                                   insight=record.description, insight_type=record.type,
                                   is_latest=True) for record in data]
        self.db.bulk_save_objects(insights)
        self.db.commit()
        return data

    def generate_swot(self, session: SessionModel, transactions: list[type[SessionTransaction]],
                      data_in: FinancialProfileDataIn):

        documents = []
        for transaction in transactions:
            if transaction.category_id is None:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.account.currency} {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name},"
                f"Category Description: {transaction.category.description}")
            documents.append(transaction_data)

        parser = PydanticOutputParser(pydantic_object=TransactionSWOTInsight)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["transaction_documents"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                                                       You are a financial assistant that analyzes transaction and financial profile data.
                            Your goal is to provide a clear SWOT analysis (Strengths, Weaknesses, Opportunities, Threats) for the customer.
                            Always be concise, use simple language, and make the insights actionable.
                            
                            Here is the customer's Income/Outflow Profile:
                            
                            Income: {income}  
                            Outflow: {outflow}  
                            Closing Balance: {closing_balance}  
                            Net Income: {net_income}  
                            
                            
                            Here is the customer's Financial Risk Profile:
                            
                            Liquidity Risk: {liquidity_risk}  
                            Concentration Risk: {concentration_risk}  
                            Expense Risk: {expense_risk}  
                            Volatility Risk: {volatility_risk}  
                            
                            
                            Here is the Customer’s Spending Profile:
                            
                            Spending Ratio: {spending_ratio}  
                            Savings Ratio: {savings_ratio}  
                            Budget Conscious Ratio: {budget_ratio}  
                            
                            
                            Here is a list of transactions:
                            
                            {transaction_documents}
                            
                            Your Task
                            
                            Using all this data, generate a SWOT analysis that highlights:
                            
                            Strengths → positive patterns in income, savings, risk control, or spending discipline
                            
                            Weaknesses → issues like overspending, high expense growth, or risky behaviors
                            
                            Opportunities → areas to improve, diversify income, or save more
                            
                            Threats → risks from volatility, liquidity issues, or unusual/suspicious transactions
                            
                            Important Output Rules
                            
                            Output must strictly follow this JSON structure:
                            
                            {
                              "strengths": ["string", "string", "..."],
                              "weaknesses": ["string", "string", "..."],
                              "opportunities": ["string", "string", "..."],
                              "threats": ["string", "string", "..."]
                            }
                            
                            
                            Do not include any comments, explanations, or extra text outside the JSON.
                            
                            Use simple, clear sentences.
                            
                            Keep each point short and actionable.
                   """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"transaction_documents": documents,
                                 "income": data_in.income_flow.income, "outflow": data_in.income_flow.outflow,
                                 "closing_balance": data_in.income_flow.closing_balance,
                                 "net_income": data_in.income_flow.net_income,
                                 "liquidity_risk": data_in.risk.liquidity_risk,
                                 "concentration_risk": data_in.risk.concentration_risk,
                                 "expense_risk": data_in.risk.expense_risk,
                                 "volatility_risk": data_in.risk.volatility_risk,
                                 "spending_ratio": data_in.spending_profile.spending_ratio,
                                 "savings_ratio": data_in.spending_profile.savings_ratio,
                                 "budget_ratio": data_in.spending_profile.budget_conscious})
        print(response['text'].root)
        data: TransactionSWOTInsight = response["text"].root

        s_data = [SessionSwot(session_id=session.id, analysis=strength, swot_type='strength') for strength in
                  data.strengths]
        w_data = [SessionSwot(session_id=session.id, analysis=w, swot_type='weakness') for w in data.weaknesses]
        o_data = [SessionSwot(session_id=session.id, analysis=w, swot_type='opportunities') for w in data.opportunities]
        t_data = [SessionSwot(session_id=session.id, analysis=w, swot_type='threats') for w in data.threats]

        self.db.bulk_save_objects(s_data)
        self.db.bulk_save_objects(w_data)
        self.db.bulk_save_objects(o_data)
        self.db.bulk_save_objects(t_data)

        self.db.commit()

        return data

    def generate_savings_potential(self, session: SessionModel, transactions: list[type[SessionTransaction]],
                                   data_in: FinancialProfileDataIn):

        documents = []
        for transaction in transactions:
            if transaction.category_id is None:
                continue

            transaction_data = (
                f"Transaction ID : {transaction.transaction_id}, Date: {transaction.date}, Transaction Type: {transaction.transaction_type}, Amount: {transaction.account.currency} {transaction.amount}, "
                f"Description: {transaction.description}, Category Name: {transaction.category.name},"
                f"Category Description: {transaction.category.description}")
            documents.append(transaction_data)

        parser = PydanticOutputParser(pydantic_object=SavingsPotentials)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["transaction_documents"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                              You are a financial assistant that analyzes transaction data. 
                              Your goal is to provide clear, personalized insights from a list of transactions. 
                              Always be concise, use simple language, and make the insights actionable.

                              Here is the customer's Income/Outflow Profile

                              Income: {income}
                              Outflow: {outflow}
                              Closing Balance: {closing_balance}
                              Net Income: {net_income}

                              Here is the customer's financial Risk profile data

                              Liquidity Risk: {liquidity_risk}
                              Concentration Risk: {concentration_risk}
                              Expense Risk: {expense_risk}
                              Volatility Risk: {volatility_risk}

                              Here is the Customers Spending Profile

                              Spending Ratio: {spending_ratio}
                              Savings Ratio: {savings_ratio}
                              Budget Conscious Ratio: {budget_ratio}


                              Here is a list of transactions:

                              {transaction_documents}

                              Based on this data, generate savings potential including but not limited to:
                              - Total income (credits) and total expenses (debits)
                              - Biggest spending categories or merchants
                              - Any unusual or large transactions
                              - Spending vs saving balance
                              - Suggestions for better financial health

                              You may also add any other useful observations, such as:
                              - Spending trends over time
                              - Recurring payments or subscriptions
                              - Changes compared to previous periods
                              - Savings opportunities
                              - Risky or suspicious transactions
                              - Risk Scores
                              - Customer Spending Profiles

                              Important output rules:
                              - Each savings potential must be a JSON object with the following fields:
                                - potential (short headline of the actual potential to be embarked upon)
                                - amount (the amount expected to be saved if potential is followed through)
                                
                              {format_instructions}
                              Each element MUST be an object with exactly these keys: 
                                  - "title" (string)
                                  - "amount" (float)
                      """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"transaction_documents": documents,
                                 "income": data_in.income_flow.income, "outflow": data_in.income_flow.outflow,
                                 "closing_balance": data_in.income_flow.closing_balance,
                                 "net_income": data_in.income_flow.net_income,
                                 "liquidity_risk": data_in.risk.liquidity_risk,
                                 "concentration_risk": data_in.risk.concentration_risk,
                                 "expense_risk": data_in.risk.expense_risk,
                                 "volatility_risk": data_in.risk.volatility_risk,
                                 "spending_ratio": data_in.spending_profile.spending_ratio,
                                 "savings_ratio": data_in.spending_profile.savings_ratio,
                                 "budget_ratio": data_in.spending_profile.budget_conscious})
        print(response['text'].root)
        data: list[SavingsPotential] = response["text"].root

        potentials = [SessionSavingsPotential(session_id=session.id, potential=record.potential, amount=record.amount)
                      for record in data]
        self.db.bulk_save_objects(potentials)
        self.db.commit()
        return data
