
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any
import traceback

from app.rag import answer_question

app = FastAPI(
    title="DarGlobal & Wasalt Real Estate AI Assistant",
    description="AI-powered real estate assistant using RAG.",
    version="1.0.0"
)


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=1000
    )


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict[str, Any]]


@app.get("/")
def root():
    return {
        "message": "DarGlobal & Wasalt AI Assistant API",
        "status": "running",
        "documentation": "/docs"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "DarGlobal & Wasalt AI Assistant",
        "version": "1.0.0"
    }


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    try:
        result = answer_question(payload.question)

        if not isinstance(result, dict) or "answer" not in result:
            raise HTTPException(
                status_code=500,
                detail="Invalid response from AI service."
            )

        return {
            "answer": result["answer"],
            "sources": result.get("sources", [])
        }

    except HTTPException:
        raise

    except Exception as exc:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(exc)}"
        )
