# OpenClaw Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated pipeline that finds local businesses without good websites, generates a custom AI site, deploys it as a preview, and contacts the business via email and WhatsApp.

**Architecture:** Five independent Celery workers (scraper, auditor, generator, deployer, outreach) connected via Redis queue. Each business is a task that flows through the pipeline independently. SQLite for storage, FastAPI for a simple dashboard.

**Tech Stack:** Python 3.11, Celery, Redis (Docker), Playwright, Anthropic Claude API, GitHub Pages API, Gmail SMTP / Resend, Evolution API (WhatsApp), SQLAlchemy, FastAPI.

---

## Prerequisites (do once manually before starting)

1. Install Python 3.11+
2. Install Docker Desktop
3. Install Node.js (needed for Playwright browsers)
4. Have a Claude API key ready
5. Have a GitHub account + personal access token (repo scope)
6. Have a Gmail account or Resend API key

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `openclaw/requirements.txt`
- Create: `openclaw/docker-compose.yml`
- Create: `openclaw/config.py`
- Create: `openclaw/.env.example`
- Create: `openclaw/main.py`

**Step 1: Create the project folder and virtualenv**

```bash
mkdir -p C:/Users/elise/OneDrive/Escritorio/openclaw
cd C:/Users/elise/OneDrive/Escritorio/openclaw
python -m venv venv
venv/Scripts/activate
```

**Step 2: Create `requirements.txt`**

```
celery==5.3.6
redis==5.0.3
playwright==1.43.0
anthropic==0.25.0
sqlalchemy==2.0.29
alembic==1.13.1
fastapi==0.111.0
uvicorn==0.29.0
python-dotenv==1.0.1
httpx==0.27.0
jinja2==3.1.3
pillow==10.3.0
requests==2.31.0
pytest==8.1.1
pytest-asyncio==0.23.6
```

**Step 3: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors, chromium downloaded.

**Step 4: Create `docker-compose.yml`**

```yaml
version: "3.9"
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

**Step 5: Start Redis**

```bash
docker compose up -d
```

Expected: `redis` container running.

**Step 6: Create `.env.example`**

```
CLAUDE_API_KEY=your_key_here
GITHUB_TOKEN=your_github_token
GITHUB_USERNAME=your_github_username
GITHUB_REPO=raven-previews
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=your_app_password
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=your_key
EVOLUTION_INSTANCE=openclaw
RESEND_API_KEY=optional_if_using_resend
```

**Step 7: Create `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "raven-previews")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "openclaw")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

REDIS_URL = "redis://localhost:6379/0"
DATABASE_URL = "sqlite:///openclaw.db"
PREVIEWS_DIR = "previews"
```

**Step 8: Create `main.py`**

```python
from db.database import init_db

if __name__ == "__main__":
    init_db()
    print("OpenClaw DB initialized. Run workers with: celery -A workers.celery_app worker --loglevel=info")
```

**Step 9: Commit**

```bash
git init
git add .
git commit -m "feat: project scaffold and dependencies"
```

---

### Task 2: Database models

**Files:**
- Create: `openclaw/db/__init__.py`
- Create: `openclaw/db/database.py`
- Create: `openclaw/db/models.py`
- Create: `openclaw/tests/test_models.py`

**Step 1: Create `db/__init__.py`** (empty file)

**Step 2: Create `db/models.py`**

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    ciudad = Column(String, nullable=False)
    rubros = Column(String)  # JSON string list
    cantidad_diaria = Column(Integer, default=50)
    activa = Column(Boolean, default=True)
    creada_en = Column(DateTime, default=datetime.utcnow)


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True)
    campana_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)

    # Datos scrapeados
    nombre = Column(String, nullable=False)
    categoria = Column(String)
    ciudad = Column(String)
    telefono = Column(String)
    email = Column(String)
    whatsapp = Column(String)
    url_sitio_actual = Column(String)
    rating = Column(String)
    direccion = Column(String)

    # Auditoria
    nota_auditoria = Column(String)  # F, D, C, B, A
    screenshot_actual = Column(String)  # path local

    # Preview generado
    html_generado = Column(Text)
    url_preview = Column(String)

    # Pipeline state
    estado = Column(String, default="scraped")
    # Estados: scraped, audited, skipped, generated, deployed,
    #          outreach_email, outreach_whatsapp, follow_up,
    #          responded, converted, lost

    # Outreach tracking
    email_enviado = Column(Boolean, default=False)
    whatsapp_enviado = Column(Boolean, default=False)
    respondio = Column(Boolean, default=False)
    convertido = Column(Boolean, default=False)

    fecha_scraping = Column(DateTime, default=datetime.utcnow)
    fecha_ultimo_contacto = Column(DateTime)
    notas = Column(Text)
```

**Step 3: Create `db/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session():
    return SessionLocal()
```

**Step 4: Write test**

```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Business, Campaign


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_campaign(db):
    c = Campaign(nombre="Test", ciudad="Mar del Plata", rubros='["plomero"]')
    db.add(c)
    db.commit()
    assert c.id is not None


def test_create_business(db):
    b = Business(nombre="Plomeria Test", ciudad="Mar del Plata", estado="scraped")
    db.add(b)
    db.commit()
    assert b.id is not None
    assert b.estado == "scraped"


def test_business_default_estado(db):
    b = Business(nombre="Test SRL")
    db.add(b)
    db.commit()
    assert b.estado == "scraped"
```

**Step 5: Run tests**

```bash
cd openclaw
python -m pytest tests/test_models.py -v
```

Expected: 3 tests PASS.

**Step 6: Commit**

```bash
git add db/ tests/
git commit -m "feat: database models and session setup"
```

---

### Task 3: Celery app and worker base

**Files:**
- Create: `openclaw/workers/__init__.py`
- Create: `openclaw/workers/celery_app.py`
- Create: `openclaw/tests/test_celery.py`

**Step 1: Create `workers/__init__.py`** (empty)

**Step 2: Create `workers/celery_app.py`**

```python
from celery import Celery
from config import REDIS_URL

app = Celery(
    "openclaw",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "workers.scraper",
        "workers.auditor",
        "workers.generator",
        "workers.deployer",
        "workers.outreach",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    task_track_started=True,
)
```

**Step 3: Write test**

```python
# tests/test_celery.py
from workers.celery_app import app


def test_celery_app_created():
    assert app.main == "openclaw"


def test_celery_broker_configured():
    assert "redis" in app.conf.broker_url
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_celery.py -v
```

Expected: 2 tests PASS.

**Step 5: Commit**

```bash
git add workers/
git commit -m "feat: celery app configuration"
```

---

### Task 4: Scraper worker

**Files:**
- Create: `openclaw/workers/scraper.py`
- Create: `openclaw/tests/test_scraper.py`

**Step 1: Create `workers/scraper.py`**

```python
import time
import random
from playwright.sync_api import sync_playwright
from workers.celery_app import app
from db.database import get_session
from db.models import Business
import logging

logger = logging.getLogger(__name__)


def scrape_google_maps(query: str, ciudad: str, max_results: int = 50) -> list[dict]:
    """Scrapa Google Maps y retorna lista de negocios."""
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        search_query = f"{query} {ciudad}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"

        page.goto(url, wait_until="networkidle")
        time.sleep(2)

        # Scroll para cargar mas resultados
        scrollable = page.locator('[role="feed"]')
        for _ in range(5):
            scrollable.evaluate("el => el.scrollTop += 1000")
            time.sleep(1.5)

        # Extraer resultados
        listings = page.locator('[role="feed"] > div > div > a').all()

        for listing in listings[:max_results]:
            try:
                listing.click()
                time.sleep(2)

                name = page.locator('h1').first.inner_text() if page.locator('h1').count() > 0 else ""
                if not name:
                    continue

                # Telefono
                phone = ""
                phone_el = page.locator('[data-item-id^="phone"]')
                if phone_el.count() > 0:
                    phone = phone_el.first.get_attribute("data-item-id", "").replace("phone:tel:", "")

                # Sitio web
                website = ""
                web_el = page.locator('[data-item-id="authority"]')
                if web_el.count() > 0:
                    website = web_el.first.get_attribute("href", "")

                # Categoria
                category = ""
                cat_el = page.locator('button[jsaction*="category"]')
                if cat_el.count() > 0:
                    category = cat_el.first.inner_text()

                # Rating
                rating = ""
                rat_el = page.locator('[role="img"][aria-label*="estrellas"]')
                if rat_el.count() > 0:
                    rating = rat_el.first.get_attribute("aria-label", "")

                results.append({
                    "nombre": name.strip(),
                    "categoria": category.strip(),
                    "ciudad": ciudad,
                    "telefono": phone.strip(),
                    "url_sitio_actual": website.strip(),
                    "rating": rating.strip(),
                })

                time.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                logger.warning(f"Error extrayendo negocio: {e}")
                continue

        browser.close()

    return results


def save_businesses(businesses: list[dict], campana_id: int = None) -> list[int]:
    """Guarda negocios en DB, evita duplicados por nombre+ciudad. Retorna IDs."""
    session = get_session()
    ids = []

    try:
        for biz in businesses:
            existing = session.query(Business).filter_by(
                nombre=biz["nombre"],
                ciudad=biz["ciudad"]
            ).first()

            if existing:
                continue

            b = Business(
                nombre=biz["nombre"],
                categoria=biz.get("categoria"),
                ciudad=biz["ciudad"],
                telefono=biz.get("telefono"),
                url_sitio_actual=biz.get("url_sitio_actual"),
                rating=biz.get("rating"),
                campana_id=campana_id,
                estado="scraped",
            )
            session.add(b)
            session.flush()
            ids.append(b.id)

        session.commit()
    finally:
        session.close()

    return ids


@app.task(name="workers.scraper.run_scraper")
def run_scraper(query: str, ciudad: str, max_results: int = 50, campana_id: int = None):
    """Task Celery: scrapa Google Maps y encola cada negocio para auditoria."""
    from workers.auditor import audit_business

    logger.info(f"Scraping: {query} en {ciudad}")
    businesses = scrape_google_maps(query, ciudad, max_results)
    ids = save_businesses(businesses, campana_id)

    logger.info(f"Guardados {len(ids)} negocios nuevos")

    # Encolar auditoria para cada uno
    for biz_id in ids:
        audit_business.delay(biz_id)

    return {"scraped": len(businesses), "new": len(ids)}
```

**Step 2: Write test (sin Playwright, mockeamos)**

```python
# tests/test_scraper.py
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Base, Business
from workers.scraper import save_businesses


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_save_businesses_creates_records(db_session):
    businesses = [
        {"nombre": "Plomeria Juan", "ciudad": "MdP", "telefono": "223000", "url_sitio_actual": "", "categoria": "Plomero", "rating": "4.5"},
    ]

    with patch("workers.scraper.get_session", return_value=db_session):
        ids = save_businesses(businesses)

    assert len(ids) == 1
    b = db_session.query(Business).first()
    assert b.nombre == "Plomeria Juan"
    assert b.estado == "scraped"


def test_save_businesses_no_duplicates(db_session):
    businesses = [
        {"nombre": "Plomeria Juan", "ciudad": "MdP", "telefono": "223000", "url_sitio_actual": "", "categoria": "Plomero", "rating": ""},
    ]

    with patch("workers.scraper.get_session", return_value=db_session):
        ids1 = save_businesses(businesses)
        ids2 = save_businesses(businesses)  # mismo negocio

    assert len(ids1) == 1
    assert len(ids2) == 0  # no duplicado
```

**Step 3: Run tests**

```bash
python -m pytest tests/test_scraper.py -v
```

Expected: 2 tests PASS.

**Step 4: Commit**

```bash
git add workers/scraper.py tests/test_scraper.py
git commit -m "feat: scraper worker with Google Maps and dedup"
```

---

### Task 5: Auditor worker

**Files:**
- Create: `openclaw/workers/auditor.py`
- Create: `openclaw/tests/test_auditor.py`

**Step 1: Create `workers/auditor.py`**

```python
import anthropic
import httpx
from workers.celery_app import app
from db.database import get_session
from db.models import Business
from config import CLAUDE_API_KEY
import logging

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

AUDIT_PROMPT = """Eres un experto en diseño web y UX. Analiza este sitio web de un negocio local.

URL: {url}
Nombre del negocio: {nombre}
Categoria: {categoria}

Basandote en lo que sabes sobre sitios web de negocios locales en Argentina, evalua:
1. Diseno visual (moderno vs desactualizado)
2. Adaptacion mobile (responsive o no)
3. Claridad del mensaje y CTA
4. Velocidad percibida (uso de recursos pesados)
5. Informacion de contacto visible

Responde SOLO con una linea en este formato exacto:
NOTA: [F/D/C/B/A] | RAZON: [una frase corta explicando la nota principal]

F = sin sitio web
D = sitio muy malo (desactualizado, no mobile, sin CTA)
C = sitio regular (funciona pero poco profesional)
B = sitio bueno pero mejorable
A = sitio excelente, no contactar
"""


def check_site_exists(url: str) -> bool:
    """Verifica si el sitio web existe y responde."""
    if not url:
        return False
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True)
        return r.status_code < 400
    except Exception:
        return False


def audit_with_claude(nombre: str, categoria: str, url: str) -> tuple[str, str]:
    """Llama a Claude para auditar el sitio. Retorna (nota, razon)."""
    prompt = AUDIT_PROMPT.format(url=url, nombre=nombre, categoria=categoria or "negocio local")

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text.strip()

    # Parsear respuesta: "NOTA: D | RAZON: Sitio desactualizado sin mobile"
    nota = "D"
    razon = ""
    if "NOTA:" in response and "|" in response:
        parts = response.split("|")
        nota = parts[0].replace("NOTA:", "").strip()
        razon = parts[1].replace("RAZON:", "").strip() if len(parts) > 1 else ""

    return nota, razon


@app.task(name="workers.auditor.audit_business")
def audit_business(business_id: int):
    """Audita un negocio y encola generacion si la nota es C, D o F."""
    from workers.generator import generate_website

    session = get_session()
    try:
        b = session.get(Business, business_id)
        if not b:
            return {"error": "Business not found"}

        # Sin sitio web -> nota F directo
        if not b.url_sitio_actual:
            b.nota_auditoria = "F"
            b.notas = "Sin sitio web"
            b.estado = "audited"
            session.commit()
            generate_website.delay(business_id)
            return {"id": business_id, "nota": "F"}

        # Verificar si el sitio existe
        site_exists = check_site_exists(b.url_sitio_actual)
        if not site_exists:
            b.nota_auditoria = "F"
            b.notas = "Sitio no responde"
            b.estado = "audited"
            session.commit()
            generate_website.delay(business_id)
            return {"id": business_id, "nota": "F"}

        # Auditar con Claude
        nota, razon = audit_with_claude(b.nombre, b.categoria, b.url_sitio_actual)
        b.nota_auditoria = nota
        b.notas = razon
        b.estado = "audited"
        session.commit()

        # Solo contactar si nota es C, D o F
        if nota in ("C", "D", "F"):
            generate_website.delay(business_id)
            return {"id": business_id, "nota": nota, "accion": "generando sitio"}
        else:
            b.estado = "skipped"
            session.commit()
            return {"id": business_id, "nota": nota, "accion": "skipped"}

    finally:
        session.close()
```

**Step 2: Write test**

```python
# tests/test_auditor.py
import pytest
from unittest.mock import patch, MagicMock
from workers.auditor import check_site_exists, audit_with_claude


def test_check_site_exists_no_url():
    assert check_site_exists("") is False
    assert check_site_exists(None) is False


def test_check_site_exists_bad_url():
    with patch("workers.auditor.httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        assert check_site_exists("http://sitio-que-no-existe-123.com") is False


def test_check_site_exists_200():
    with patch("workers.auditor.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        assert check_site_exists("http://ejemplo.com") is True


def test_audit_with_claude_parses_response():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="NOTA: D | RAZON: Sitio desactualizado sin version mobile")]
    )

    with patch("workers.auditor.client", mock_client):
        nota, razon = audit_with_claude("Test SA", "Plomero", "http://test.com")

    assert nota == "D"
    assert "desactualizado" in razon
```

**Step 3: Run tests**

```bash
python -m pytest tests/test_auditor.py -v
```

Expected: 4 tests PASS.

**Step 4: Commit**

```bash
git add workers/auditor.py tests/test_auditor.py
git commit -m "feat: auditor worker with Claude site grading"
```

---

### Task 6: Generator worker

**Files:**
- Create: `openclaw/workers/generator.py`
- Create: `openclaw/templates/` (directorio)
- Create: `openclaw/templates/base_prompt.txt`
- Create: `openclaw/tests/test_generator.py`

**Step 1: Crear directorio templates y `templates/base_prompt.txt`**

```
Eres un experto desarrollador web y copywriter. Crea un sitio web completo y profesional para el siguiente negocio local argentino.

NEGOCIO:
- Nombre: {nombre}
- Rubro: {categoria}
- Ciudad: {ciudad}
- Telefono: {telefono}
- Nota del sitio actual: {nota} ({nota_descripcion})

REQUISITOS TECNICOS:
- Un solo archivo HTML completo y autocontenido
- CSS embebido en <style> dentro del <head>
- Sin dependencias externas excepto Google Fonts (una sola fuente)
- Completamente responsive (mobile-first)
- Dark mode moderno o paleta profesional segun el rubro

REQUISITOS DE CONTENIDO:
- Hero section con nombre del negocio, slogan y CTA claro
- Seccion de servicios (inventar 4-5 servicios tipicos del rubro)
- Seccion "Por que elegirnos" con 3 puntos fuertes
- Seccion de contacto con telefono real y formulario simple (no funcional, solo HTML)
- Footer con nombre, ciudad y año

TONO: Profesional pero cercano, en español rioplatense argentino.

Responde SOLO con el HTML completo. Sin explicaciones. Sin bloques de codigo markdown. Solo el HTML puro empezando con <!DOCTYPE html>.
```

**Step 2: Create `workers/generator.py`**

```python
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

    session = get_session()
    try:
        b = session.get(Business, business_id)
        if not b:
            return {"error": "Business not found"}

        logger.info(f"Generando sitio para: {b.nombre}")
        html = generate_html(b.nombre, b.categoria, b.ciudad, b.telefono, b.nota_auditoria)

        path = save_preview(b.id, html)
        b.html_generado = html
        b.estado = "generated"
        session.commit()

        deploy_website.delay(business_id, path)
        return {"id": business_id, "path": path}

    finally:
        session.close()
```

**Step 3: Write test**

```python
# tests/test_generator.py
import pytest
from unittest.mock import patch, MagicMock
from workers.generator import generate_html, save_preview
import os
import tempfile


def test_generate_html_cleans_markdown():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="```html\n<!DOCTYPE html><html></html>\n```")]
    )

    with patch("workers.generator.client", mock_client):
        html = generate_html("Test SA", "Plomero", "MdP", "223000", "F")

    assert html.startswith("<!DOCTYPE html>")
    assert "```" not in html


def test_generate_html_returns_doctype():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="<!DOCTYPE html><html><head></head><body></body></html>")]
    )

    with patch("workers.generator.client", mock_client):
        html = generate_html("Restaurante El Gaucho", "Restaurante", "Mendoza", "261000", "D")

    assert "<!DOCTYPE html>" in html


def test_save_preview_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("workers.generator.PREVIEWS_DIR", tmpdir):
            path = save_preview(999, "<html>test</html>")
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == "<html>test</html>"
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_generator.py -v
```

Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add workers/generator.py templates/ tests/test_generator.py
git commit -m "feat: generator worker with Claude HTML generation"
```

---

### Task 7: Deployer worker (GitHub Pages)

**Files:**
- Create: `openclaw/workers/deployer.py`
- Create: `openclaw/tests/test_deployer.py`

**Prerequisito:** Crear repo `raven-previews` en GitHub con GitHub Pages habilitado (rama `main`, carpeta raiz).

**Step 1: Crear el repo en GitHub manualmente**
1. Ir a github.com → New repository → nombre: `raven-previews`
2. Inicializar con README
3. Settings → Pages → Source: Deploy from branch `main` / `/ (root)`

**Step 2: Create `workers/deployer.py`**

```python
import base64
import requests
from workers.celery_app import app
from db.database import get_session
from db.models import Business
from config import GITHUB_TOKEN, GITHUB_USERNAME, GITHUB_REPO
import logging
import re

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def slugify(text: str) -> str:
    """Convierte nombre a slug URL-safe."""
    text = text.lower().strip()
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

    session = get_session()
    try:
        b = session.get(Business, business_id)
        if not b or not b.html_generado:
            return {"error": "Business or HTML not found"}

        logger.info(f"Desplegando preview para: {b.nombre}")
        url = upload_to_github_pages(business_id, b.nombre, b.html_generado)

        b.url_preview = url
        b.estado = "deployed"
        session.commit()

        # Encolar outreach con countdown de 60 segundos (esperar que GitHub Pages propague)
        send_outreach.apply_async(args=[business_id], countdown=60)
        return {"id": business_id, "url": url}

    finally:
        session.close()
```

**Step 3: Write test**

```python
# tests/test_deployer.py
import pytest
from unittest.mock import patch, MagicMock
from workers.deployer import slugify, upload_to_github_pages


def test_slugify_basic():
    assert slugify("Plomería González & Hijos") == "plomeria-gonzalez-hijos"


def test_slugify_max_length():
    long_name = "A" * 100
    assert len(slugify(long_name)) <= 50


def test_upload_creates_url():
    with patch("workers.deployer.requests.get") as mock_get, \
         patch("workers.deployer.requests.put") as mock_put, \
         patch("workers.deployer.GITHUB_USERNAME", "testuser"), \
         patch("workers.deployer.GITHUB_REPO", "test-repo"):

        mock_get.return_value = MagicMock(status_code=404)
        mock_put.return_value = MagicMock(status_code=201)
        mock_put.return_value.raise_for_status = lambda: None

        url = upload_to_github_pages(1, "Plomeria Test", "<html></html>")

        assert "testuser.github.io" in url
        assert "plomeria-test" in url
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_deployer.py -v
```

Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add workers/deployer.py tests/test_deployer.py
git commit -m "feat: deployer worker with GitHub Pages upload"
```

---

### Task 8: Outreach worker (Email + WhatsApp)

**Files:**
- Create: `openclaw/workers/outreach.py`
- Create: `openclaw/tests/test_outreach.py`

**Step 1: Create `workers/outreach.py`**

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import requests
from workers.celery_app import app
from db.database import get_session
from db.models import Business
from config import GMAIL_USER, GMAIL_APP_PASSWORD, EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE
import logging

logger = logging.getLogger(__name__)

EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2 style="color: #1a1a2e;">Hola, {nombre}</h2>
  <p>Somos <strong>RAVEN</strong>, una agencia de automatizacion digital de Argentina.</p>
  <p>Notamos que {problema}, por eso preparamos una <strong>muestra gratuita</strong> de como podria verse tu sitio web:</p>
  <p style="text-align: center; margin: 30px 0;">
    <a href="{url_preview}"
       style="background: #00d4ff; color: #000; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">
      Ver mi sitio web gratis
    </a>
  </p>
  <p>Si te interesa, respondenos este mail o escribinos al WhatsApp.</p>
  <p>Saludos,<br><strong>Equipo RAVEN</strong><br>
  <a href="https://raven.com.ar">raven.com.ar</a></p>
</body>
</html>
"""

WA_TEMPLATE = """Hola {nombre}! Soy de RAVEN, agencia de automatizacion digital.

Preparamos una muestra gratuita de tu nuevo sitio web:
{url_preview}

Entras y lo ves, sin compromiso. Si te copa, coordinamos.

Saludos!"""


def get_problema(nota: str) -> str:
    mapping = {
        "F": "tu negocio no tiene sitio web todavia",
        "D": "tu sitio web actual esta bastante desactualizado",
        "C": "tu sitio web puede mejorar bastante para atraer mas clientes",
    }
    return mapping.get(nota, "tu sitio web puede mejorar")


def send_email(to: str, nombre: str, url_preview: str, nota: str) -> bool:
    """Envia email via Gmail SMTP. Retorna True si exitoso."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Hola {nombre} — preparamos algo para vos"
        msg["From"] = GMAIL_USER
        msg["To"] = to

        html_body = EMAIL_TEMPLATE.format(
            nombre=nombre,
            problema=get_problema(nota),
            url_preview=url_preview,
        )
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to, msg.as_string())

        return True
    except Exception as e:
        logger.error(f"Error enviando email a {to}: {e}")
        return False


def send_whatsapp(phone: str, nombre: str, url_preview: str) -> bool:
    """Envia WhatsApp via Evolution API. Retorna True si exitoso."""
    try:
        phone_clean = "".join(filter(str.isdigit, phone))
        if not phone_clean.startswith("54"):
            phone_clean = "54" + phone_clean

        message = WA_TEMPLATE.format(nombre=nombre, url_preview=url_preview)

        r = requests.post(
            f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"},
            json={"number": phone_clean, "text": message},
            timeout=15,
        )
        return r.status_code == 201
    except Exception as e:
        logger.error(f"Error enviando WhatsApp a {phone}: {e}")
        return False


@app.task(name="workers.outreach.send_outreach")
def send_outreach(business_id: int):
    """Envia email si hay email, WhatsApp si hay telefono."""
    session = get_session()
    try:
        b = session.get(Business, business_id)
        if not b or not b.url_preview:
            return {"error": "Business or preview not found"}

        enviado = False

        # Email
        if b.email:
            ok = send_email(b.email, b.nombre, b.url_preview, b.nota_auditoria)
            if ok:
                b.email_enviado = True
                enviado = True

        # WhatsApp
        if b.telefono:
            ok = send_whatsapp(b.telefono, b.nombre, b.url_preview)
            if ok:
                b.whatsapp_enviado = True
                enviado = True

        b.estado = "outreach_email" if b.email_enviado else ("outreach_whatsapp" if b.whatsapp_enviado else "deployed")
        b.fecha_ultimo_contacto = datetime.utcnow()
        session.commit()

        # Programar seguimiento en 3 dias (259200 segundos)
        if enviado:
            send_followup.apply_async(args=[business_id], countdown=259200)

        return {"id": business_id, "email": b.email_enviado, "whatsapp": b.whatsapp_enviado}

    finally:
        session.close()


@app.task(name="workers.outreach.send_followup")
def send_followup(business_id: int):
    """Seguimiento si no respondio."""
    session = get_session()
    try:
        b = session.get(Business, business_id)
        if not b or b.respondio:
            return {"skipped": True}

        # Solo WhatsApp de seguimiento si no respondio
        if b.telefono and b.url_preview:
            send_whatsapp(b.telefono, b.nombre, b.url_preview)

        b.estado = "follow_up"
        b.fecha_ultimo_contacto = datetime.utcnow()
        session.commit()
        return {"id": business_id, "followup": True}

    finally:
        session.close()
```

**Step 2: Write test**

```python
# tests/test_outreach.py
import pytest
from workers.outreach import get_problema, WA_TEMPLATE


def test_get_problema_F():
    assert "no tiene sitio web" in get_problema("F")


def test_get_problema_D():
    assert "desactualizado" in get_problema("D")


def test_get_problema_C():
    assert "mejorar" in get_problema("C")


def test_wa_template_format():
    msg = WA_TEMPLATE.format(nombre="Juan", url_preview="https://preview.com")
    assert "Juan" in msg
    assert "https://preview.com" in msg
```

**Step 3: Run tests**

```bash
python -m pytest tests/test_outreach.py -v
```

Expected: 4 tests PASS.

**Step 4: Commit**

```bash
git add workers/outreach.py tests/test_outreach.py
git commit -m "feat: outreach worker with email and whatsapp"
```

---

### Task 9: Dashboard FastAPI

**Files:**
- Create: `openclaw/dashboard/__init__.py`
- Create: `openclaw/dashboard/app.py`

**Step 1: Create `dashboard/__init__.py`** (empty)

**Step 2: Create `dashboard/app.py`**

```python
from fastapi import FastAPI, Request
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
    session = get_session()
    try:
        businesses = session.query(Business).order_by(Business.id.desc()).limit(200).all()
        total = session.query(func.count(Business.id)).scalar()
        sin_sitio = session.query(func.count(Business.id)).filter(Business.nota_auditoria == "F").scalar()
        desplegados = session.query(func.count(Business.id)).filter(Business.url_preview != None).scalar()
        contactados = session.query(func.count(Business.id)).filter(Business.email_enviado == True).scalar()
        convertidos = session.query(func.count(Business.id)).filter(Business.convertido == True).scalar()

        rows = ""
        for b in businesses:
            preview = f'<a href="{b.url_preview}" target="_blank" style="color:#00d4ff">Ver</a>' if b.url_preview else "-"
            rows += ROW_TEMPLATE.format(
                nombre=b.nombre or "-",
                ciudad=b.ciudad or "-",
                nota=b.nota_auditoria or "-",
                estado=b.estado or "-",
                preview=preview,
            )

        return DASHBOARD_HTML.format(
            total=total, sin_sitio=sin_sitio, desplegados=desplegados,
            contactados=contactados, convertidos=convertidos, rows=rows
        )
    finally:
        session.close()


@app.get("/api/stats")
def stats():
    session = get_session()
    try:
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
    finally:
        session.close()


@app.post("/api/mark-converted/{business_id}")
def mark_converted(business_id: int):
    session = get_session()
    try:
        b = session.get(Business, business_id)
        if b:
            b.convertido = True
            b.estado = "converted"
            session.commit()
        return {"ok": True}
    finally:
        session.close()
```

**Step 3: Inicializar DB y correr dashboard**

```bash
python main.py
uvicorn dashboard.app:app --reload --port 8001
```

Abrir: `http://localhost:8001`

**Step 4: Commit**

```bash
git add dashboard/
git commit -m "feat: fastapi dashboard with stats and business list"
```

---

### Task 10: CLI principal y ejecucion end-to-end

**Files:**
- Modify: `openclaw/main.py`
- Create: `openclaw/run_campaign.py`

**Step 1: Reemplazar `main.py`**

```python
import argparse
from db.database import init_db

def main():
    parser = argparse.ArgumentParser(description="OpenClaw - Automated Website Agency")
    subparsers = parser.add_subparsers(dest="command")

    # Init DB
    subparsers.add_parser("init", help="Inicializar base de datos")

    # Run scraper
    scrape_parser = subparsers.add_parser("scrape", help="Scraper Google Maps")
    scrape_parser.add_argument("--query", required=True, help='Ej: "plomero"')
    scrape_parser.add_argument("--ciudad", required=True, help='Ej: "Mar del Plata"')
    scrape_parser.add_argument("--max", type=int, default=50)

    # Dashboard
    subparsers.add_parser("dashboard", help="Iniciar dashboard web")

    # Worker
    subparsers.add_parser("worker", help="Iniciar Celery worker")

    args = parser.parse_args()

    if args.command == "init":
        init_db()
        print("DB inicializada.")

    elif args.command == "scrape":
        from workers.scraper import run_scraper
        result = run_scraper.delay(args.query, args.ciudad, args.max)
        print(f"Tarea encolada: {result.id}")

    elif args.command == "dashboard":
        import uvicorn
        uvicorn.run("dashboard.app:app", host="0.0.0.0", port=8001, reload=True)

    elif args.command == "worker":
        import subprocess
        subprocess.run(["celery", "-A", "workers.celery_app", "worker", "--loglevel=info"])

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

**Step 2: Probar el flujo completo (en 4 terminales)**

Terminal 1 — Redis:
```bash
docker compose up
```

Terminal 2 — Worker:
```bash
cd openclaw
python main.py worker
```

Terminal 3 — Dashboard:
```bash
cd openclaw
python main.py dashboard
```

Terminal 4 — Trigger scraping:
```bash
cd openclaw
python main.py init
python main.py scrape --query "plomero" --ciudad "Mar del Plata" --max 10
```

Verificar en `http://localhost:8001` que aparecen negocios.

**Step 3: Commit final**

```bash
git add main.py
git commit -m "feat: CLI principal con init, scrape, worker, dashboard"
```

---

## Resumen de comandos de ejecucion

```bash
# 1. Setup inicial (una vez)
cd openclaw
cp .env.example .env   # editar con tus claves
pip install -r requirements.txt
playwright install chromium
docker compose up -d
python main.py init

# 2. Correr el sistema (4 terminales)
python main.py worker       # procesa tareas
python main.py dashboard    # http://localhost:8001
python main.py scrape --query "electricista" --ciudad "Cordoba" --max 50

# 3. Tests
python -m pytest tests/ -v
```

---

## Proximos pasos (post-MVP)

- Agregar deteccion automatica de emails desde el sitio web del negocio (scraping de pagina de contacto)
- Campanas programadas via cron (scraping automatico diario)
- Multi-tenant: tabla `campaigns` con credenciales por cliente
- Upgrade a Postgres cuando haya >10k negocios
- WhatsApp oficial via Twilio cuando haya presupuesto
