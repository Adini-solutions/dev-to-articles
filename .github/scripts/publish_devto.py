import os
import json
import requests
import subprocess
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DEVTO_API_URL = "https://dev.to/api/articles"
RAW_BASE = "https://github.com/Adini-solutions/dev-to-articles/blob/main"


# Mapeo de author_slug a nombre de variable de entorno
AUTHOR_API_KEYS = {
    "agustin-ezequiel-acevedo": "DEVTO_API_KEY_AGUS",
    "otro-autor": "DEVTO_API_KEY_OTRO",
    # Agregar más autores aquí
}

def extract_author_from_path(article_path: Path) -> str:
    """
    Extrae el author_slug del path: {author}/{year}/article/file.md
    """
    parts = article_path.parts
    if len(parts) >= 3:
        # El primer elemento del path es el author_slug
        author_slug = parts[0]
        logger.info(f"Extracted author from path: {author_slug}")
        return author_slug
    else:
        raise ValueError(f"Path inválido, se esperaba author/year/article/file.md: {article_path}")

def get_api_key_for_author(author_slug: str) -> str:
    """
    Obtiene la API key del autor desde las variables de entorno
    """
    env_var = AUTHOR_API_KEYS.get(author_slug)
    if not env_var:
        raise ValueError(f"Autor '{author_slug}' no tiene API key configurada en AUTHOR_API_KEYS")
    
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(f"Variable de entorno '{env_var}' no está configurada para el autor '{author_slug}'")
    
    return api_key

def notify_discord(url: str, author: str):
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook URL no configurada")
        return
    try:
        requests.post(
            DISCORD_WEBHOOK_URL, 
            json={"content": f"📢 Nuevo artículo de **{author}** en Dev.to: {url}"}, 
            timeout=10
        )
        logger.info("Discord notification sent successfully")
    except Exception as e:
        logger.error(f"Discord notification failed: {e}")

def find_changed_article():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True,
        text=True
    )
    
    logger.info(f"Git diff output:\n{result.stdout}")
    if result.stderr:
        logger.warning(f"Git diff stderr:\n{result.stderr}")
    
    changed_files = [f for f in result.stdout.strip().split("\n") if f]
    logger.info(f"Changed files count: {len(changed_files)}")
    
    for file in changed_files:
        logger.debug(f"Checking file: '{file}'")
        # Busca archivos .md que estén en la estructura author/year/article/
        if file.endswith(".md") and file.count("/") >= 2:
            article_path = Path(file)
            logger.info(f"Found potential article: {article_path}")
            if article_path.exists():
                logger.info(f"Article exists: {article_path}")
                return article_path
            else:
                logger.warning(f"Article path doesn't exist: {article_path}")
    
    logger.warning("No article found matching criteria")
    return None

def load_metadata(article_path: Path) -> dict:
    meta_path = article_path.parent / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json no encontrado junto a {article_path}")
    with meta_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def publish_article(article_path: Path):
    # Extraer autor del path
    author_slug = extract_author_from_path(article_path)
    logger.info(f"Detected author: {author_slug}")
    
    # Obtener API key correspondiente
    api_key = get_api_key_for_author(author_slug)
    logger.info(f"API key loaded for author: {author_slug}")
    
    # Body del artículo
    body_markdown = article_path.read_text(encoding="utf-8")
    logger.info(f"Article content loaded, length: {len(body_markdown)} chars")

    # Metadata asociada
    meta = load_metadata(article_path)
    logger.info(f"Metadata loaded: {meta.get('title')}")

    # Tags (pueden venir como string o lista)
    tags = meta.get("tags", "")
    if isinstance(tags, list):
        tags = ",".join(tags)

    # Imagen principal desde banner_path
    banner_path = meta.get("banner_path")
    main_image = f"{RAW_BASE}/{banner_path}?raw=true" if banner_path else None
    logger.info(f"Main image URL: {main_image}")

    payload = {
        "article": {
            "title": meta.get("title", "Sin título"),
            "body_markdown": body_markdown,
            "published": False,
            "tags": tags,
            "main_image": main_image,
            "description": "",
            "organization_id": 12123,
        }
    }

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    logger.info("Sending request to Dev.to API...")
    response = requests.post(DEVTO_API_URL, json=payload, headers=headers, timeout=10)

    if response.status_code == 201:
        article_data = response.json()
        logger.info(f"Full API response: {article_data}")
        url = article_data.get("url")
        logger.info(f"Article published successfully: {url}")
        notify_discord(url, author_slug)
    else:
        logger.error(f"API Error: {response.status_code} - {response.text}")
        raise SystemExit(1)

if __name__ == "__main__":
    try:
        logger.info("Starting Dev.to publish script")
        article = find_changed_article()
        if article:
            logger.info(f"Publishing article: {article}")
            publish_article(article)
        else:
            logger.error("No article found or file doesn't exist")
            raise SystemExit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise SystemExit(1)