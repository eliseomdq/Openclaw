import html as html_module
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from db.database import get_session, init_db
from db.models import Business, Campaign
from sqlalchemy import func

app = FastAPI(title="OpenClaw Dashboard")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>OpenClaw Dashboard</title>
  <style>
    body {{ font-family: system-ui; background: #0d0d1a; color: #e0e0e0; padding: 20px; }}
    h1 {{ color: #00d4ff; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin: 20px 0; }}
    .stat {{ background: #1a1a2e; border: 1px solid #00d4ff33; border-radius: 8px; padding: 16px; text-align: center; }}
    .stat .num {{ font-size: 2em; color: #00d4ff; font-weight: bold; }}
    .stat .label {{ color: #888; font-size: 0.85em; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th {{ background: #1a1a2e; color: #00d4ff; padding: 10px; text-align: left; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #1a1a2e; font-size: 0.9em; }}
    tr:hover td {{ background: #1a1a2e44; }}
    .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.8em; }}
    .F {{ background: #ff000033; color: #ff6b6b; }}
    .D {{ background: #ff6b0033; color: #ffaa44; }}
    .C {{ background: #ffff0033; color: #ffff44; }}
    .B {{ background: #00ff0033; color: #44ff88; }}
  </style>
</head>
<body>
  <h1>OpenClaw Dashboard</h1>
  <div class="stats">
    <div class="stat"><div class="num">{total}</div><div class="label">Total negocios</div></div>
    <div class="stat"><div class="num">{sin_sitio}</div><div class="label">Sin sitio (F)</div></div>
    <div class="stat"><div class="num">{desplegados}</div><div class="label">Previews listos</div></div>
    <div class="stat"><div class="num">{contactados}</div><div class="label">Contactados</div></div>
    <div class="stat"><div class="num">{convertidos}</div><div class="label">Convertidos</div></div>
  </div>
  <table>
    <tr>
      <th>Negocio</th><th>Ciudad</th><th>Nota</th><th>Estado</th><th>Preview</th>
    </tr>
    {rows}
  </table>
</body>
</html>
"""

ROW_TEMPLATE = """<tr>
  <td>{nombre}</td>
  <td>{ciudad}</td>
  <td><span class="badge {nota}">{nota}</span></td>
  <td>{estado}</td>
  <td>{preview}</td>
</tr>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with get_session() as session:
        businesses = session.query(Business).order_by(Business.id.desc()).limit(200).all()
        total = session.query(func.count(Business.id)).scalar()
        sin_sitio = session.query(func.count(Business.id)).filter(Business.nota_auditoria == "F").scalar()
        desplegados = session.query(func.count(Business.id)).filter(Business.url_preview.isnot(None)).scalar()
        contactados = session.query(func.count(Business.id)).filter(Business.email_enviado == True).scalar()
        convertidos = session.query(func.count(Business.id)).filter(Business.convertido == True).scalar()

        rows = ""
        for b in businesses:
            url = b.url_preview or ""
            # Only allow http/https URLs to prevent javascript: injection
            if url and not url.startswith(("http://", "https://")):
                url = ""
            preview = f'<a href="{html_module.escape(url)}" target="_blank" style="color:#00d4ff">Ver</a>' if url else "-"
            nota = html_module.escape(b.nota_auditoria or "-")
            rows += ROW_TEMPLATE.format(
                nombre=html_module.escape(b.nombre or "-"),
                ciudad=html_module.escape(b.ciudad or "-"),
                nota=nota,
                estado=html_module.escape(b.estado or "-"),
                preview=preview,
            )

    return DASHBOARD_HTML.format(
        total=total, sin_sitio=sin_sitio, desplegados=desplegados,
        contactados=contactados, convertidos=convertidos, rows=rows
    )


@app.get("/api/stats")
def stats():
    with get_session() as session:
        return {
            "total": session.query(func.count(Business.id)).scalar(),
            "por_nota": {
                n: session.query(func.count(Business.id)).filter(Business.nota_auditoria == n).scalar()
                for n in ["F", "D", "C", "B", "A"]
            },
            "por_estado": dict(
                session.query(Business.estado, func.count(Business.id)).group_by(Business.estado).all()
            ),
        }


@app.post("/api/mark-converted/{business_id}")
def mark_converted(business_id: int):
    from fastapi import HTTPException
    with get_session() as session:
        b = session.get(Business, business_id)
        if not b:
            raise HTTPException(status_code=404, detail="Business not found")
        b.convertido = True
        b.estado = "converted"
        session.commit()
    return {"ok": True}
