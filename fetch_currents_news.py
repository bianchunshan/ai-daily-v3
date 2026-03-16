#!/usr/bin/env python3
"""
Currents API 新闻获取脚本
使用 currentsapi.services
免费版：20次/天
"""

import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta

# API配置
API_KEY = 'Zgk7l7N-kQp6UYGyZ6RXRmkv8TH1_Ohn7O7ai8AGLDXqzCiC'
BASE_URL = 'https://api.currentsapi.services/v1'

# 板块配置
SECTIONS = {
    '国际局势': {'keywords': 'geopolitics OR military OR conflict OR war', 'category': 'world'},
    '人工智能': {'keywords': 'artificial intelligence OR AI OR ChatGPT OR OpenAI', 'category': 'technology'},
    '集成电路': {'keywords': 'semiconductor OR chip OR TSMC OR NVIDIA OR Intel', 'category': 'technology'},
    '商业航天': {'keywords': 'space OR SpaceX OR rocket OR satellite', 'category': 'science'},
    '生物医药': {'keywords': 'biotech OR pharma OR gene therapy OR CRISPR', 'category': 'science'},
    '低空经济': {'keywords': 'drone OR UAV OR eVTOL OR flying car', 'category': 'technology'},
    '具身智能': {'keywords': 'robotics OR robot OR humanoid OR Tesla Bot', 'category': 'technology'},
    '未来能源': {'keywords': 'nuclear fusion OR solar OR battery OR EV', 'category': 'science'},
    '量子科技': {'keywords': 'quantum computing OR quantum OR qubit', 'category': 'science'},
}

def fetch_news(section_name, config, limit=20):
    """获取新闻"""
    try:
        # 构建请求URL
        params = {
            'apiKey': API_KEY,
            'keywords': config['keywords'],
            'category': config['category'],
            'language': 'en',
            'page_size': limit
        }
        
        query_string = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/search?{query_string}"
        
        print(f"正在获取 [{section_name}] 新闻...")
        
        # 发送请求
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
        })
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if data.get('status') == 'ok':
                news_list = []
                for item in data.get('news', []):
                    news = {
                        'title': item.get('title', ''),
                        'summary': item.get('description', '')[:150] + '...' if len(item.get('description', '')) > 150 else item.get('description', ''),
                        'image': item.get('image', 'https://via.placeholder.com/200x150/f04142/ffffff?text=News'),
                        'category': section_name,
                        'tags': [section_name, '科技'],
                        'source': item.get('author', 'Currents API'),
                        'time': format_time(item.get('published', '')),
                        'url': item.get('url', ''),
                        'stocks': []
                    }
                    news_list.append(news)
                
                print(f"  ✅ 获取到 {len(news_list)} 条新闻")
                return news_list
            else:
                print(f"  ❌ API错误: {data.get('message', 'Unknown error')}")
                return []
    
    except Exception as e:
        print(f"  ❌ 获取失败: {e}")
        return []

def format_time(published):
    """格式化时间"""
    try:
        # Currents API时间格式: 2024-01-01 12:00:00 +0000
        dt = datetime.strptime(published[:19], '%Y-%m-%d %H:%M:%S')
        # 转换为相对时间
        now = datetime.utcnow()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds // 3600 > 0:
            return f"{diff.seconds // 3600}小时前"
        else:
            return f"{diff.seconds // 60}分钟前"
    except:
        return "刚刚"

def generate_all_news():
    """生成所有板块的新闻"""
    all_news = []
    
    print("=" * 60)
    print("Currents API 新闻获取")
    print("=" * 60)
    
    for section_name, config in SECTIONS.items():
        news = fetch_news(section_name, config, 20)
        all_news.extend(news)
        
        # 免费版限制，不要请求太快
        import time
        time.sleep(2)
    
    print("\n" + "=" * 60)
    print(f"总计获取: {len(all_news)} 条新闻")
    print("=" * 60)
    
    return all_news

def save_to_js(news_data):
    """保存为JavaScript文件"""
    # 添加ID
    for i, news in enumerate(news_data, 1):
        news['id'] = i
    
    # 保存为JS文件
    with open('news_data_api.js', 'w', encoding='utf-8') as f:
        f.write('const newsData = ')
        json.dump(news_data, f, ensure_ascii=False, indent=2)
        f.write(';\n')
    
    print(f"\n✅ 已保存到 news_data_api.js ({len(news_data)} 条新闻)")

if __name__ == '__main__':
    news = generate_all_news()
    save_to_js(news)
