from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.commands import generate_commands
from app.core.diff import diff_config

router = APIRouter()


@router.get("/api/status")
async def api_status(request: Request):
    driver = request.app.state.driver
    status = driver.get_status()
    return JSONResponse(content=status.model_dump())


@router.get("/diff")
async def diff_view(request: Request):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()
    diffs = diff_config(config, status)
    all_commands = generate_commands(diffs) if diffs else []

    return templates.TemplateResponse("diff.html", {
        "request": request,
        "diffs": diffs,
        "commands": all_commands,
        "diff_count": len(diffs),
    })


@router.post("/apply")
async def apply_config(request: Request):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()
    diffs = diff_config(config, status)

    if not diffs:
        return templates.TemplateResponse("diff.html", {
            "request": request,
            "diffs": [],
            "commands": [],
            "diff_count": 0,
            "result": "No changes needed.",
            "success": True,
        })

    all_commands = generate_commands(diffs)

    try:
        output = driver.send_commands(all_commands)
        return templates.TemplateResponse("diff.html", {
            "request": request,
            "diffs": diffs,
            "commands": all_commands,
            "diff_count": len(diffs),
            "result": output,
            "success": True,
        })
    except Exception as e:
        return templates.TemplateResponse("diff.html", {
            "request": request,
            "diffs": diffs,
            "commands": all_commands,
            "diff_count": len(diffs),
            "result": str(e),
            "success": False,
        })
