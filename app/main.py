from typing import Union

from fastapi import Depends, FastAPI, Request
from starlette.responses import JSONResponse
from dotenv import load_dotenv
load_dotenv() 

from .database.index import engine
from .routers.index import router
from .routers.auth import router as auth_router
from .routers.account import router as account_router
from .models import verification
from .util.errors import CustomError
from fastapi.middleware.cors import CORSMiddleware


verification.Base.metadata.create_all(bind=engine)
 # Load environment variables from .env file
app = FastAPI()

app.include_router(router)
app.include_router(auth_router)
app.include_router(account_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
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
