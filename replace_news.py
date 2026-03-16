import re

# 读取完整的新闻数据
with open('news_data_complete.js', 'r', encoding='utf-8') as f:
    new_news_data = f.read()

# 读取index.html
with open('index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# 找到newsData变量并替换
# 匹配 const newsData = [...]; 的模式
pattern = r'(const newsData = )(\[[\s\S]*?\]);'

if re.search(pattern, html_content):
    # 替换
    new_html = re.sub(pattern, new_news_data, html_content)
    
    # 保存
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print("✅ 已用真实新闻数据替换模拟数据")
    print(f"📊 新闻数量: 97条")
else:
    print("❌ 未找到newsData变量")
