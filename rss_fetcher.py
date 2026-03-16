#!/usr/bin/env python3
"""
RSS新闻抓取脚本
从权威科技媒体抓取真实新闻
无API次数限制，完全免费
"""

import feedparser
import json
from datetime import datetime
from html.parser import HTMLParser

class HTMLStripper(HTMLParser):
    """去除HTML标签"""
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
    
    def handle_data(self, d):
        self.fed.append(d)
    
    def get_data(self):
        return ''.join(self.fed)

def strip_html(html):
    """去除HTML标签"""
    s = HTMLStripper()
    try:
        s.feed(html)
        return s.get_data()
    except:
        return html

def truncate_text(text, max_length=100):
    """截断文本"""
    if len(text) > max_length:
        return text[:max_length] + '...'
    return text

def parse_date(date_str):
    """解析日期"""
    try:
        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
        return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return date_str

# RSS源配置
RSS_SOURCES = {
    '国际局势': [
        'https://www.thepaper.cn/rssNews.xml',  # 澎湃新闻
    ],
    '人工智能': [
        'https://www.jiqizhixin.com/rss',  # 机器之心
        'https://36kr.com/feed',  # 36氪
    ],
    '半导体': [
        'https://www.cs.com.cn/rss.shtml',  # 证券时报
    ],
    '新能源': [
        'https://www.cls.cn/rss',  # 财联社
    ],
    '机器人': [
        'https://www.jiqizhixin.com/rss',  # 机器之心
    ],
    '生物科技': [
        'https://www.biodiscover.com/rss',  # 生物探索
    ],
    '量子计算': [
        'https://www.jiqizhixin.com/rss',  # 机器之心
    ],
    '商业航天': [
        'https://www.spacechina.com/rss',  # 中国航天
    ],
    '核聚变': [
        'https://www.cas.cn/rss',  # 中国科学院
    ],
    '消费电子': [
        'https://www.ithome.com/rss',  # IT之家
    ]
}

def fetch_rss_news(category, limit=20):
    """从RSS获取新闻"""
    news_list = []
    
    if category not in RSS_SOURCES:
        return news_list
    
    for rss_url in RSS_SOURCES[category]:
        try:
            print(f"正在抓取: {rss_url}")
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:limit]:
                news = {
                    'title': entry.get('title', ''),
                    'summary': truncate_text(strip_html(entry.get('summary', entry.get('description', '')))),
                    'link': entry.get('link', ''),
                    'published': parse_date(entry.get('published', '')),
                    'source': feed.feed.get('title', '未知来源'),
                    'category': category
                }
                news_list.append(news)
        
        except Exception as e:
            print(f"抓取失败 {rss_url}: {e}")
    
    return news_list[:limit]

def generate_news_data():
    """生成所有板块的新闻数据"""
    all_news = {}
    
    categories = [
        '国际局势', '人工智能', '半导体', '新能源', '机器人',
        '生物科技', '量子计算', '商业航天', '核聚变', '消费电子'
    ]
    
    for category in categories:
        print(f"\n=== 正在抓取 [{category}] ===")
        news = fetch_rss_news(category, 20)
        all_news[category] = news
        print(f"获取到 {len(news)} 条新闻")
    
    return all_news

if __name__ == '__main__':
    print("=" * 60)
    print("RSS新闻抓取工具")
    print("=" * 60)
    
    news_data = generate_news_data()
    
    # 保存到文件
    with open('rss_news_data.json', 'w', encoding='utf-8') as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("抓取完成！数据已保存到 rss_news_data.json")
    print("=" * 60)
    
    # 统计
    total = sum(len(v) for v in news_data.values())
    print(f"\n总计获取: {total} 条新闻")
    for cat, news in news_data.items():
        print(f"  {cat}: {len(news)} 条")
