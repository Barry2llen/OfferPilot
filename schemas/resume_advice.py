from pydantic import BaseModel


class ResumeAdviceRequest(BaseModel):
    model_selection_id: int
    user_prompt: str | None = None


class ResumeAdviceResponse(BaseModel):
    resume_id: int
    model_selection_id: int
    content: str


__all__ = ["ResumeAdviceRequest", "ResumeAdviceResponse"]
