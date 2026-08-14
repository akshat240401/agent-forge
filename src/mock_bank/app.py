from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.mock_bank.data import (
    MEMBERS,
    NOT_FOUND_MEMBER_ID,
    PERMISSION_DENIED_MEMBER_ID,
    SLOW_MEMBER_ID,
)


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Legacy Member Servicing",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def search_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"message": None, "member_id": ""},
    )


@app.post("/members/search", response_class=HTMLResponse)
async def search_member(request: Request, member_id: str = Form(...)):
    member_id = member_id.strip()

    if not member_id:
        return templates.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "message": "Member ID is required.",
                "member_id": "",
            },
            status_code=400,
        )

    if member_id == SLOW_MEMBER_ID:
        # Deliberately bounded slowness: a real runtime condition, not a permanent hang.
        await asyncio.sleep(2.0)
        return templates.TemplateResponse(
            request=request,
            name="interstitial.html",
            context={"member_id": "12345"},
        )

    if member_id == PERMISSION_DENIED_MEMBER_ID:
        return templates.TemplateResponse(
            request=request,
            name="permission_denied.html",
            context={"member_id": member_id},
            status_code=403,
        )

    member = MEMBERS.get(member_id)
    if member is None or member_id == NOT_FOUND_MEMBER_ID:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={"member_id": member_id},
            status_code=200,
        )

    return templates.TemplateResponse(
        request=request,
        name="member_detail.html",
        context={"member": member},
    )


@app.post("/session/continue", response_class=HTMLResponse)
async def continue_session(request: Request, member_id: str = Form(...)):
    member = MEMBERS.get(member_id)
    if member is None:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={"member_id": member_id},
        )

    return templates.TemplateResponse(
        request=request,
        name="member_detail.html",
        context={"member": member},
    )
