"""Run against a started dev server or deployment; never invokes paid AI calls."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:4193')
    parser.add_argument('--output', default='.test-output/browser')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000},
                                          locale='zh-CN', timezone_id='America/Los_Angeles')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.base, wait_until='networkidle')
            page.locator('#tabs button[data-cat="量子科技"]').click()
            page.wait_for_function("document.getElementById('feedTitle').textContent==='量子科技'")
            recent = page.locator('#resultCount').inner_text()
            page.locator('#scopeFilter button[data-archive="1"]').click()
            page.wait_for_function("document.querySelectorAll('.item').length===40 && document.querySelector('#scopeFilter [data-archive=\"1\"]').getAttribute('aria-pressed')==='true'")
            archive = page.locator('#resultCount').inner_text()
            page.locator('#more').click()
            page.wait_for_function("document.querySelectorAll('.item').length===80")
            target = page.locator('.item-title').nth(60)
            target.scroll_into_view_if_needed()
            before_scroll = page.evaluate('scrollY')
            before_url = page.url
            target.click()
            page.wait_for_selector('.article-body')
            page.wait_for_load_state('networkidle')
            page.get_by_role('button', name='返回', exact=True).click()
            page.wait_for_function("document.querySelectorAll('.item').length===80")
            page.wait_for_function('(y) => Math.abs(scrollY-y)<150', arg=before_scroll)
            assert page.url == before_url
            assert page.locator('#feedTitle').inner_text() == '量子科技'
            result['archive'] = {'recent': recent, 'archived': archive, 'restoredItems': 80,
                                 'scrollBefore': before_scroll, 'scrollAfter': page.evaluate('scrollY')}
            page.locator('#more').click()
            page.wait_for_function("document.querySelectorAll('.item').length>80")
            result['archive']['continuedItems'] = page.locator('.item').count()

            page.goto(args.base, wait_until='networkidle')
            page.locator('#searchBtn').click()
            page.locator('#searchInput').fill('量子')
            page.wait_for_function("document.getElementById('feedTitle').textContent==='搜索结果'")
            count = page.locator('#resultCount').inner_text()
            page.locator('.item-title').first.click()
            page.wait_for_selector('.article-body')
            page.get_by_role('button', name='返回', exact=True).click()
            page.wait_for_function("document.getElementById('feedTitle').textContent==='搜索结果'")
            assert page.locator('#searchBar').is_visible()
            assert page.locator('#searchInput').input_value() == '量子'
            assert page.locator('#resultCount').inner_text() == count
            page.reload(wait_until='networkidle')
            assert page.locator('#searchInput').input_value() == '量子'
            assert page.locator('#feedTitle').inner_text() == '搜索结果'
            result['search'] = {'restoredCount': count, 'url': page.url}

            page.locator('.save-btn').first.click()
            page.locator('#savedBtn').click()
            page.wait_for_function("document.getElementById('feedTitle').textContent==='我的收藏'")
            page.locator('.item-title').first.click()
            page.wait_for_selector('.article-body')
            page.get_by_role('button', name='返回', exact=True).click()
            page.wait_for_function("document.getElementById('feedTitle').textContent==='我的收藏'")
            assert page.locator('.item').count() == 1
            result['bookmarks'] = 'restored'
            page.route('**/api/news?**', lambda route: route.abort())
            page.goto(args.base + '/?saved=1', wait_until='networkidle')
            assert page.locator('.item').count() == 1
            page.locator('.save-btn').first.click()
            assert page.locator('#resultCount').inner_text() == '0 条'
            page.unroute('**/api/news?**')
            result['bookmarksOffline'] = 'passed'

            response = context.request.get(args.base + '/api/news?from=2026-10-03&to=2026-10-03&limit=60')
            assert response.ok
            items = response.json()['items']
            assert items
            from datetime import datetime, timezone, timedelta
            zone = timezone(timedelta(hours=8))
            assert all(datetime.fromisoformat(n['ts'].replace('Z', '+00:00')).astimezone(zone).date().isoformat() == '2026-10-03' for n in items)
            bad = context.request.get(args.base + '/api/news?from=2026-10-04&to=2026-10-03')
            assert bad.status == 400
            result['date'] = {'checked': len(items), 'invalidRangeStatus': bad.status}
            assert not errors, errors
            context.close()

            for width, height in [(1440, 1000), (390, 844), (320, 640)]:
                context = browser.new_context(viewport={'width': width, 'height': height},
                                              is_mobile=width < 500, has_touch=width < 500,
                                              locale='zh-CN', timezone_id='Asia/Shanghai')
                page = context.new_page()
                page.goto(args.base + '/?from=2026-10-03&to=2026-10-03', wait_until='networkidle')
                page.wait_for_selector('.item-title')
                assert page.locator('#searchBar').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output / f'filters-{width}.png'))
                page.goto(args.base, wait_until='networkidle')
                page.locator('#updateStatus').click()
                assert '重试耗尽' in page.locator('#updateInfo').inner_text()
                page.screenshot(path=str(output / f'home-{width}.png'))
                page.locator('#chatBtn').click()
                send = page.locator('#chatSend').bounding_box()
                assert send['x'] + send['width'] <= width
                assert send['y'] + send['height'] <= height
                page.screenshot(path=str(output / f'chat-{width}.png'))
                result[str(width)] = {'layout': 'passed', 'status': page.locator('#updateStatus').inner_text()}
                context.close()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
