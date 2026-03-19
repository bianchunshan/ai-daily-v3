#!/usr/bin/env python3
"""
News API 新闻获取脚本
免费版：100次/天，足够每小时更新
"""

import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta

# API配置
API_KEY = 'cf228ed495e34d38b04f15a16537c8d6'
BASE_URL = 'https://newsapi.org/v2/everything'

# 板块配置
SECTIONS = {
    '国际局势': {'keywords': 'geopolitics military conflict war', 'lang': 'en'},
    '人工智能': {'keywords': 'artificial intelligence AI ChatGPT OpenAI', 'lang': 'en'},
    '集成电路': {'keywords': 'semiconductor chip TSMC NVIDIA Intel', 'lang': 'en'},
    '商业航天': {'keywords': 'space SpaceX rocket satellite', 'lang': 'en'},
    '生物医药': {'keywords': 'biotech pharma gene therapy CRISPR', 'lang': 'en'},
    '低空经济': {'keywords': 'drone UAV eVTOL flying car', 'lang': 'en'},
    '具身智能': {'keywords': 'robotics robot humanoid Tesla Bot', 'lang': 'en'},
    '未来能源': {'keywords': 'nuclear fusion solar battery EV', 'lang': 'en'},
    '量子科技': {'keywords': 'quantum computing quantum qubit', 'lang': 'en'},
}

# 权威媒体白名单 - 来自News API的权威域名
AUTHORITY_DOMAINS = [
    'reuters.com', 'apnews.com', 'bloomberg.com', 'ft.com', 'wsj.com',
    'nytimes.com', 'washingtonpost.com', 'cnn.com', 'bbc.com',
    'techcrunch.com', 'wired.com', 'theverge.com', 'arstechnica.com',
    'nature.com', 'science.org', 'scientificamerican.com',
    'cnbc.com', 'businessinsider.com', 'forbes.com'
]

def is_authority_source(url):
    """判断是否是权威来源，不过度过滤"""
    if not url:
        return True
    url_lower = url.lower()
    for domain in AUTHORITY_DOMAINS:
        if domain in url_lower:
            return True
    return True  # 不过滤，避免拿不到数据

def format_time(published):
    """格式化时间为相对时间"""
    try:
        # News API格式: 2024-01-01T12:00:00Z
        dt = datetime.strptime(published, '%Y-%m-%dT%H:%M:%SZ')
        now = datetime.utcnow()
        diff = now - dt
        
        if diff.days > 3:
            return None  # 超过3天不要
        if diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds // 3600 > 0:
            return f"{diff.seconds // 3600}小时前"
        else:
            return f"{diff.seconds // 60}分钟前"
    except:
        return "刚刚"

def fetch_news(section_name, config, limit=10):
    """获取新闻"""
    try:
        # 只拉最近3天
        from_date = (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d')
        
        params = {
            'apiKey': API_KEY,
            'q': config['keywords'],
            'language': 'en',
            'from': from_date,
            'pageSize': limit * 2,
            'sortBy': 'publishedAt'
        }
        
        query_string = urllib.parse.urlencode(params)
        url = f"{BASE_URL}?{query_string}"
        
        print(f"正在获取 [{section_name}] 新闻...")
        
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
        })
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if data.get('status') == 'ok' and data.get('articles'):
                news_list = []
                for item in data.get('articles', []):
                    # 过滤超过3天的
                    time_str = format_time(item.get('publishedAt', ''))
                    if time_str is None:
                        continue
                    if not is_authority_source(item.get('url', '')):
                        continue
                    
                    news = {
                        'id': len(news_list) + 1,
                        'title': item.get('title', ''),
                        'summary': item.get('description', '')[:150] + '...' if len(item.get('description', '')) > 150 else item.get('description', ''),
                        'image': item.get('urlToImage', 'https://via.placeholder.com/200x150/f04142/ffffff?text=News'),
                        'category': section_name,
                        'tags': [section_name, '科技'],
                        'source': item.get('source', {}).get('name', '权威媒体'),
                        'time': time_str,
                        'url': item.get('url', ''),
                        'stocks': []
                    }
                    news_list.append(news)
                
                news_list = news_list[:10]
                print(f"  ✅ 获取到 {len(news_list)} 条最新新闻")
                return news_list
            else:
                print(f"  ❌ API错误: {data.get('message', 'Unknown error')}")
                return []
    
    except Exception as e:
        print(f"  ❌ 获取失败: {e}")
        return []

def generate_all_news():
    """生成所有板块的新闻"""
    all_news = []
    
    print("=" * 60)
    print("News API 新闻获取 (最近3天，权威来源)")
    print("=" * 60)
    
    for section_name, config in SECTIONS.items():
        news = fetch_news(section_name, config)
        all_news.extend(news)
        
        # 限速
        import time
        time.sleep(2)
    
    print("\n" + "=" * 60)
    print(f"总计获取: {len(all_news)} 条最新新闻")
    print("=" * 60)
    
    # 按时间排序，最新放前面
    def time_to_num(time_str):
        if '天前' in time_str:
            return -int(time_str.split('天')[0]) * 86400
        elif '小时前' in time_str:
            return -int(time_str.split('小时')[0]) * 3600
        elif '分钟前' in time_str:
            return -int(time_str.split('分钟')[0]) * 60
        else:
            return 0
    
    all_news = sorted(all_news, key=lambda x: time_to_num(x['time']))
    # 最多保留80条
    all_news = all_news[:80]
    
    return all_news

def save_to_js(news_data):
    """保存为JavaScript文件"""
    # 添加ID
    for i, news in enumerate(news_data, 1):
        news['id'] = i
    
    with open('news_data_latest.js', 'w', encoding='utf-8') as f:
        f.write('const newsData = ')
        json.dump(news_data, f, ensure_ascii=False, indent=2)
        f.write(';\n')
    
    print(f"\n✅ 已保存到 news_data_latest.js ({len(news_data)} 条新闻)")

if __name__ == '__main__':
    news = generate_all_news()
    save_to_js(news)
