import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin, urlparse

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.5        # секунд между запросами страниц статей
MAX_ARTICLES = None        # Ограничить количество (None = все)
# ===============================

def get_article_urls_from_homepage():
    """Получает список URL статей, парся главную страницу и все страницы архива."""
    article_urls = []
    page_num = 1
    while True:
        # Формируем URL для страницы архива. Если это первая страница, используем основной URL.
        if page_num == 1:
            page_url = BLOG_URL
        else:
            page_url = f"{BLOG_URL}/search?updated-max=2025-01-01T00:00:00-08:00&max-results=20&start={20 * (page_num - 1)}"
            # Более простой вариант, который работает почти для всех блогов Blogger:
            # page_url = f"{BLOG_URL}/page/{page_num}"
        
        print(f"📄 Загружаем страницу архива: {page_url}")
        try:
            response = requests.get(page_url, timeout=10)
            if response.status_code != 200:
                print(f"   Страница {page_num} не найдена (код {response.status_code}), останавливаемся.")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            # Ищем все ссылки, которые ведут на страницы постов
            # Обычно это <a> с href, содержащим '/year/month/post-title.html'
            links = soup.find_all('a', href=re.compile(r'/\d{4}/\d{2}/.+\.html$'))
            if not links:
                # Если не нашли по стандартному шаблону, ищем все ссылки, которые не являются внутренними для блога
                # и не ведут на главную, картинки и т.д.
                potential_links = soup.find_all('a', href=True)
                for link in potential_links:
                    href = link['href']
                    if href.startswith(BLOG_URL) and '/post/' in href:
                        links.append(link)

            if not links:
                print("   Новых ссылок на статьи не найдено. Завершаем.")
                break

            new_urls = list(set([urljoin(BLOG_URL, link['href']) for link in links]))
            article_urls.extend(new_urls)
            print(f"   Найдено {len(new_urls)} новых ссылок (всего {len(article_urls)})")
            
            # Проверяем, есть ли ссылка на следующую страницу
            next_link = soup.find('a', class_='blog-pager-older-link')
            if not next_link:
                print("   Ссылка на следующую страницу не найдена. Завершаем.")
                break
            
            page_num += 1
            # time.sleep(REQUEST_DELAY) # Раскомментируйте, если нужно добавить задержку между страницами
        except Exception as e:
            print(f"   Ошибка при загрузке страницы {page_num}: {e}")
            break
    
    # Удаляем возможные дубликаты
    article_urls = list(set(article_urls))
    return article_urls

def extract_post_data(post_url):
    """Извлекает заголовок, дату, HTML-контент и первую картинку из страницы статьи."""
    print(f"📖 Парсим: {post_url}")
    try:
        response = requests.get(post_url, timeout=15)
        if response.status_code != 200:
            print(f"   Ошибка {response.status_code}, пропускаем")
            return None
        soup = BeautifulSoup(response.text, 'html.parser')

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
        post_id_match = re.search(r'/(\d{4}/\d{2}/[^/?#]+)\.html', post_url)
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
        print(f"   Ошибка при парсинге: {e}")
        return None

def main():
    print("🔍 Поиск статей на главной странице и в архивах...")
    article_urls = get_article_urls_from_homepage()
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
