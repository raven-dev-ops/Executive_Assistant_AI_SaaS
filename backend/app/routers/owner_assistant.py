from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import ensure_business_active, require_owner_dashboard_auth
from ..services.owner_assistant import owner_assistant_service


router = APIRouter(dependencies=[Depends(require_owner_dashboard_auth)])


class OwnerAssistantQuery(BaseModel):
    question: str


class OwnerAssistantReply(BaseModel):
    answer: str
    model: str | None = None


@router.post("/query", response_model=OwnerAssistantReply)
async def owner_assistant_query(
    payload: OwnerAssistantQuery,
    business_id: str = Depends(ensure_business_active),
) -> OwnerAssistantReply:
    """Answer owner dashboard questions via the AI assistant.

    The request is scoped to the authenticated tenant but does not expose
    any private identifiers or secrets to the model. Answers are grounded
    primarily in local documentation and public metric definitions.
    """
    # `business_id` is accepted for future per-tenant tuning but not sent
    # directly to the model to avoid leaking identifiers.
    _ = business_id
    result = await owner_assistant_service.answer(payload.question)
    return OwnerAssistantReply(answer=result.answer, model=result.used_model)
