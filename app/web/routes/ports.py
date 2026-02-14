from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.diff import diff_config

router = APIRouter()

# SVG layout constants
RECT_W = 32
RECT_H = 28
GAP = 4
LEFT_MARGIN = 30
TOP_MARGIN = 30
PORT_RADIUS = 4


def _build_port_data(status, config):
    """Build port rendering data for SVG grid.

    Layout: 48 copper ports in 2 rows (top=odd, bottom=even), plus 4 SFP+ uplinks.
    """
    # Compute diffs for drift detection
    drifted_ports: set[str] = set()
    try:
        diffs = diff_config(config, status)
        for d in diffs:
            if d.resource_type == "port":
                drifted_ports.add(d.resource_id)
    except Exception:
        pass

    port_items = []

    for i in range(1, 49):
        port_id = str(i)
        port = status.ports.get(port_id)

        # Column: pairs of ports share a column (1&2 = col 0, 3&4 = col 1, ...)
        col = (i - 1) // 2
        row = 0 if i % 2 == 1 else 1  # odd=top, even=bottom

        x = LEFT_MARGIN + col * (RECT_W + GAP)
        y = TOP_MARGIN + row * (RECT_H + GAP)

        # Color by status
        if port is None:
            color = "#6b7280"
            stroke = "none"
        elif port_id in drifted_ports:
            color = "#f97316"  # orange for drift
            stroke = "#f97316"
        elif port.admin_status == "down":
            color = "#ef4444"  # red for disabled
            stroke = "none"
        elif port.oper_status == "up":
            color = "#22c55e"  # green for up
            stroke = "#3b82f6" if port.poe_status == "delivering" else "none"
        else:
            color = "#6b7280"  # gray for down
            stroke = "none"

        stroke_width = 2 if stroke != "none" else 0

        # Tooltip text
        desc = port.description if port else ""
        vlan = port.vlan if port else ""
        speed = port.speed if port else ""
        title = f"Port {port_id}"
        if desc:
            title += f" - {desc}"
        if vlan:
            title += f"\nVLAN: {vlan}"
        if speed and speed != "auto":
            title += f"\nSpeed: {speed}"

        port_items.append({
            "id": port_id,
            "x": x,
            "y": y,
            "tx": x + RECT_W // 2,
            "ty": y + RECT_H // 2 + 4,
            "color": color,
            "stroke": stroke,
            "stroke_width": stroke_width,
            "title_text": title,
        })

    # SFP+ uplinks (49-52)
    sfp_y = TOP_MARGIN + 2 * (RECT_H + GAP) + 20
    sfp_w = 40
    for idx, i in enumerate(range(49, 53)):
        port_id = str(i)
        port = status.ports.get(port_id)

        x = LEFT_MARGIN + idx * (sfp_w + GAP * 2)
        y = sfp_y

        if port is None:
            color = "#6b7280"
            stroke = "none"
        elif port_id in drifted_ports:
            color = "#f97316"
            stroke = "#f97316"
        elif port.admin_status == "down":
            color = "#ef4444"
            stroke = "none"
        elif port.oper_status == "up":
            color = "#22c55e"
            stroke = "none"
        else:
            color = "#6b7280"
            stroke = "none"

        stroke_width = 2 if stroke != "none" else 0

        desc = port.description if port else ""
        title = f"SFP+ Port {port_id}"
        if desc:
            title += f" - {desc}"

        port_items.append({
            "id": port_id,
            "x": x,
            "y": y,
            "tx": x + sfp_w // 2,
            "ty": y + RECT_H // 2 + 4,
            "color": color,
            "stroke": stroke,
            "stroke_width": stroke_width,
            "title_text": title,
            "is_sfp": True,
            "width": sfp_w,
        })

    # Calculate SVG dimensions
    svg_width = LEFT_MARGIN + 24 * (RECT_W + GAP) + 20
    svg_height = sfp_y + RECT_H + 40

    return port_items, svg_width, svg_height


@router.get("/ports")
async def ports_view(request: Request):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()
    port_items, svg_width, svg_height = _build_port_data(status, config)

    return templates.TemplateResponse("ports.html", {
        "request": request,
        "ports": port_items,
        "svg_width": svg_width,
        "svg_height": svg_height,
        "rect_w": RECT_W,
        "rect_h": RECT_H,
        "port_radius": PORT_RADIUS,
    })


@router.get("/ports/{port_id}")
async def port_detail(request: Request, port_id: str):
    driver = request.app.state.driver
    templates = request.app.state.templates
    config = request.app.state.config

    status = driver.get_status()
    port = status.ports.get(port_id)

    # Get config for this port
    port_config = config.ports.get(port_id) or config.uplinks.get(port_id)

    return templates.TemplateResponse("port_detail.html", {
        "request": request,
        "port": port,
        "port_config": port_config,
        "port_id": port_id,
    })
