// Alpha Vantage API 配置
// 申请地址：https://www.alphavantage.co/support/#api-key
// 免费版：500次/天，完全够用

const ALPHA_VANTAGE_API_KEY = 'YOUR_API_KEY_HERE'; // 替换为你的API Key

// 股票代码映射（Alpha Vantage格式）
const stockSymbols = {
    '微软': 'MSFT',
    '英伟达': 'NVDA', 
    '特斯拉': 'TSLA',
    '苹果': 'AAPL',
    '谷歌': 'GOOGL',
    '台积电': 'TSM',
    'AMD': 'AMD',
    'IBM': 'IBM',
    '亚马逊': 'AMZN',
    'Meta': 'META',
    '奈飞': 'NFLX',
    '英特尔': 'INTC',
    '高通': 'QCOM',
    '博通': 'AVGO'
};

// 获取实时股价
async function fetchStockPrice(symbol) {
    if (ALPHA_VANTAGE_API_KEY === 'YOUR_API_KEY_HERE') {
        console.log('请先配置Alpha Vantage API Key');
        return null;
    }
    
    try {
        // 全球报价接口（免费版）
        const url = `https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${ALPHA_VANTAGE_API_KEY}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data['Global Quote']) {
            const quote = data['Global Quote'];
            return {
                symbol: quote['01. symbol'],
                price: parseFloat(quote['05. price']).toFixed(2),
                change: parseFloat(quote['09. change']).toFixed(2),
                changePercent: quote['10. change percent'].replace('%', ''),
                volume: quote['06. volume'],
                latestTradingDay: quote['07. latest trading day']
            };
        }
        
        return null;
    } catch (error) {
        console.error('获取股价失败:', error);
        return null;
    }
}

// 获取历史数据（用于走势图）
async function fetchStockHistory(symbol) {
    if (ALPHA_VANTAGE_API_KEY === 'YOUR_API_KEY_HERE') {
        return null;
    }
    
    try {
        // 日K线数据
        const url = `https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=${symbol}&apikey=${ALPHA_VANTAGE_API_KEY}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data['Time Series (Daily)']) {
            const timeSeries = data['Time Series (Daily)'];
            const dates = Object.keys(timeSeries).slice(0, 30); // 最近30天
            
            return dates.map(date => ({
                date: date,
                open: parseFloat(timeSeries[date]['1. open']),
                high: parseFloat(timeSeries[date]['2. high']),
                low: parseFloat(timeSeries[date]['3. low']),
                close: parseFloat(timeSeries[date]['4. close']),
                volume: parseInt(timeSeries[date]['5. volume'])
            })).reverse();
        }
        
        return null;
    } catch (error) {
        console.error('获取历史数据失败:', error);
        return null;
    }
}

// 获取公司信息
async function fetchCompanyInfo(symbol) {
    if (ALPHA_VANTAGE_API_KEY === 'YOUR_API_KEY_HERE') {
        return null;
    }
    
    try {
        const url = `https://www.alphavantage.co/query?function=OVERVIEW&symbol=${symbol}&apikey=${ALPHA_VANTAGE_API_KEY}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.Name) {
            return {
                name: data.Name,
                description: data.Description,
                sector: data.Sector,
                industry: data.Industry,
                marketCap: data.MarketCapitalization,
                peRatio: data.PERatio,
                dividendYield: data.DividendYield,
                fiftyTwoWeekHigh: data['52WeekHigh'],
                fiftyTwoWeekLow: data['52WeekLow']
            };
        }
        
        return null;
    } catch (error) {
        console.error('获取公司信息失败:', error);
        return null;
    }
}

// 批量获取多只股票（优化API调用）
async function fetchMultipleStocks(symbols) {
    const results = {};
    
    for (const symbol of symbols) {
        const data = await fetchStockPrice(symbol);
        if (data) {
            results[symbol] = data;
        }
        // 免费版限制：每秒最多1个请求
        await new Promise(resolve => setTimeout(resolve, 1200));
    }
    
    return results;
}

// 自动刷新（每5分钟）
function startAutoRefresh() {
    // 立即执行一次
    refreshAllStocks();
    
    // 每5分钟刷新
    setInterval(refreshAllStocks, 5 * 60 * 1000);
}

// 刷新所有股票
async function refreshAllStocks() {
    const symbols = ['MSFT', 'NVDA', 'TSLA', 'AAPL', 'GOOGL', 'TSM', 'AMD', 'IBM'];
    
    console.log('开始刷新股票数据...');
    const results = await fetchMultipleStocks(symbols);
    
    // 更新到页面
    updateStockDisplay(results);
    
    console.log('股票数据刷新完成');
}

// 更新页面显示
function updateStockDisplay(stockData) {
    // 这里根据返回的数据更新页面
    // 实际实现需要根据页面结构来编写
    console.log('更新股票显示:', stockData);
}

// API Key申请说明
const apiKeyInstructions = `
=============================================
Alpha Vantage API Key 申请步骤
=============================================

1. 访问：https://www.alphavantage.co/support/#api-key

2. 填写表单：
   - First Name: 你的名字
   - Last Name: 你的姓氏
   - Email: 你的邮箱
   - Organization: 个人使用可填 "Personal"
   - Purpose: 选择 "Academic/Research" 或 "Personal"

3. 点击 "Get Free API Key"

4. 查收邮件，复制API Key

5. 替换上面代码中的：
   const ALPHA_VANTAGE_API_KEY = 'YOUR_API_KEY_HERE';
   
   改成：
   const ALPHA_VANTAGE_API_KEY = '你的真实API Key';

=============================================
免费版限制
=============================================
- 500次请求/天
- 每分钟最多5次请求
- 完全够用！（8只股票 × 每5分钟刷新1次 = 每天约230次）

=============================================
`;

console.log(apiKeyInstructions);
