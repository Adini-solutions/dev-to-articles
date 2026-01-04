import os
import json
import requests
import subprocess
from pathlib import Path

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DEVTO_API_URL = "https://dev.to/api/articles"
RAW_BASE = "https://raw.githubusercontent.com/adini/dev-to-articles/main"

# Mapeo de author_slug a nombre de variable de entorno
AUTHOR_API_KEYS = {
    "agustin-ezequiel-acevedo": "DEVTO_API_KEY_AGUS",
    "otro-autor": "DEVTO_API_KEY_OTRO",
    # Agregar más autores aquí
}

def extract_author_from_path(article_path: Path) -> str:
    """
    Extrae el author_slug del path: dev-to-articles/{author}/{year}/article/
    """
    parts = article_path.parts
    try:
        # Busca 'dev-to-articles' y toma el siguiente elemento
        articles_idx = parts.index("dev-to-articles")
        author_slug = parts[articles_idx + 1]
        return author_slug
    except (ValueError, IndexError):
        raise ValueError(f"No se pudo extraer el autor del path: {article_path}")

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
        return
    try:
        requests.post(
            DISCORD_WEBHOOK_URL, 
            json={"content": f"📢 Nuevo artículo de **{author}** en Dev.to: {url}"}, 
            timeout=10
        )
    except Exception as e:
        print(f"Discord notification failed: {e}")

def find_changed_article():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True,
        text=True
    )
    for file in result.stdout.split("\n"):
        if file.endswith(".md") and "/articles/" in file:
            article_path = Path(file)
            if article_path.exists():
                return article_path
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
    print(f"Detected author: {author_slug}")
    
    # Obtener API key correspondiente
    api_key = get_api_key_for_author(author_slug)
    
    # Body del artículo
    body_markdown = article_path.read_text(encoding="utf-8")

    # Metadata asociada
    meta = load_metadata(article_path)

    # Tags (pueden venir como string o lista)
    tags = meta.get("tags", "")
    if isinstance(tags, list):
        tags = ",".join(tags)

    # Imagen principal desde banner_path
    banner_path = meta.get("banner_path")
    main_image = f"{RAW_BASE}/{banner_path}" if banner_path else None

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

    response = requests.post(DEVTO_API_URL, json=payload, headers=headers, timeout=10)

    if response.status_code == 201:
        url = response.json().get("url")
        print(f"Article published: {url}")
        notify_discord(url, author_slug)
    else:
        print(f"Error: {response.status_code} - {response.text}")
        raise SystemExit(1)

if __name__ == "__main__":
    try:
        article = find_changed_article()
        if article:
            print(f"Publishing: {article}")
            publish_article(article)
        else:
            print("No article found or file doesn't exist")
            raise SystemExit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        raise SystemExit(1)