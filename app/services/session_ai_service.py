import asyncio
import json
import re
import tempfile
from typing import Optional

import fitz
import pdfplumber
from dotenv import load_dotenv
from langchain.chains.llm import LLMChain
import marker
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI
from openai import OpenAI, AsyncOpenAI
from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFException
from pdfplumber.utils.exceptions import PdfminerException
from sqlalchemy.orm import Session
import pikepdf
from app.data.session import CurrencyCodeData, CurrencyOut, Statement, BankData, FinancialProfileDataIn, SessionTransactionOut
from app.data.transaction_insight import Insights, Insight, TransactionSWOTInsight, SavingsPotentials, SavingsPotential, \
    OverallAssessment
from app.models.session import Session as SessionModel, SessionInsight, SessionSwot, SessionSavingsPotential, \
    SessionFile
from app.models.account import Bank, Currency
import os

from app.models.session import SessionTransaction

load_dotenv(override=True)


class SessionAIService:

    def __init__(self, session: Session):
        self.db = session
        self.ai_key = os.environ.get("CHAT_GPT_KEY")
        self.client = AsyncOpenAI(api_key=self.ai_key)

    def is_encrypted(self):
        return self.ai_key is not None

    async def process_page(self, i, text, parser, prompt, llm):
        formatted_prompt = prompt.format_messages(
            statement_text=text,
            format_instructions=parser.get_format_instructions()
        )
        print("Processing page {} with LLM {}".format(i, text))
        result = await llm.ainvoke(formatted_prompt)
        clean_output = re.sub(r'(\d+),(\d+)', r'\1\2', result.content)
        parsed_page: Statement = parser.parse(clean_output)
        return i, parsed_page

    def unlock_pdf(self, file: SessionFile, password: str) -> bool:
        try:
            with pdfplumber.open(file.file_path, password=password) as pdf:
                # Successfully opened
                file.password = password
                self.db.commit()
                self.db.refresh(file)
                print("Unlocked {}".format(file.id))
                return True
        except PDFPasswordIncorrect:
            return False
        except PdfminerException:
            return False
        except Exception as e:
            # handle other errors (file missing/corrupt)
            print(e)
            raise e

    @staticmethod
    def is_pdf_locked(file: SessionFile):
        try:
            # Try opening with given password (empty string if none)
            with pdfplumber.open(file.file_path, password="") as pdf:
                # If no exception, it's unlocked
                return False
        except PDFPasswordIncorrect:
            return True
        except PdfminerException as e:
            return True

    async def read_pdf_statement(self, file: SessionFile) -> Statement | None:
        print("Reading PDF statement from {}".format(file.file_path))
        parser = PydanticOutputParser(pydantic_object=Statement)
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a financial assistant. Extract structured fields from a bank statement. "
             "Rules:\n"
             "- All float fields must be plain numbers (e.g. 28989.95) without commas, spaces, or currency symbols.\n"
             "- All date fields must strictly follow the format YYYY-MM-DD (ISO 8601).\n"
             "- Only return valid JSON as described in the format instructions."),
            ("user", "Here is some text from a bank statement:\n\n{statement_text}\n\n{format_instructions}")
        ])
        final_statement = Statement(transactions=[])
        tasks = []
        if SessionAIService.is_pdf_locked(file):
            print("PDF is locked, Trying to Unlock PDF")
            for i in range(1, 10000000):
                # replace this with whatever work you need to do per number
                result = self.unlock_pdf(file, str(i))
                if result:
                    break

        if SessionAIService.is_pdf_locked(file):
            return None

        with pdfplumber.open(file.file_path) as pdf:
            last_page_statement = None
            llm = ChatOpenAI(model='gpt-4.1-mini', temperature=0, api_key=self.ai_key)
            for i, page in enumerate(pdf.pages, 1):
                print("Processing page {}".format(i))
                text = page.extract_text()

                clean_text = re.sub(r'([A-Za-z])\1', r'\1', text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                tasks.append(self.process_page(i, clean_text, parser, prompt, llm))

            results = await asyncio.gather(*tasks)

            for i, parsed_page in sorted(results, key=lambda x: x[0]):
                if i == 1:
                    final_statement.accountName = parsed_page.accountName
                    final_statement.accountNumber = parsed_page.accountNumber
                    final_statement.accountCurrency = parsed_page.accountCurrency
                    final_statement.accountBalance = parsed_page.accountBalance
                final_statement.transactions.extend(parsed_page.transactions)
                last_page_statement = parsed_page

                if last_page_statement and last_page_statement.accountBalance and final_statement.accountBalance is None:
                    final_statement.accountBalance = last_page_statement.accountBalance
            print("Done processing page {}".format(i))

        return final_statement

    def get_currency_data(self, currency_name: str) -> Optional[CurrencyCodeData]:
        currencies = self.db.query(Currency).all()
        currency_list = [CurrencyOut.model_validate(c) for c in currencies]
        parser = PydanticOutputParser(pydantic_object=CurrencyCodeData)
        template = """
            You are given a target currency and a list of currencies with their codes.
            Currency name: {currency_name}

            Currency list:
            {currency_list}

            Return the code and the ID of the currency that matches the currency name.
            Pick the most likely match.
            If no match is found, return "None" as code and 0 as id.
            Format your response as JSON with the following structure:
            {format_instructions}
        """

        prompt = PromptTemplate.from_template(template)
        final_prompt = prompt.format(
            currency_name=currency_name, currency_list=currency_list,
            format_instructions=parser.get_format_instructions()
        )
        llm = ChatOpenAI(model='gpt-4o-mini', temperature=0, api_key=self.ai_key)
        result = llm.invoke(final_prompt)
        data: CurrencyCodeData = parser.parse(result.content)

        print("Currency Data: {}".format(data))
        return data
    
    
    async def read_pdf_directly(self, file) -> Optional[Statement]:
        # 🔐 Try brute-forcing the password if locked
        if self.is_pdf_locked(file) and file.password is None:
            print("PDF is locked. Attempting to unlock...")
            should_break = False
            for length in range(1, 10):  # from 1-digit up to 9-digits
                for i in range(10 ** length):
                    s = str(i).zfill(length)

                    if self.unlock_pdf(file, str(s)):
                        print(f"Unlocked PDF with password {i}")
                        should_break = True
                        break

                if should_break:
                    break

        # If still locked, abort
        if self.is_pdf_locked(file) and file.password is None:
            print("Failed to unlock PDF.")
            return None
        tasks = []
        final_statement = Statement(transactions=[])
        parser = PydanticOutputParser(pydantic_object=Statement)
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a financial assistant. Extract structured fields from a bank statement. "
             "Rules:\n"
             "- All float fields must be plain numbers (e.g. 28989.95) without commas, spaces, or currency symbols.\n"
             "- All date fields must strictly follow the format YYYY-MM-DD (ISO 8601).\n"
             "- Only return valid JSON as described in the format instructions."),
            ("user", "Here is some text from a bank statement:\n\n{statement_text}\n\n{format_instructions}")
        ])
        # Create a decrypted temp copy
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with pikepdf.open(file.file_path, password=(file.password or "")) as pdf:
                pdf.save(tmp_path)

            llm = ChatOpenAI(model='gpt-4.1-mini', temperature=0, api_key=self.ai_key)
            doc = fitz.open(tmp_path)

            print("Number of pages:", len(doc))

            for page in doc:
                print("Processing page {}".format(page.number + 1))
                text = page.get_text('text')
                print(text)

                clean_text = re.sub(r'([A-Za-z])\1', r'\1', text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                tasks.append(self.process_page(page.number + 1, clean_text, parser, prompt, llm))

            results = await asyncio.gather(*tasks)

            for i, parsed_page in sorted(results, key=lambda x: x[0]):
                if i == 1:
                    final_statement.accountName = parsed_page.accountName
                    final_statement.accountNumber = parsed_page.accountNumber
                    final_statement.accountCurrency = parsed_page.accountCurrency
                    final_statement.accountBalance = parsed_page.accountBalance
                final_statement.transactions.extend(parsed_page.transactions)
                last_page_statement = parsed_page

                if last_page_statement and last_page_statement.accountBalance and final_statement.accountBalance is None:
                    final_statement.accountBalance = last_page_statement.accountBalance
            print("Done processing page {}".format(i))
            doc.close()
            return final_statement

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

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
        llm = ChatOpenAI(model='gpt-4o-mini', temperature=0, api_key=self.ai_key)
        result = llm.invoke(final_prompt)
        data: BankData = parser.parse(result.content)

        bank_id = data.bank_id
        print("Bank ID: {}".format(bank_id))
        return bank_id

    def generate_insights(self, session: SessionModel, data_in: FinancialProfileDataIn):

        parser = PydanticOutputParser(pydantic_object=Insights)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["inflow", "outflow", "closing_balance", "liquidity_risk", "concentration_risk",
                             "expense_risk", "volatility_risk", "spending_ratio", "savings_ratio", "budget_ratio",
                             "income_categories", "spending_categories"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                        You are a concise financial analyst for individual customers. 
                        Use the input data to produce a focused, predictive, and actionable 360° overview.
                         Prioritize facts, numbers, and short prescriptive recommendations. 
                         Avoid repeating generic risk buzzwords unless you provide a specific implication and an action.
                        
                        INPUT:
                        Inflow: {inflow}
                        Outflow: {outflow}
                        Closing Balance: {closing_balance}
                        Net Income: {net_income}
                        
                        Liquidity Risk: {liquidity_risk}
                        Concentration Risk: {concentration_risk}
                        Expense Risk: {expense_risk}
                        Volatility Risk: {volatility_risk}
                        
                        Spending Ratio: {spending_ratio}
                        Savings Ratio: {savings_ratio}
                        Budget Conscious Ratio: {budget_ratio}
                        
                        Income Categories: {income_categories}
                        Spending Categories: {spending_categories}
                        
                        Additional (optional): include a short time series of past weekly or monthly totals if available:
                        
                        TASK:
                        Produce a compact set of insights that together form a 360° assessment. Each insight must be a single JSON object with keys: title, description, priority, type, action. Return a JSON array of insight objects (no text outside the array).
                        
                        Required content to include somewhere among the insights (at least once):
                        1. Net totals: clearly state Total Income and Total Expenses and Net Income using the input currency.
                        2. Biggest spending categories/merchants (top 3) with amounts.
                        3. Any unusual or one-off large transactions (flag > 3× median transaction or > X% of monthly income).
                        4. Spending vs Saving balance: current savings ratio and suggested safe target with numeric goal.
                        5. Cash runway: how many days/weeks of spending the closing balance covers (use average daily/weekly outflow).
                        6. Short-term forecast: a 1–3 month expense forecast (e.g., "Estimated monthly expense next month: ₦X ±Y%") using trend in provided historical_series or recent growth rate.
                        7. Top 2 high-impact recommendations (e.g., reduce X category by Y% to save ₦Z/month).
                        8. One alert if Expense Risk or Liquidity Risk is above your thresholds (explain concretely what that implies).
                        9. One actionable behavior change (automations, subscriptions to cancel, target emergency fund).
                        
                        FORMAT & STYLE RULES:
                        - Output MUST be a JSON array only. No extra text, no explanations.
                        - Each array element MUST be an object with exactly these keys:
                          - "title": short headline (max 6 words)
                          - "description": one or two sentences with numbers (use the same currency as input)
                          - "priority": one of "low", "medium", "high"
                          - "type": one of "recommendation", "alert", "forecast", "spending trend"
                          - "action": a short next step for the user or null
                        - Use exact numeric values where possible (e.g., "Cash runway: 18 days" or "Reduce food by 20% → save ₦4,500/month").
                        - If historical_series is empty, compute short-term forecast from recent growth rate; if growth rate is unstable use 3-week moving average.
                        - Do NOT repeat the same point across multiple insights; each insight must add unique value.
                        - Keep descriptions simple, direct, and actionable.
                        
                        END

                   """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({
            "inflow": data_in.income_flow.inflow, "outflow": data_in.income_flow.outflow,
            "closing_balance": data_in.income_flow.closing_balance,
            "net_income": data_in.income_flow.net_income,
            "liquidity_risk": data_in.risk.liquidity_risk,
            "concentration_risk": data_in.risk.concentration_risk,
            "expense_risk": data_in.risk.expense_risk,
            "volatility_risk": data_in.risk.volatility_risk,
            "income_categories": data_in.income_categories,
            "spending_categories": data_in.expense_categories,
            "spending_ratio": data_in.spending_profile.spending_ratio,
            "savings_ratio": data_in.spending_profile.savings_ratio,
            "budget_ratio": data_in.spending_profile.budget_conscious})

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

    def generate_swot(self, session: SessionModel,
                      data_in: FinancialProfileDataIn):

        parser = PydanticOutputParser(pydantic_object=TransactionSWOTInsight)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["inflow", "outflow", "closing_balance", "liquidity_risk", "concentration_risk",
                             "expense_risk", "volatility_risk", "spending_ratio", "income_categories",
                             "spending_categories", "savings_ratio", "budget_ratio"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                                You are a financial assistant that analyzes transaction and financial profile data.  
                    Your goal is to provide a clear SWOT analysis (Strengths, Weaknesses, Opportunities, Threats) for the customer.  
                    Always be concise, use simple language, and make the insights actionable.  
                    
                    Here is the customer's Income/Outflow Profile:
                    
                    Inflow: {inflow}  
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
                    
                    Here is the Customer's Income Categories Breakdown

                    {income_categories}
                          
                    Here is the Customer's Spending Categories Breakdown

                    {spending_categories} 
                    
                    Your Task  
                    
                    Using all this data, generate a SWOT analysis that highlights:  
                    
                    - Strengths → positive patterns in income, savings, risk control, or spending discipline  
                    - Weaknesses → issues like overspending, high expense growth, or risky behaviors  
                    - Opportunities → areas to improve, diversify income, or save more  
                    - Threats → risks from volatility, liquidity issues, or unusual/suspicious transactions  
                    
                    Important Output Rules:  
                    
                    - Output must strictly follow this JSON structure:  
                    
                      "strengths": ["string", "string", "..."],
                      "weaknesses": ["string", "string", "..."],
                      "opportunities": ["string", "string", "..."],
                      "threats": ["string", "string", "..."]
                    
                    - Do not include any comments, explanations, or extra text outside the JSON.  
                    - Always include all four keys, even if some arrays are empty.  
                    - Keep each point short, clear, and actionable. 
                   """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"inflow": data_in.income_flow.inflow, "outflow": data_in.income_flow.outflow,
                                 "closing_balance": data_in.income_flow.closing_balance,
                                 "net_income": data_in.income_flow.net_income,
                                 "liquidity_risk": data_in.risk.liquidity_risk,
                                 "concentration_risk": data_in.risk.concentration_risk,
                                 "expense_risk": data_in.risk.expense_risk,
                                 "volatility_risk": data_in.risk.volatility_risk,
                                 "income_categories": data_in.income_categories,
                                 "spending_categories": data_in.expense_categories,
                                 "spending_ratio": data_in.spending_profile.spending_ratio,
                                 "savings_ratio": data_in.spending_profile.savings_ratio,
                                 "budget_ratio": data_in.spending_profile.budget_conscious})

        data: TransactionSWOTInsight = response["text"]
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

    def generate_savings_potential(self, session: SessionModel,
                                   data_in: FinancialProfileDataIn):

        parser = PydanticOutputParser(pydantic_object=SavingsPotentials)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["inflow", "outflow", "closing_balance", "liquidity_risk", "concentration_risk",
                             "expense_risk", "volatility_risk", "spending_ratio", "savings_ratio", "budget_ratio",
                             "income_categories", "spending_categories"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                              You are a financial assistant that analyzes transaction data. 
                              Your goal is to provide clear, personalized insights from a list of transactions. 
                              Always be concise, use simple language, and make the insights actionable.

                              Here is the customer's Income/Outflow Profile

                              Inflow: {inflow}
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
                              
                              Here is the Customer's Income Categories Breakdown

                              {income_categories}
                          
                              Here is the Customer's Spending Categories Breakdown

                              {spending_categories} 

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
        response = chain.invoke({"inflow": data_in.income_flow.inflow, "outflow": data_in.income_flow.outflow,
                                 "closing_balance": data_in.income_flow.closing_balance,
                                 "net_income": data_in.income_flow.net_income,
                                 "liquidity_risk": data_in.risk.liquidity_risk,
                                 "concentration_risk": data_in.risk.concentration_risk,
                                 "expense_risk": data_in.risk.expense_risk,
                                 "income_categories": data_in.income_categories,
                                 "spending_categories": data_in.expense_categories,
                                 "volatility_risk": data_in.risk.volatility_risk,
                                 "spending_ratio": data_in.spending_profile.spending_ratio,
                                 "savings_ratio": data_in.spending_profile.savings_ratio,
                                 "budget_ratio": data_in.spending_profile.budget_conscious})

        data: list[SavingsPotential] = response["text"].root

        potentials = [SessionSavingsPotential(session_id=session.id, potential=record.potential, amount=record.amount)
                      for record in data]
        self.db.bulk_save_objects(potentials)
        self.db.commit()
        return data

    def get_overall_assessment(self, session: SessionModel, insights: list[Insight],
                               savings_potential: list[SessionSavingsPotential],
                               swot_insight: TransactionSWOTInsight, ):

        parser = PydanticOutputParser(pydantic_object=OverallAssessment)
        format_instructions = parser.get_format_instructions()

        prompt_template = PromptTemplate(
            input_variables=["insights", "swot", "savings_potential", "customer_type"],
            partial_variables={"format_instructions": format_instructions},
            template="""
                        You are a personal financial assistant providing a clear, insightful summary directly to the customer. 
                        Your role is to create an “Overall Assessment Analysis” — a personalized financial overview that feels 
                        like a professional yet friendly financial review. 
                        
                        You are NOT writing about the customer in the third person. 
                        Always speak directly to them using “you” and “your”.
                        
                        You are a financial analyst that produces holistic summaries of customers' financial behavior and health. 
                        You receive multiple analysis inputs (Insights, SWOT, Savings Potentials, Customer Type) and must create 
                        a single concise “Overall Assessment Analysis” — a 360° view of the customer’s financial profile. 
                        
                        Focus on synthesis, not repetition. 
                        Show clear reasoning, trends, and predictions in simple language that anyone can understand. 
                        Always sound professional, factual, and human.
                        
                        INPUT:
                        Customer Insights:
                        {insights}
                        
                        Customer SWOT Analysis:
                        {swot}
                        
                        Customer Savings Potentials:
                        {savings_potential}
                        
                        Customer Type:
                        {customer_type}
                        
                        TASK:
                        Using all the inputs above, produce an overall assessment that:
                        1. Summarizes the customer’s financial personality and key strengths/weaknesses.
                        2. Highlights noticeable patterns in spending, saving, and inflow stability.
                        3. Identifies changes compared to previous periods (if trends exist).
                        4. Describes risk posture (e.g., liquidity, expense, volatility) with brief implications.
                        5. Predicts possible near-term outcomes (e.g., improving stability, likely overspending, cash shortfall).
                        6. Mentions 1–2 actionable recommendations that align with the customer’s type (individual, business, church, NGO).
                        7. Ends with an encouraging or advisory tone, not just a report.
                        
                        OUTPUT RULES:
                        - Return ONLY a single JSON object (no arrays, no extra text).
                        - The object MUST have exactly these two keys:
                          - "title": (short, headline-style summary of the assessment; e.g. "Stable but Overspending in Essentials")
                          - "assessment": (1–3 paragraphs summarizing the customer’s financial outlook and actionable insights)
                        - Do NOT include savings_potentials or any other fields.
                        - Keep the tone analytical but empathetic, with clear insight into future behavior or risks.
                        - Use consistent currency and avoid technical jargon.
                        - Be specific, not generic (“Spending increased by 12% over 3 months” instead of “Spending went up”).
                        - Never include formatting, markdown, or additional commentary.
                        
                        {format_instructions}

                     """)

        llm = ChatOpenAI(temperature=0, model="gpt-4o-mini", max_tokens=1000, api_key=self.ai_key)
        chain = LLMChain(llm=llm, prompt=prompt_template, output_parser=parser)
        response = chain.invoke({"insights": insights, "swot": swot_insight,
                                 "savings_potential": savings_potential,
                                 "customer_type": session.customer_type})

        data = response["text"]

        session.overall_assessment_title = data.title
        session.overall_assessment = data.assessment

        self.db.commit()
        return data
