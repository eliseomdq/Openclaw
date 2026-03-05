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
                    phone = (phone_el.first.get_attribute("data-item-id") or "").replace("phone:tel:", "")

                # Sitio web
                website = ""
                web_el = page.locator('[data-item-id="authority"]')
                if web_el.count() > 0:
                    website = web_el.first.get_attribute("href") or ""

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
    with get_session() as session:
        ids = []

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
        return ids


@app.task(name="workers.scraper.run_scraper")
def run_scraper(query: str, ciudad: str, max_results: int = 50, campana_id: int = None):
    """Task Celery: scrapa Google Maps y encola cada negocio para auditoria."""
    from workers.auditor import audit_business

    logger.info(f"Scraping: {query} en {ciudad}")
    businesses = scrape_google_maps(query, ciudad, max_results)
    ids = save_businesses(businesses, campana_id)

    logger.info(f"Guardados {len(ids)} negocios nuevos")

    for biz_id in ids:
        audit_business.delay(biz_id)

    return {"scraped": len(businesses), "new": len(ids)}
