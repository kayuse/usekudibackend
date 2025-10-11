import asyncio
from typing import Union

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse
from dotenv import load_dotenv

from .services.session_chat_service import SessionChatService
from .util.redis import redis

load_dotenv(override=True)
from .database.index import engine, get_db
from .routers.index import router
from .routers.auth import router as auth_router
from .routers.account import router as account_router
from .routers.transaction import router as transaction_router
from .routers.message import router as message_router
from .routers.budget import router as budget_router
from .routers.dashboard import router as dashboard_router
from .routers.session import router as session_router
from .models import verification
from .util.errors import CustomError
from fastapi.middleware.cors import CORSMiddleware


verification.Base.metadata.create_all(bind=engine)
# Load environment variables from .env file
app = FastAPI()

app.include_router(router)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(transaction_router)
app.include_router(message_router)
app.include_router(budget_router)
app.include_router(dashboard_router)
app.include_router(session_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
connected_clients = {}


@app.exception_handler(CustomError)
async def custom_error_handler(request: Request, exc: CustomError):
    return JSONResponse(
        status_code=418,  # Example status code
        content={"message": f"Custom Error: {exc.name}"},
    )


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


async def process_chat(session_id: str, socket_id: str, text: str):
    db = next(get_db())
    print("Processing Chat {}".format(session_id))
    chat_service = SessionChatService(db)
    response = chat_service.process(session_id, text)
    print("Processing Chat {}".format(session_id))
    await send_to_user(socket_id, response)
    return f"Processed message for {socket_id}: {text}"

async def send_to_user(socket_id: str, message: str):
    websocket = connected_clients.get(socket_id)
    if websocket:
        await websocket.send_text(message)

@app.websocket("/chat/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session_socket = str(id(websocket))
    connected_clients[session_socket] = websocket
    try:
        while True:
            user_message = await websocket.receive_text()
            print(user_message)
            asyncio.create_task(process_chat(session_id, session_socket, user_message))
    except WebSocketDisconnect:
        print("User disconnected")
