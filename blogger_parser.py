import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.0        # секунд между запросами страниц статей
MAX_ARTICLES = None        # ограничить количество (None = все)
# ===============================

def get_article_urls_from_rss():
    """Получает список URL статей через RSS-ленту (быстро, но не более 150)."""
    rss_url = f"{BLOG_URL}/feeds/posts/default?max-results=150&alt=rss"
    print(f"📡 Пробуем получить статьи через RSS: {rss_url}")
    try:
        resp = requests.get(rss_url, timeout=10)
        if resp.status_code != 200:
            print("   RSS-лента не найдена")
            return []
        soup = BeautifulSoup(resp.text, 'xml')
        links = soup.find_all('link')
        article_urls = []
        for link in links:
            href = link.get('href')
            if href and '/post/' in href and href not in article_urls:
                article_urls.append(href)
        print(f"   ✅ Найдено {len(article_urls)} статей в RSS")
        return article_urls
    except Exception as e:
        print(f"   ❌ Ошибка при загрузке RSS: {e}")
        return []

def get_article_urls_from_sitemap():
    """Получает все URL статей через sitemap.xml (постранично, до 500)."""
    article_urls = []
    page = 1
    while True:
        sitemap_page_url = f"{BLOG_URL}/sitemap.xml?page={page}"
        print(f"📄 Загружаем sitemap: {sitemap_page_url}")
        try:
            resp = requests.get(sitemap_page_url, timeout=10)
            if resp.status_code != 200:
                break
            # Парсим XML с помощью 'xml'
            soup = BeautifulSoup(resp.text, 'xml')
            locs = soup.find_all('loc')
            if not locs:
                break
            urls_on_page = [loc.text for loc in locs if '/post/' in loc.text]
            if not urls_on_page:
                break
            article_urls.extend(urls_on_page)
            print(f"   Найдено {len(urls_on_page)} ссылок (всего {len(article_urls)})")
            page += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"   ❌ Ошибка при загрузке sitemap: {e}")
            break
    return article_urls

def extract_post_data(post_url):
    """Извлекает заголовок, дату, HTML-контент и первую картинку из страницы статьи."""
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
        date_tag = soup.find('time', {'datetime': True}) or soup.find('span', class_='publishdate')
        if date_tag and date_tag.get('datetime'):
            date_str = date_tag['datetime']
        else:
            meta_date = soup.find('meta', {'property': 'article:published_time'})
            date_str = meta_date['content'] if meta_date else '1970-01-01T00:00:00Z'

        # Контент статьи
        content_div = soup.find('div', class_='post-body') or soup.find('div', class_='entry-content')
        if not content_div:
            content_div = soup.find('div', itemprop='articleBody')
        content_html = str(content_div) if content_div else ''

        # Первое изображение (превью)
        img_tag = content_div.find('img') if content_div else None
        thumbnail = None
        if img_tag and img_tag.get('src'):
            thumbnail = img_tag['src']
            if thumbnail.startswith('//'):
                thumbnail = 'https:' + thumbnail
            elif thumbnail.startswith('/'):
                thumbnail = urljoin(BLOG_URL, thumbnail)

        # ID статьи из URL
        post_id_match = re.search(r'/post/([a-zA-Z0-9_-]+)', post_url)
        post_id = post_id_match.group(1) if post_id_match else post_url.split('/')[-2]

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
        print(f"   ❌ Ошибка при парсинге: {e}")
        return None

def main():
    print("🔍 Поиск статей...")
    # Сначала пробуем RSS (быстро, до 150 статей)
    article_urls = get_article_urls_from_rss()
    # Если RSS не дал результатов, пробуем sitemap (до 500)
    if not article_urls:
        article_urls = get_article_urls_from_sitemap()
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

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Готово! Сохранено {len(all_posts)} статей в {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
