import requests
import xml.etree.ElementTree as ET
import json
import re
import time
from datetime import datetime
from html import unescape

# ========== НАСТРОЙКИ ==========
BLOG_URL = 'https://sochi-autoparts.blogspot.com'
OUTPUT_FILE = 'articles.json'
REQUEST_DELAY = 1.0   # секунд между запросами (пагинация)
MAX_ARTICLES = None   # ограничить количество (None = все)
# ===============================

# Пространства имён Blogger RSS
NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'openSearch': 'http://a9.com/-/spec/opensearchrss/1.0/',
    'media': 'http://search.yahoo.com/mrss/',
    'blogger': 'http://schemas.google.com/blogger/2008',
}


def _parse_item(item):
    """Парсит один <item> из RSS-фида Blogger и возвращает словарь.

    Blogger возвращает RSS 2.0:
        <item>
            <guid isPermaLink="false">tag:blogger.com,...</guid>
            <pubDate>Mon, 20 Apr 2026 11:45:00 +0000</pubDate>
            <title>...</title>
            <description>&lt;p&gt;...HTML...&lt;/p&gt;</description>
            <link>https://blog.blogspot.com/2026/04/post.html</link>
            <media:thumbnail url="..." height="72" width="72"/>
            <author>...</author>
        </item>
    """

    # --- Заголовок ---
    title_elem = item.find('title')
    title = title_elem.text if title_elem is not None and title_elem.text else 'Без заголовка'

    # --- Ссылка ---
    # В RSS 2.0 <link> содержит URL как текст, НЕ как атрибут href!
    link_elem = item.find('link')
    link = None
    if link_elem is not None:
        link = link_elem.text  # .text, а не .get('href')
    if not link:
        # Fallback: берём <guid> (в RSS это уникальный идентификатор, а не <id>)
        guid_elem = item.find('guid')
        if guid_elem is not None and guid_elem.text:
            link = guid_elem.text
    if not link:
        return None  # не можем обработать без ссылки

    # --- Дата публикации ---
    pub_date_elem = item.find('pubDate')
    if pub_date_elem is not None and pub_date_elem.text:
        try:
            pub_date = datetime.strptime(pub_date_elem.text, '%a, %d %b %Y %H:%M:%S %z')
            date_str = pub_date.isoformat()
        except (ValueError, TypeError):
            date_str = datetime.now().isoformat()
    else:
        date_str = datetime.now().isoformat()

    # --- Содержимое (HTML из <description>) ---
    desc_elem = item.find('description')
    content_html = ''
    if desc_elem is not None and desc_elem.text:
        content_html = unescape(desc_elem.text)

    # --- Миниатюра ---
    thumbnail = None
    # Пробуем media:thumbnail
    thumb_elem = item.find('media:thumbnail', NS)
    if thumb_elem is not None:
        thumbnail = thumb_elem.get('url')
    if not thumbnail and content_html:
        # Fallback: первое изображение из контента
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        if img_match:
            thumbnail = img_match.group(1)

    # --- ID записи ---
    guid_elem = item.find('guid')
    post_id = 'unknown'
    if guid_elem is not None and guid_elem.text:
        # Формат: tag:blogger.com,1999:blog-XXX.post-YYY
        m = re.search(r'post-(\d+)$', guid_elem.text)
        if m:
            post_id = m.group(1)

    return {
        'id': f"blogger_{post_id}",
        'source': 'blogger',
        'title': title,
        'date': date_str,
        'content': content_html,
        'telegraph_url': link,
        'thumbnail': thumbnail,
        'description': content_html[:200].strip() if content_html else title,
    }


def _get_total_results(root):
    """Извлекает общее количество статей из openSearch:totalResults."""
    total_elem = root.find('.//openSearch:totalResults', NS)
    if total_elem is not None and total_elem.text:
        try:
            return int(total_elem.text)
        except ValueError:
            pass
    return None


def _get_next_page_url(root):
    """Ищет ссылку на следующую страницу (rel='next') в Atom-ссылках канала."""
    for link_elem in root.findall('.//atom:link', NS):
        if link_elem.get('rel') == 'next':
            return link_elem.get('href')
    return None


def fetch_all_articles():
    """Загружает все статьи через RSS-фид с пагинацией.

    Blogger RSS возвращает до 150 записей на страницу.
    Если статей больше, в канале появляется <atom:link rel="next" href="..."/>.
    """
    all_articles = []
    url = f"{BLOG_URL}/feeds/posts/default?alt=rss&max-results=150"
    page = 1

    while url:
        print(f"  [стр. {page}] Загружаем: {url}")
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"  [стр. {page}] Ошибка HTTP {resp.status_code} — остановка.")
                break

            root = ET.fromstring(resp.content)

            # Выводим общее количество статей (на первой странице)
            if page == 1:
                total = _get_total_results(root)
                if total is not None:
                    print(f"  Всего статей в блоге: {total}")

            # Ищем <item> внутри <channel>
            channel = root.find('channel')
            if channel is None:
                print(f"  [стр. {page}] Не найден <channel> — остановка.")
                break

            items = channel.findall('item')
            if not items:
                print(f"  [стр. {page}] Нет <item> — всё загружено.")
                break

            page_articles = []
            for item in items:
                article = _parse_item(item)
                if article is not None:
                    page_articles.append(article)

            print(f"  [стр. {page}] Обработано {len(page_articles)} статей")
            all_articles.extend(page_articles)

            # Ищем ссылку на следующую страницу
            next_url = _get_next_page_url(root)
            if next_url:
                url = next_url
                page += 1
                time.sleep(REQUEST_DELAY)  # пауза между страницами
            else:
                print(f"  [стр. {page}] Следующая страница не найдена — загрузка завершена.")
                url = None

        except requests.Timeout:
            print(f"  [стр. {page}] Таймаут запроса — остановка.")
            break
        except ET.ParseError as e:
            print(f"  [стр. {page}] Ошибка парсинга XML: {e}")
            break
        except Exception as e:
            print(f"  [стр. {page}] Ошибка: {e}")
            break

    # Удаляем дубликаты по ссылке
    seen = set()
    unique = []
    for art in all_articles:
        if art['telegraph_url'] not in seen:
            seen.add(art['telegraph_url'])
            unique.append(art)

    print(f"\n  Уникальных статей: {len(unique)} (из {len(all_articles)} загруженных)")
    return unique


def main():
    print("=" * 60)
    print("  Парсер Blogger RSS: sochi-autoparts.blogspot.com")
    print("=" * 60)
    print(f"  Блог: {BLOG_URL}")
    print(f"  Вывод: {OUTPUT_FILE}")
    if MAX_ARTICLES:
        print(f"  Лимит: {MAX_ARTICLES} статей")
    print("-" * 60)

    articles = fetch_all_articles()

    # Ограничение количества (если задано)
    if MAX_ARTICLES and len(articles) > MAX_ARTICLES:
        articles = articles[:MAX_ARTICLES]
        print(f"\n  Ограничение: оставляем первые {MAX_ARTICLES} статей.")

    # Сохраняем в JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n  Готово! Сохранено {len(articles)} статей в {OUTPUT_FILE}")
    print("=" * 60)

    # Краткая статистика
    if articles:
        print("\n  Первые 5 статей:")
        for i, art in enumerate(articles[:5], 1):
            date_short = art['date'][:10]
            print(f"    {i}. [{date_short}] {art['title'][:70]}")


if __name__ == '__main__':
    main()
