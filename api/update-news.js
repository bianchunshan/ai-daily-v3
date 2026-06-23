const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Vercel Cron 定时更新新闻
// 文档：https://vercel.com/docs/cron-jobs

module.exports = async (req, res) => {
    if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
    const expected = process.env.UPDATE_NEWS_SECRET;
    if (!expected || req.headers['x-update-secret'] !== expected) {
        return res.status(401).json({ error: 'unauthorized' });
    }
    try {
        console.log('=== 开始自动更新新闻 ===');
        
        // 拉取最新新闻
        const result = execSync('python3 fetch_currents_news.py', { 
            cwd: path.resolve(__dirname, '..'),
            timeout: 120000,
            maxBuffer: 1024 * 1024,
            env: {
                ...process.env,
                PYTHONIOENCODING: 'utf-8'
            }
        }).toString();
        
        console.log(result);
        
        // 检查是否生成了新的新闻数据
        const newsPath = path.join(__dirname, '..', 'news_data_latest.js');
        if (!fs.existsSync(newsPath)) {
            throw new Error('新闻数据生成失败');
        }
        
        console.log('✅ 新闻数据更新成功');
        return res.status(200).json({
            success: true,
            message: '新闻更新成功'
        });
        
    } catch (error) {
        console.error('❌ 新闻更新失败:', error);
        return res.status(500).json({
            success: false,
            error: error.message
        });
    }
};
