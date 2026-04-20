import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.5          # секунд между запросами к страницам статей
SITEMAP_DELAY = 0.5          # секунд между запросами страниц sitemap
MAX_ARTICLES = None          # если нужно ограничить количество (None = все)
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
# ===============================

def get_sitemap_urls():
    """Получает все URL статей из sitemap Blogger (постранично)."""
    article_urls = []
    page = 1
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    while True:
        sitemap_page_url = f"{BLOG_URL}/sitemap.xml?page={page}"
        print(f"📄 Загружаем sitemap: {sitemap_page_url}")
        try:
            resp = session.get(sitemap_page_url, timeout=10)
            if resp.status_code != 200:
                print(f"   Страница {page} не найдена (код {resp.status_code}), останавливаемся.")
                break
            soup = BeautifulSoup(resp.text, 'xml')
            # Ищем все теги <loc>
            locs = soup.find_all('loc')
            if not locs:
                print("   Нет ссылок, выходим.")
                break
            # Фильтруем только посты (содержат '/post/')
            urls_on_page = [loc.text for loc in locs if '/post/' in loc.text]
            if not urls_on_page:
                break
            article_urls.extend(urls_on_page)
            print(f"   Найдено {len(urls_on_page)} ссылок (всего {len(article_urls)})")
            page += 1
            time.sleep(SITEMAP_DELAY)
        except Exception as e:
            print(f"   Ошибка при загрузке sitemap: {e}")
            break
    return article_urls

def extract_post_data(post_url):
    """Загружает страницу статьи и извлекает заголовок, дату, контент, первую картинку."""
    print(f"📖 Парсим: {post_url}")
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    try:
        resp = session.get(post_url, timeout=15)
        if resp.status_code != 200:
            print(f"   Ошибка {resp.status_code}, пропускаем")
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Заголовок – часто в <h1 class='post-title'>
        title_tag = soup.find('h1', class_='post-title') or soup.find('h1', class_='title')
        if not title_tag:
            title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else 'Без заголовка'

        # Дата – ищем <time> или <span class='publishdate'>
        date_tag = soup.find('time', {'datetime': True}) or soup.find('span', class_='publishdate')
        if date_tag and date_tag.get('datetime'):
            date_str = date_tag['datetime']
        elif date_tag:
            date_str = date_tag.get_text(strip=True)
        else:
            # fallback: мета-тег article:published_time
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            date_str = meta_date['content'] if meta_date else None
        if not date_str:
            date_str = '1970-01-01T00:00:00Z'

        # Контент статьи – внутри <div class='post-body'> или <div class='entry-content'>
        content_div = soup.find('div', class_='post-body') or soup.find('div', class_='entry-content')
        if not content_div:
            content_div = soup.find('div', itemprop='articleBody')
        content_html = str(content_div) if content_div else ''

        # Первое изображение (для превью)
        img_tag = None
        if content_div:
            img_tag = content_div.find('img')
        thumbnail = None
        if img_tag and img_tag.get('src'):
            thumbnail = img_tag['src']
            if thumbnail.startswith('//'):
                thumbnail = 'https:' + thumbnail
            elif thumbnail.startswith('/'):
                thumbnail = urljoin(BLOG_URL, thumbnail)

        # ID статьи из URL (например, /post/1234567890 или /2025/04/post-name.html)
        # Попробуем взять последнюю часть URL
        post_id_match = re.search(r'/post/([a-zA-Z0-9_-]+)', post_url)
        if not post_id_match:
            post_id_match = re.search(r'/(\d{10,})(?:[/?#]|$)', post_url)
        post_id = post_id_match.group(1) if post_id_match else post_url.split('/')[-2]

        return {
            'id': f"blogger_{post_id}",
            'source': 'blogger',
            'title': title,
            'date': date_str,
            'content': content_html,
            'telegraph_url': post_url,
            'thumbnail': thumbnail,
            'description': (content_html[:200] if content_html else title),
        }
    except Exception as e:
        print(f"   Ошибка при парсинге {post_url}: {e}")
        return None

def main():
    print("🔍 Получаем список всех статей из sitemap...")
    article_urls = get_sitemap_urls()
    print(f"✅ Найдено всего статей: {len(article_urls)}")

    if MAX_ARTICLES and len(article_urls) > MAX_ARTICLES:
        article_urls = article_urls[:MAX_ARTICLES]
        print(f"⚠️ Ограничиваемся первыми {MAX_ARTICLES} статьями.")

    all_posts = []
    for i, url in enumerate(article_urls, 1):
        print(f"\n[{i}/{len(article_urls)}]")
        post_data = extract_post_data(url)
        if post_data:
            all_posts.append(post_data)
        time.sleep(REQUEST_DELAY)

    # Сохраняем в JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Готово! Сохранено {len(all_posts)} статей в {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
