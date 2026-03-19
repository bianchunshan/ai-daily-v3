const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Vercel Cron 定时更新新闻
// 文档：https://vercel.com/docs/cron-jobs

module.exports = async (req, res) => {
    try {
        console.log('=== 开始自动更新新闻 ===');
        
        // 拉取最新新闻
        const result = execSync('python3 fetch_currents_news.py', { 
            cwd: path.resolve(__dirname, '..'),
            env: {
                ...process.env,
                PYTHONIOENCODING: 'utf-8'
            }
        }).toString();
        
        console.log(result);
        
        // 检查是否生成了新的新闻数据
        const newsPath = path.join(__dirname, '..', 'news_data_api.js');
        if (!fs.existsSync(newsPath)) {
            throw new Error('新闻数据生成失败');
        }
        
        console.log('✅ 新闻数据更新成功');
        return res.status(200).json({
            success: true,
            message: '新闻更新成功',
            output: result
        });
        
    } catch (error) {
        console.error('❌ 新闻更新失败:', error);
        return res.status(500).json({
            success: false,
            error: error.message
        });
    }
};
