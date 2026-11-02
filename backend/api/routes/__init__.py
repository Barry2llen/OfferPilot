from .ai import router as ai_router
from .analysis import router as analysis_router
from .job_description import router as job_description_router
from .model_config import router as model_config_router
from .resume import router as resume_router

__all__ = [
    "ai_router",
    "analysis_router",
    "job_description_router",
    "model_config_router",
    "resume_router",
]
