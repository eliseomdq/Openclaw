import os
import anthropic
from workers.celery_app import app
from db.database import get_session
from db.models import Business
from config import CLAUDE_API_KEY, PREVIEWS_DIR
import logging

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

NOTA_DESCRIPCIONES = {
    "F": "sin sitio web actualmente",
    "D": "sitio web muy desactualizado",
    "C": "sitio web regular, poco profesional",
}

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "base_prompt.txt")


def load_prompt_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def generate_html(nombre: str, categoria: str, ciudad: str, telefono: str, nota: str) -> str:
    """Genera HTML completo del sitio con Claude."""
    template = load_prompt_template()
    prompt = template.format(
        nombre=nombre,
        categoria=categoria or "negocio local",
        ciudad=ciudad or "Argentina",
        telefono=telefono or "Consultar",
        nota=nota,
        nota_descripcion=NOTA_DESCRIPCIONES.get(nota, "sitio mejorable"),
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    html = message.content[0].text.strip()

    # Limpiar si Claude envolvio en markdown
    if html.startswith("```html"):
        html = html[7:]
    if html.startswith("```"):
        html = html[3:]
    if html.endswith("```"):
        html = html[:-3]

    return html.strip()


def save_preview(business_id: int, html: str) -> str:
    """Guarda el HTML en disco. Retorna path."""
    os.makedirs(PREVIEWS_DIR, exist_ok=True)
    path = os.path.join(PREVIEWS_DIR, f"business_{business_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


@app.task(name="workers.generator.generate_website")
def generate_website(business_id: int):
    """Genera sitio web con Claude y lo guarda. Encola deploy."""
    from workers.deployer import deploy_website

    path = None
    with get_session() as session:
        b = session.get(Business, business_id)
        if not b:
            return {"error": "Business not found"}

        logger.info(f"Generando sitio para: {b.nombre}")
        try:
            html = generate_html(b.nombre, b.categoria, b.ciudad, b.telefono, b.nota_auditoria)
            path = save_preview(b.id, html)
            b.html_generado = html
            b.estado = "generated"
            session.commit()
        except Exception as e:
            logger.error(f"Error generando sitio para {b.nombre}: {e}")
            b.estado = "error"
            session.commit()
            raise

    if path:
        deploy_website.delay(business_id, path)
    return {"id": business_id, "path": path}
