import requests
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime
from html import unescape

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.0  # секунд между запросами (если нужна пагинация)
MAX_ARTICLES = None  # ограничить количество (None = все)
# ===============================

def get_article_urls_from_rss():
    """Получает список статей из RSS-фида Blogger."""
    rss_url = f"{BLOG_URL}/feeds/posts/default?alt=rss&max-results=150"
    print(f"📡 Загружаем RSS: {rss_url}")
    try:
        resp = requests.get(rss_url, timeout=10)
        if resp.status_code != 200:
            print(f"   Ошибка RSS: {resp.status_code}")
            return []
        
        # Парсим XML
        root = ET.fromstring(resp.content)
        # Пространства имён
        ns = {'': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
        # Ищем все элементы item (в RSS они называются entry, но Blogger возвращает Atom)
        # Уточним: Blogger RSS возвращает <item> внутри <channel>, но в Atom формате.
        # Проще: ищем все элементы с тегом item (в пространстве имён по умолчанию)
        items = root.findall('.//item')
        if not items:
            # Если нет, пробуем найти entry (Atom)
            items = root.findall('.//entry')
        
        articles = []
        for item in items:
            # Заголовок
            title_elem = item.find('title')
            title = title_elem.text if title_elem is not None else 'Без заголовка'
            # Ссылка
            link_elem = item.find('link')
            link = link_elem.get('href') if link_elem is not None else None
            if not link:
                # Иногда ссылка в элементе <id>
                id_elem = item.find('id')
                if id_elem is not None and id_elem.text:
                    link = id_elem.text
            # Дата публикации
            pub_date_elem = item.find('pubDate')
            if pub_date_elem is not None and pub_date_elem.text:
                # Парсим дату в формате RFC 822
                try:
                    pub_date = datetime.strptime(pub_date_elem.text, '%a, %d %b %Y %H:%M:%S %z')
                    date_str = pub_date.isoformat()
                except:
                    date_str = datetime.now().isoformat()
            else:
                date_str = datetime.now().isoformat()
            # Описание (содержимое статьи) – в элементе description
            desc_elem = item.find('description')
            content_html = desc_elem.text if desc_elem is not None else ''
            if content_html:
                # Раскодируем HTML-сущности (например, &lt; -> <)
                content_html = unescape(content_html)
            # Изображение: сначала пробуем media:thumbnail
            thumb_elem = item.find('media:thumbnail', ns)
            thumbnail = None
            if thumb_elem is not None:
                thumbnail = thumb_elem.get('url')
            else:
                # Пробуем найти первое изображение в description
                img_match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
                if img_match:
                    thumbnail = img_match.group(1)
            
            # Формируем запись
            articles.append({
                'id': f"blogger_{link.split('/')[-2] if link else 'unknown'}",
                'source': 'blogger',
                'title': title,
                'date': date_str,
                'content': content_html,
                'telegraph_url': link,
                'thumbnail': thumbnail,
                'description': content_html[:200] if content_html else title
            })
        print(f"   ✅ Найдено {len(articles)} статей в RSS")
        return articles
    except Exception as e:
        print(f"   ❌ Ошибка при загрузке RSS: {e}")
        return []

def get_all_article_urls():
    """Получает все статьи из RSS (с пагинацией, если больше 150)."""
    all_articles = []
    # Начальный URL
    url = f"{BLOG_URL}/feeds/posts/default?alt=rss&max-results=150"
    page = 1
    while url:
        print(f"📡 Загружаем страницу {page}: {url}")
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                break
            root = ET.fromstring(resp.content)
            # Ищем элементы item
            items = root.findall('.//item')
            if not items:
                items = root.findall('.//entry')
            if not items:
                break
            # Обрабатываем каждый item
            for item in items:
                title_elem = item.find('title')
                title = title_elem.text if title_elem is not None else 'Без заголовка'
                link_elem = item.find('link')
                link = link_elem.get('href') if link_elem is not None else None
                if not link:
                    id_elem = item.find('id')
                    if id_elem is not None and id_elem.text:
                        link = id_elem.text
                if not link:
                    continue
                pub_date_elem = item.find('pubDate')
                if pub_date_elem is not None and pub_date_elem.text:
                    try:
                        pub_date = datetime.strptime(pub_date_elem.text, '%a, %d %b %Y %H:%M:%S %z')
                        date_str = pub_date.isoformat()
                    except:
                        date_str = datetime.now().isoformat()
                else:
                    date_str = datetime.now().isoformat()
                desc_elem = item.find('description')
                content_html = unescape(desc_elem.text) if desc_elem is not None else ''
                thumb_elem = item.find('media:thumbnail', {'media': 'http://search.yahoo.com/mrss/'})
                thumbnail = thumb_elem.get('url') if thumb_elem is not None else None
                if not thumbnail:
                    img_match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
                    if img_match:
                        thumbnail = img_match.group(1)
                all_articles.append({
                    'id': f"blogger_{link.split('/')[-2] if link else 'unknown'}",
                    'source': 'blogger',
                    'title': title,
                    'date': date_str,
                    'content': content_html,
                    'telegraph_url': link,
                    'thumbnail': thumbnail,
                    'description': content_html[:200] if content_html else title
                })
            # Ищем ссылку на следующую страницу (в RSS нет стандартной пагинации, но у Blogger есть rel="next")
            next_link = None
            for link_elem in root.findall('.//link'):
                if link_elem.get('rel') == 'next':
                    next_link = link_elem.get('href')
                    break
            url = next_link
            page += 1
            # Небольшая пауза между запросами
            # time.sleep(REQUEST_DELAY)  # раскомментировать если нужно
        except Exception as e:
            print(f"   Ошибка: {e}")
            break
    # Удаляем дубликаты по ссылке
    seen = set()
    unique = []
    for art in all_articles:
        if art['telegraph_url'] not in seen:
            seen.add(art['telegraph_url'])
            unique.append(art)
    print(f"✅ Всего уникальных статей: {len(unique)}")
    return unique

def main():
    print("🔍 Поиск статей через RSS...")
    articles = get_all_article_urls()
    if MAX_ARTICLES and len(articles) > MAX_ARTICLES:
        articles = articles[:MAX_ARTICLES]
        print(f"⚠️ Ограничиваемся первыми {MAX_ARTICLES} статьями.")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 Готово! Сохранено {len(articles)} статей в {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
