from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/vlans")
async def vlans_view(request: Request):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()

    # Build VLAN data with port counts
    vlan_data = []
    config_vlans = {v.id: v for v in config.vlans}

    for vs in status.vlans:
        cv = config_vlans.get(vs.id)
        port_count = sum(
            1 for p in status.ports.values()
            if p.vlan == str(vs.id)
        )
        vlan_data.append({
            "id": vs.id,
            "name": vs.name,
            "status": vs.status,
            "description": cv.description if cv else "",
            "port_count": port_count,
            "in_config": cv is not None,
        })

    return templates.TemplateResponse("vlans.html", {
        "request": request,
        "vlans": vlan_data,
    })
