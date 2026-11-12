"""Typed marketplace handoff service with an observable agent-loop boundary."""

from __future__ import annotations

import hashlib
import traceback
from typing import Callable, Literal, Protocol
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai_client import InfraiClient, InfraiError, InfraiTransportError


class SellerAsset(BaseModel):
    asset_id: str
    seller_id: str
    name: str
    status: Literal["draft", "ready"]


class BuyerUpdate(BaseModel):
    update_id: str
    kind: Literal["delivery_note", "contact_change"]
    text: str


class HandoffRequest(BaseModel):
    order_id: str
    asset: SellerAsset
    buyer_updates: list[BuyerUpdate] = Field(default_factory=list)


class HandoffResult(BaseModel):
    order_id: str
    state: Literal["waiting_for_asset", "handed_off"]
    asset_id: str
    included_update_ids: list[str]


class Observability(Protocol):
    errors: object
    flags: object


def decide_handoff(request: HandoffRequest, include_buyer_updates: bool) -> HandoffResult:
    """Build the handoff manifest; drafts never cross the order boundary."""
    included = (
        [update.update_id for update in request.buyer_updates]
        if include_buyer_updates
        else []
    )
    state = "handed_off" if request.asset.status == "ready" else "waiting_for_asset"
    return HandoffResult(
        order_id=request.order_id,
        state=state,
        asset_id=request.asset.asset_id,
        included_update_ids=included,
    )


def process_handoff(request: HandoffRequest, infrai: InfraiClient) -> HandoffResult:
    """Cross flag evaluation and error capture around one marketplace decision."""
    try:
        flag = infrai.flags.get_value("buyer-updates-in-handoff")
        return decide_handoff(request, include_buyer_updates=bool(flag["value"]))
    except (InfraiError, InfraiTransportError):
        raise
    except Exception as exc:
        identity = f"{request.order_id}:{request.asset.asset_id}:{type(exc).__name__}"
        write_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        infrai.errors.capture(
            title="marketplace handoff agent failed",
            message=str(exc),
            exception=traceback.format_exc(),
            level="error",
            fingerprint=["marketplace-handoff", type(exc).__name__],
            context={
                "order_id": request.order_id,
                "asset_id": request.asset.asset_id,
                "seller_id": request.asset.seller_id,
            },
            idempotency_key=write_key,
        )
        raise


app = FastAPI(title="Marketplace handoff observer")


@app.post("/handoffs", response_model=HandoffResult)
def create_handoff(request: HandoffRequest) -> HandoffResult:
    try:
        return process_handoff(request, InfraiClient())
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=client_status, detail=exc.detail) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def build_local_processor(flag_value: bool) -> Callable[[HandoffRequest], HandoffResult]:
    """Return the deterministic decision used by the local script."""
    return lambda request: decide_handoff(request, flag_value)
