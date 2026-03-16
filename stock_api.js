// Alpha Vantage API 配置
// 已配置真实API Key
const ALPHA_VANTAGE_CONFIG = {
    API_KEY: '2F0RW04NVUB5KYXF',
    BASE_URL: 'https://www.alphavantage.co/query',
    RATE_LIMIT: 1200, // 每秒最多1次请求，间隔1.2秒
    DAILY_LIMIT: 500  // 每日500次限制
};

// 股票代码映射
const stockSymbols = {
    'MSFT': { name: '微软', chineseName: '微软公司' },
    'NVDA': { name: '英伟达', chineseName: '英伟达' },
    'TSLA': { name: '特斯拉', chineseName: '特斯拉' },
    'AAPL': { name: '苹果', chineseName: '苹果公司' },
    'GOOGL': { name: '谷歌', chineseName: '谷歌(Alphabet)' },
    'TSM': { name: '台积电', chineseName: '台积电' },
    'AMD': { name: 'AMD', chineseName: 'AMD' },
    'IBM': { name: 'IBM', chineseName: 'IBM' },
    'AMZN': { name: '亚马逊', chineseName: '亚马逊' },
    'META': { name: 'Meta', chineseName: 'Meta' },
    'NFLX': { name: '奈飞', chineseName: '奈飞' },
    'INTC': { name: '英特尔', chineseName: '英特尔' },
    'QCOM': { name: '高通', chineseName: '高通' },
    'AVGO': { name: '博通', chineseName: '博通' }
};

// 获取实时股价
async function fetchStockPrice(symbol) {
    try {
        const url = `${ALPHA_VANTAGE_CONFIG.BASE_URL}?function=GLOBAL_QUOTE&symbol=${symbol}&apikey=${ALPHA_VANTAGE_CONFIG.API_KEY}`;
        
        console.log(`正在获取 ${symbol} 股价...`);
        const response = await fetch(url);
        const data = await response.json();
        
        if (data['Global Quote'] && data['Global Quote']['05. price']) {
            const quote = data['Global Quote'];
            const price = parseFloat(quote['05. price']);
            const change = parseFloat(quote['09. change']);
            const changePercent = quote['10. change percent'].replace('%', '');
            
            return {
                symbol: symbol,
                name: stockSymbols[symbol]?.name || symbol,
                price: price.toFixed(2),
                change: change.toFixed(2),
                changePercent: changePercent,
                changeValue: (change >= 0 ? '+' : '') + change.toFixed(2),
                trend: change >= 0 ? 'up' : 'down',
                volume: parseInt(quote['06. volume']).toLocaleString(),
                latestTradingDay: quote['07. latest trading day'],
                open: parseFloat(quote['02. open']).toFixed(2),
                high: parseFloat(quote['03. high']).toFixed(2),
                low: parseFloat(quote['04. low']).toFixed(2),
                timestamp: new Date().toISOString()
            };
        } else if (data['Note']) {
            console.warn('API频率限制:', data['Note']);
            return { error: 'RATE_LIMIT', message: 'API请求频率限制，请稍后再试' };
        } else {
            console.error('API返回数据异常:', data);
            return null;
        }
    } catch (error) {
        console.error(`获取 ${symbol} 股价失败:`, error);
        return null;
    }
}

// 获取历史数据（用于走势图）
async function fetchStockHistory(symbol, days = 30) {
    try {
        const url = `${ALPHA_VANTAGE_CONFIG.BASE_URL}?function=TIME_SERIES_DAILY&symbol=${symbol}&apikey=${ALPHA_VANTAGE_CONFIG.API_KEY}`;
        
        console.log(`正在获取 ${symbol} 历史数据...`);
        const response = await fetch(url);
        const data = await response.json();
        
        if (data['Time Series (Daily)']) {
            const timeSeries = data['Time Series (Daily)'];
            const dates = Object.keys(timeSeries).slice(0, days).sort();
            
            return dates.map(date => ({
                date: date,
                open: parseFloat(timeSeries[date]['1. open']),
                high: parseFloat(timeSeries[date]['2. high']),
                low: parseFloat(timeSeries[date]['3. low']),
                close: parseFloat(timeSeries[date]['4. close']),
                volume: parseInt(timeSeries[date]['5. volume'])
            }));
        } else if (data['Note']) {
            console.warn('API频率限制:', data['Note']);
            return { error: 'RATE_LIMIT' };
        } else {
            console.error('API返回数据异常:', data);
            return null;
        }
    } catch (error) {
        console.error(`获取 ${symbol} 历史数据失败:`, error);
        return null;
    }
}

// 获取公司信息
async function fetchCompanyInfo(symbol) {
    try {
        const url = `${ALPHA_VANTAGE_CONFIG.BASE_URL}?function=OVERVIEW&symbol=${symbol}&apikey=${ALPHA_VANTAGE_CONFIG.API_KEY}`;
        
        console.log(`正在获取 ${symbol} 公司信息...`);
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.Name) {
            return {
                name: data.Name,
                chineseName: stockSymbols[symbol]?.chineseName || data.Name,
                description: data.Description,
                sector: data.Sector,
                industry: data.Industry,
                marketCap: (parseInt(data.MarketCapitalization) / 1000000000).toFixed(2) + 'B',
                marketCapFull: data.MarketCapitalization,
                peRatio: data.PERatio,
                dividendYield: data.DividendYield ? (parseFloat(data.DividendYield) * 100).toFixed(2) + '%' : 'N/A',
                fiftyTwoWeekHigh: data['52WeekHigh'],
                fiftyTwoWeekLow: data['52WeekLow'],
                country: data.Country,
                currency: data.Currency
            };
        } else if (data['Note']) {
            console.warn('API频率限制:', data['Note']);
            return { error: 'RATE_LIMIT' };
        } else {
            return null;
        }
    } catch (error) {
        console.error(`获取 ${symbol} 公司信息失败:`, error);
        return null;
    }
}

// 延迟函数
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 批量获取多只股票（带频率控制）
async function fetchMultipleStocks(symbols) {
    const results = {};
    
    for (const symbol of symbols) {
        const data = await fetchStockPrice(symbol);
        if (data && !data.error) {
            results[symbol] = data;
        }
        // 免费版限制：每秒最多1个请求，间隔1.2秒
        await sleep(ALPHA_VANTAGE_CONFIG.RATE_LIMIT);
    }
    
    return results;
}

// 获取单个股票完整信息
async function fetchStockFullData(symbol) {
    console.log(`=== 获取 ${symbol} 完整数据 ===`);
    
    // 并行获取基础信息
    const [priceData, companyInfo] = await Promise.all([
        fetchStockPrice(symbol),
        fetchCompanyInfo(symbol)
    ]);
    
    if (priceData && !priceData.error) {
        return {
            ...priceData,
            company: companyInfo
        };
    }
    
    return null;
}

// 缓存机制
const stockCache = {
    data: {},
    timestamp: {},
    
    get(symbol) {
        const now = Date.now();
        const cached = this.data[symbol];
        const cachedTime = this.timestamp[symbol];
        
        // 缓存5分钟
        if (cached && cachedTime && (now - cachedTime) < 5 * 60 * 1000) {
            console.log(`使用缓存数据: ${symbol}`);
            return cached;
        }
        return null;
    },
    
    set(symbol, data) {
        this.data[symbol] = data;
        this.timestamp[symbol] = Date.now();
    }
};

// 带缓存的股票数据获取
async function getStockDataWithCache(symbol) {
    // 先查缓存
    const cached = stockCache.get(symbol);
    if (cached) return cached;
    
    // 获取新数据
    const data = await fetchStockFullData(symbol);
    if (data) {
        stockCache.set(symbol, data);
    }
    return data;
}

// 自动刷新（每5分钟）
function startAutoRefresh(callback) {
    // 立即执行一次
    refreshAllStocks(callback);
    
    // 每5分钟刷新
    const interval = setInterval(() => {
        refreshAllStocks(callback);
    }, 5 * 60 * 1000);
    
    return interval;
}

// 刷新所有股票
async function refreshAllStocks(callback) {
    const symbols = Object.keys(stockSymbols).slice(0, 8); // 取前8只
    
    console.log('=== 开始刷新股票数据 ===');
    const startTime = Date.now();
    
    const results = {};
    for (const symbol of symbols) {
        // 先清缓存强制刷新
        delete stockCache.data[symbol];
        delete stockCache.timestamp[symbol];
        
        const data = await getStockDataWithCache(symbol);
        if (data) {
            results[symbol] = data;
        }
    }
    
    const duration = Date.now() - startTime;
    console.log(`=== 股票数据刷新完成，耗时 ${duration}ms ===`);
    console.log('结果:', results);
    
    if (callback) {
        callback(results);
    }
    
    return results;
}

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        fetchStockPrice,
        fetchStockHistory,
        fetchCompanyInfo,
        fetchMultipleStocks,
        fetchStockFullData,
        getStockDataWithCache,
        refreshAllStocks,
        startAutoRefresh,
        stockSymbols,
        ALPHA_VANTAGE_CONFIG
    };
}
