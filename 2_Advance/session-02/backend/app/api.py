import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from app.runtime import run_turn
from app.validation import validate_submission

api = FastAPI(title="A2UI Demo")
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173","http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

class ChatRequest(BaseModel):
    session_id: str=Field(min_length=3,max_length=100)
    message: str=Field(min_length=1,max_length=4000)

class SubmitRequest(BaseModel):
    session_id: str=Field(min_length=3,max_length=100)
    values: dict


@api.post("/api/chat")
async def chat(request: ChatRequest):
    return await run_turn(request.session_id,request.message)


@api.post("/api/submit")
async def submit(request: SubmitRequest):

    print(json.dumps(request.values, indent=2))
    return {
        "ok": True,
        "message": "Submission received successfully.",
        "submitted": request.values
    }