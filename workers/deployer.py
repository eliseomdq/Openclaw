import base64
import re
import unicodedata
import requests
from workers.celery_app import app
from db.database import get_session
from db.models import Business
from config import GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO
import logging

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def slugify(text: str) -> str:
    """Convierte nombre a slug URL-safe."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:50]


def upload_to_github_pages(business_id: int, nombre: str, html: str) -> str:
    """Sube el HTML a GitHub Pages. Retorna URL publica."""
    slug = slugify(nombre)
    filename = f"previews/{slug}-{business_id}.html"

    # Verificar si ya existe (necesitamos el SHA para actualizar)
    check_url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{filename}"
    check_r = requests.get(check_url, headers=HEADERS)
    sha = check_r.json().get("sha") if check_r.status_code == 200 else None

    content_b64 = base64.b64encode(html.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"preview: {nombre}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(check_url, headers=HEADERS, json=payload)
    r.raise_for_status()

    preview_url = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}/previews/{slug}-{business_id}.html"
    return preview_url


@app.task(name="workers.deployer.deploy_website")
def deploy_website(business_id: int, html_path: str):
    """Despliega el preview a GitHub Pages y encola outreach."""
    from workers.outreach import send_outreach

    with get_session() as session:
        b = session.get(Business, business_id)
        if not b or not b.html_generado:
            return {"error": "Business or HTML not found"}

        logger.info(f"Desplegando preview para: {b.nombre}")
        try:
            url = upload_to_github_pages(business_id, b.nombre, b.html_generado)
            b.url_preview = url
            b.estado = "deployed"
            session.commit()
        except Exception as e:
            logger.error(f"Error desplegando {b.nombre}: {e}")
            b.estado = "error"
            session.commit()
            raise

    # Encolar outreach con countdown de 60 segundos
    send_outreach.apply_async(args=[business_id], countdown=60)
    return {"id": business_id, "url": url}
