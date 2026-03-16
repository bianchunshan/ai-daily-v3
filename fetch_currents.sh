#!/bin/bash
# Currents API 批量获取脚本
# 限制：20次/天，需要高效利用

API_KEY="Zgk7l7N-kQp6UYGyZ6RXRmkv8TH1_Ohn7O7ai8AGLDXqzCiC"
BASE_URL="https://api.currentsapi.services/v1"

echo "=========================================="
echo "Currents API 新闻获取"
echo "限制：20次/天"
echo "=========================================="
echo ""

# 只获取最热门的几个板块（节省API调用）
# 策略：一次请求获取所有新闻，然后本地分类

echo "正在获取科技新闻（最新100条）..."

# 获取最新科技新闻（1次API调用获取100条）
curl -s "${BASE_URL}/latest-news?apiKey=${API_KEY}&category=technology&language=en&page_size=100" \
  -H "User-Agent: Mozilla/5.0" > /tmp/tech_news.json

if [ $? -eq 0 ]; then
    echo "✅ 获取成功"
    
    # 统计数量
    count=$(cat /tmp/tech_news.json | grep -o '"id"' | wc -l)
    echo "获取到 ${count} 条新闻"
    
    # 保存
    cp /tmp/tech_news.json currents_tech_news.json
    echo "✅ 已保存到 currents_tech_news.json"
else
    echo "❌ 获取失败"
fi

echo ""
echo "=========================================="
echo "获取完成！剩余可用次数：约19次"
echo "=========================================="
