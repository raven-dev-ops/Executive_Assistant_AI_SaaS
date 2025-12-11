from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import Response, Form
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
    result = await owner_assistant_service.answer(
        payload.question, business_id=business_id
    )
    return OwnerAssistantReply(answer=result.answer, model=result.used_model)


@router.post("/voice-reply", response_class=Response)
async def owner_assistant_voice_reply(
    Question: str = Form(..., description="Owner question via Twilio <Gather>"),
    business_id: str = Depends(ensure_business_active),
) -> Response:
    """Return a TwiML <Say> response for owner AI questions.

    This allows the owner assistant to answer over voice (e.g., Twilio
    webhook) without exposing sensitive data. Answers are grounded in the
    same docs as the text endpoint.
    """
    result = await owner_assistant_service.answer(Question, business_id=business_id)
    safe = result.answer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    twiml = f"""
<Response>
  <Say voice="alice">{safe}</Say>
</Response>
""".strip()
    return Response(content=twiml, media_type="text/xml")
