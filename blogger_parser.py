# blogger_parser.py
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin
from datetime import datetime

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.0          # секунд между запросами статей
SITEMAP_DELAY = 0.5          # между запросами страниц sitemap
MAX_ARTICLES = None          # ограничить количество (None = все)
# ===============================

def get_article_urls_from_rss():
    """Получает до 150 последних URL статей через RSS."""
    rss_url = f"{BLOG_URL}/feeds/posts/default?max-results=150&alt=rss"
    print(f"📡 Получаем статьи через RSS: {rss_url}")
    try:
        resp = requests.get(rss_url, timeout=10)
        if resp.status_code != 200:
            print(f"   Ошибка RSS: {resp.status_code}")
            return []
        # Парсим XML
        soup = BeautifulSoup(resp.text, 'xml')
        links = soup.find_all('link')
        urls = []
        for link in links:
            href = link.get('href')
            if href and '/post/' in href and href not in urls:
                urls.append(href)
        print(f"   ✅ Найдено {len(urls)} статей в RSS")
        return urls
    except Exception as e:
        print(f"   ❌ Ошибка RSS: {e}")
        return []

def get_article_urls_from_sitemap():
    """Получает URL статей через sitemap.xml (постранично)."""
    urls = []
    page = 1
    while True:
        sitemap_url = f"{BLOG_URL}/sitemap.xml?page={page}"
        print(f"📄 Загружаем sitemap: {sitemap_url}")
        try:
            resp = requests.get(sitemap_url, timeout=10)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, 'xml')
            locs = soup.find_all('loc')
            if not locs:
                break
            page_urls = [loc.text for loc in locs if '/post/' in loc.text]
            if not page_urls:
                break
            urls.extend(page_urls)
            print(f"   Страница {page}: найдено {len(page_urls)} ссылок (всего {len(urls)})")
            page += 1
            time.sleep(SITEMAP_DELAY)
        except Exception as e:
            print(f"   Ошибка sitemap: {e}")
            break
    return urls

def get_article_urls_from_pagination():
    """Получает URL статей через пагинацию /page/N (запасной вариант)."""
    urls = []
    page = 1
    while True:
        page_url = f"{BLOG_URL}/page/{page}"
        print(f"📄 Загружаем страницу пагинации: {page_url}")
        try:
            resp = requests.get(page_url, timeout=10)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Ищем ссылки на статьи (обычно содержат /year/month/title.html)
            links = soup.find_all('a', href=re.compile(r'/\d{4}/\d{2}/[^/?#]+\.html$'))
            if not links:
                # Альтернативный паттерн
                links = soup.find_all('a', href=re.compile(r'/post/[a-zA-Z0-9_-]+'))
            if not links:
                break
            page_urls = list(set([urljoin(BLOG_URL, a['href']) for a in links]))
            if not page_urls:
                break
            urls.extend(page_urls)
            print(f"   Страница {page}: найдено {len(page_urls)} ссылок (всего {len(urls)})")
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"   Ошибка: {e}")
            break
    return urls

def get_all_article_urls():
    """Объединяет все методы для получения максимального количества URL."""
    # Сначала sitemap (даёт больше всего)
    urls = get_article_urls_from_sitemap()
    if not urls:
        # Если sitemap не дал, пробуем RSS (но только последние 150)
        urls = get_article_urls_from_rss()
    # Если всё равно мало, добавляем из пагинации (может дублировать, но для полноты)
    pag_urls = get_article_urls_from_pagination()
    for u in pag_urls:
        if u not in urls:
            urls.append(u)
    print(f"✅ Всего уникальных URL статей: {len(urls)}")
    return urls

def extract_post_data(post_url):
    """Извлекает данные из страницы статьи."""
    print(f"📖 Парсим: {post_url}")
    try:
        resp = requests.get(post_url, timeout=15)
        if resp.status_code != 200:
            print(f"   Ошибка {resp.status_code}, пропускаем")
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Заголовок
        title_tag = soup.find('h1', class_='post-title') or soup.find('h1', class_='title')
        if not title_tag:
            title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else 'Без заголовка'

        # Дата
        date_tag = soup.find('time', {'datetime': True})
        if date_tag:
            date_str = date_tag['datetime']
        else:
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            date_str = meta_date['content'] if meta_date else datetime.now().isoformat()

        # Контент статьи
        content_div = soup.find('div', class_='post-body') or soup.find('div', class_='entry-content')
        if not content_div:
            content_div = soup.find('div', itemprop='articleBody')
        content_html = str(content_div) if content_div else ''

        # Первое изображение
        img_tag = content_div.find('img') if content_div else None
        thumbnail = None
        if img_tag and img_tag.get('src'):
            thumbnail = img_tag['src']
            if thumbnail.startswith('//'):
                thumbnail = 'https:' + thumbnail
            elif thumbnail.startswith('/'):
                thumbnail = urljoin(BLOG_URL, thumbnail)

        # ID статьи
        post_id_match = re.search(r'/(\d{4}/\d{2}/[^/?#]+)\.html', post_url)
        if not post_id_match:
            post_id_match = re.search(r'/post/([a-zA-Z0-9_-]+)', post_url)
        post_id = post_id_match.group(1).replace('/', '-') if post_id_match else post_url.split('/')[-2]

        return {
            'id': f"blogger_{post_id}",
            'source': 'blogger',
            'title': title,
            'date': date_str,
            'content': content_html,
            'telegraph_url': post_url,
            'thumbnail': thumbnail,
            'description': (content_html[:200] if content_html else title)
        }
    except Exception as e:
        print(f"   Ошибка: {e}")
        return None

def main():
    print("🔍 Поиск всех статей...")
    article_urls = get_all_article_urls()
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

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Готово! Сохранено {len(all_posts)} статей в {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
