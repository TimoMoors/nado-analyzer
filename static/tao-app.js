/**
 * TAO Subnet Analyzer - Frontend JavaScript
 * 
 * Handles data fetching, rendering, and user interactions for TAO ecosystem analysis.
 */

// ==================== Configuration ====================

const API_BASE = '/api/tao';
const REFRESH_INTERVAL = 120000; // 2 minutes

// ==================== State ====================

let subnetsData = [];
let summaryData = null;
let signalHistory = [];
let performanceStats = null;
let lastUpdate = null;

// ==================== Utility Functions ====================

function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined) return '--';
    if (num >= 1e9) return (num / 1e9).toFixed(decimals) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(decimals) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(decimals) + 'K';
    return num.toFixed(decimals);
}

function formatPercent(num) {
    if (num === null || num === undefined) return '--';
    const value = num < 1 ? num * 100 : num; // Handle both decimal and percentage formats
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(2) + '%';
}

function formatPrice(price) {
    if (price === null || price === undefined) return '--';
    if (price < 0.0001) return price.toExponential(2);
    if (price < 1) return price.toFixed(6);
    return price.toFixed(4);
}

function getSignalClass(signal) {
    return signal.toLowerCase().replace(/_/g, '-');
}

function getSignalEmoji(signal) {
    const emojis = {
        'strong_stake': '🟢',
        'stake': '🟢',
        'hold': '⚪',
        'reduce': '🟡',
        'avoid': '🔴',
        'strong_buy': '🟢',
        'buy': '🟢',
        'neutral': '⚪',
        'sell': '🟡',
        'strong_sell': '🔴'
    };
    return emojis[signal] || '⚪';
}

function getScoreClass(score) {
    if (score >= 75) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'average';
    return 'poor';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==================== API Functions ====================

async function fetchData(endpoint) {
    try {
        const response = await fetch(API_BASE + endpoint);
        if (!response.ok) {
            if (response.status === 503) {
                throw new Error('TAO data not yet loaded');
            }
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error fetching ${endpoint}:`, error);
        throw error;
    }
}

async function loadSummary() {
    try {
        summaryData = await fetchData('/summary');
        renderSummary();
    } catch (error) {
        console.error('Error loading summary:', error);
    }
}

async function loadSubnets() {
    try {
        subnetsData = await fetchData('/subnets');
        renderSubnetsTable();
    } catch (error) {
        console.error('Error loading subnets:', error);
    }
}

async function loadBestInvestments() {
    try {
        const investments = await fetchData('/best-investments?limit=10');
        renderInvestmentCards(investments);
    } catch (error) {
        console.error('Error loading investments:', error);
    }
}

async function loadSignalHistory() {
    try {
        signalHistory = await fetchData('/signal-history?limit=50');
        renderSignalHistory();
    } catch (error) {
        console.error('Error loading signal history:', error);
        signalHistory = [];
        renderSignalHistory();
    }
}

async function loadPerformanceStats() {
    try {
        performanceStats = await fetchData('/signal-performance?days=30');
        renderPerformanceStats();
    } catch (error) {
        console.error('Error loading performance stats:', error);
        performanceStats = null;
        renderPerformanceStats();
    }
}

async function checkHealth() {
    try {
        const health = await fetchData('/health');
        updateConnectionStatus(health.status === 'healthy', health.last_update);
        return health.status === 'healthy';
    } catch (error) {
        updateConnectionStatus(false);
        return false;
    }
}

async function refreshAll() {
    const btn = document.getElementById('refresh-btn');
    btn.disabled = true;
    btn.classList.add('loading');
    
    try {
        await fetch(API_BASE + '/refresh', { method: 'POST' });
        showToast('Data refreshed successfully', 'success');
        await loadAllData();
    } catch (error) {
        showToast('Error refreshing data', 'error');
    } finally {
        btn.disabled = false;
        btn.classList.remove('loading');
    }
}

async function loadAllData() {
    const isHealthy = await checkHealth();
    if (!isHealthy) {
        showToast('TAO API not available - check API key', 'warning');
        return;
    }
    
    await Promise.all([
        loadSummary(),
        loadSubnets(),
        loadBestInvestments(),
        loadSignalHistory(),
        loadPerformanceStats()
    ]);
    
    lastUpdate = new Date();
    updateLastUpdateDisplay();
}

// ==================== Render Functions ====================

function updateConnectionStatus(isConnected, lastUpdateTime) {
    const status = document.getElementById('connection-status');
    const dot = status.querySelector('.status-dot');
    const text = status.querySelector('.status-text');
    
    if (isConnected) {
        dot.style.background = '#00d4aa';
        text.textContent = 'Connected';
        status.classList.remove('disconnected');
    } else {
        dot.style.background = '#ef4444';
        text.textContent = 'Disconnected';
        status.classList.add('disconnected');
    }
}

function updateLastUpdateDisplay() {
    const el = document.getElementById('last-update');
    if (lastUpdate) {
        el.textContent = `Updated: ${lastUpdate.toLocaleTimeString()}`;
    }
}

function renderSummary() {
    if (!summaryData) return;
    
    document.getElementById('total-subnets').textContent = summaryData.total_subnets || '--';
    document.getElementById('bullish-subnets').textContent = summaryData.bullish_subnets || '0';
    document.getElementById('bearish-subnets').textContent = summaryData.bearish_subnets || '0';
    
    const avgFng = summaryData.average_fear_greed;
    if (avgFng !== null && avgFng !== undefined) {
        let sentiment = 'Neutral';
        if (avgFng >= 70) sentiment = 'Greed';
        else if (avgFng >= 55) sentiment = 'Optimistic';
        else if (avgFng <= 30) sentiment = 'Fear';
        else if (avgFng <= 45) sentiment = 'Cautious';
        document.getElementById('market-sentiment').textContent = `${avgFng.toFixed(0)} - ${sentiment}`;
    } else {
        document.getElementById('market-sentiment').textContent = '--';
    }
}

function renderInvestmentCards(investments) {
    const grid = document.getElementById('investment-grid');
    grid.innerHTML = investments.map(inv => `
        <div class="subnet-card">
            <div class="subnet-header">
                <div>
                    <div class="subnet-name">${inv.name || 'Subnet ' + inv.netuid}</div>
                    <div class="subnet-symbol">${inv.symbol || ''}</div>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span class="subnet-netuid">SN${inv.netuid}</span>
                    <span class="signal-badge ${getSignalClass(inv.signal)}">${inv.signal.replace(/_/g, ' ').toUpperCase()}</span>
                </div>
            </div>
            
            <div class="metric-row">
                <span class="metric-label">Price</span>
                <span class="metric-value">${formatPrice(inv.price)} τ</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">24h Change</span>
                <span class="metric-value ${inv.price_change_24h >= 0 ? 'positive' : 'negative'}">${formatPercent(inv.price_change_24h)}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">7d Change</span>
                <span class="metric-value ${inv.price_change_7d >= 0 ? 'positive' : 'negative'}">${formatPercent(inv.price_change_7d)}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Market Cap</span>
                <span class="metric-value">${formatNumber(inv.market_cap)} τ</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Emission</span>
                <span class="metric-value">${formatNumber(inv.emission)}</span>
            </div>
            
            <div class="score-bar-container">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <span class="metric-label">Score</span>
                    <span class="metric-value">${inv.overall_score.toFixed(1)}</span>
                </div>
                <div class="score-bar">
                    <div class="score-bar-fill ${getScoreClass(inv.overall_score)}" style="width: ${inv.overall_score}%"></div>
                </div>
            </div>
            
            <div class="component-scores">
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.momentum.toFixed(0)}</div>
                    <div class="component-score-label">Momentum</div>
                </div>
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.flow.toFixed(0)}</div>
                    <div class="component-score-label">Flow</div>
                </div>
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.emission.toFixed(0)}</div>
                    <div class="component-score-label">Emission</div>
                </div>
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.liquidity.toFixed(0)}</div>
                    <div class="component-score-label">Liquidity</div>
                </div>
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.sentiment.toFixed(0)}</div>
                    <div class="component-score-label">Sentiment</div>
                </div>
                <div class="component-score">
                    <div class="component-score-value">${inv.component_scores.network_health.toFixed(0)}</div>
                    <div class="component-score-label">Health</div>
                </div>
            </div>
            
            <div class="factors-list">
                ${inv.bullish_factors.map(f => `<div class="factor factor-bullish">✓ ${f}</div>`).join('')}
                ${inv.bearish_factors.map(f => `<div class="factor factor-bearish">✗ ${f}</div>`).join('')}
                ${inv.warnings.map(f => `<div class="factor factor-warning">${f}</div>`).join('')}
            </div>
        </div>
    `).join('');
}

function renderSubnetsTable() {
    const tbody = document.getElementById('subnets-table-body');
    tbody.innerHTML = subnetsData.map(s => `
        <tr>
            <td><span class="subnet-netuid">SN${s.netuid}</span></td>
            <td>
                <div>${s.name || 'Subnet ' + s.netuid}</div>
                <div class="subnet-symbol">${s.symbol || ''}</div>
            </td>
            <td class="font-mono">${formatPrice(s.price)}</td>
            <td class="${s.price_change_24h >= 0 ? 'positive' : 'negative'}">${formatPercent(s.price_change_24h)}</td>
            <td class="font-mono">${formatNumber(s.market_cap)}</td>
            <td class="font-mono">${formatNumber(s.emission)}</td>
            <td class="font-mono">${s.overall_score.toFixed(1)}</td>
            <td><span class="signal-badge ${getSignalClass(s.signal)}">${getSignalEmoji(s.signal)} ${s.signal.replace(/_/g, ' ')}</span></td>
        </tr>
    `).join('');
}

function renderPerformanceStats() {
    const buyAccuracy = document.getElementById('buy-accuracy-24h');
    const avgReturn = document.getElementById('avg-return-24h');
    const totalSignals = document.getElementById('total-signals');
    
    if (!performanceStats || performanceStats.total_signals === 0) {
        buyAccuracy.textContent = '--';
        avgReturn.textContent = '--';
        totalSignals.textContent = '0';
        return;
    }
    
    // Display buy accuracy
    if (performanceStats.buy_accuracy_24h !== undefined) {
        buyAccuracy.textContent = performanceStats.buy_accuracy_24h.toFixed(1) + '%';
    } else {
        buyAccuracy.textContent = '--';
    }
    
    // Display average return
    if (performanceStats.buy_avg_return_24h !== undefined) {
        const returnVal = performanceStats.buy_avg_return_24h;
        avgReturn.textContent = (returnVal >= 0 ? '+' : '') + returnVal.toFixed(2) + '%';
        avgReturn.className = 'performance-value' + (returnVal < 0 ? ' negative' : '');
    } else {
        avgReturn.textContent = '--';
    }
    
    totalSignals.textContent = performanceStats.total_signals;
}

function renderSignalHistory() {
    const tbody = document.getElementById('signal-history-body');
    
    if (!signalHistory || signalHistory.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; padding: 2rem; color: var(--text-secondary);">
                    No signal history yet. Signals will be recorded over time.
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = signalHistory.map(s => {
        const timestamp = new Date(s.timestamp);
        const timeStr = timestamp.toLocaleDateString() + ' ' + timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        
        const return24h = s.return_24h !== null 
            ? `<span class="${s.return_24h >= 0 ? 'return-positive' : 'return-negative'}">${s.return_24h >= 0 ? '+' : ''}${s.return_24h.toFixed(2)}%</span>`
            : '<span style="color: var(--text-secondary);">--</span>';
        
        const return7d = s.return_7d !== null 
            ? `<span class="${s.return_7d >= 0 ? 'return-positive' : 'return-negative'}">${s.return_7d >= 0 ? '+' : ''}${s.return_7d.toFixed(2)}%</span>`
            : '<span style="color: var(--text-secondary);">--</span>';
        
        let statusClass = 'pending';
        let statusText = 'Pending';
        if (s.outcome_status === 'complete') {
            statusClass = 'complete';
            statusText = 'Complete';
        } else if (s.outcome_status === 'partial') {
            statusClass = 'partial';
            statusText = '24h Done';
        }
        
        return `
            <tr>
                <td class="font-mono" style="font-size: 0.8rem;">${timeStr}</td>
                <td>
                    <div>${s.name || 'Subnet ' + s.netuid}</div>
                    <div class="subnet-symbol">SN${s.netuid}</div>
                </td>
                <td><span class="signal-badge ${getSignalClass(s.signal)}">${getSignalEmoji(s.signal)} ${s.signal.replace(/_/g, ' ')}</span></td>
                <td class="font-mono">${s.score.toFixed(1)}</td>
                <td class="font-mono">${formatPrice(s.price_at_signal)} τ</td>
                <td>${return24h}</td>
                <td>${return7d}</td>
                <td><span class="status-badge-small ${statusClass}">${statusText}</span></td>
            </tr>
        `;
    }).join('');
}

// ==================== Event Handlers ====================

function setupTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');
        });
    });
}

function setupSearch() {
    const subnetSearch = document.getElementById('subnet-search');
    
    if (subnetSearch) {
        subnetSearch.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('#subnets-table-body tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
}

function setupRefresh() {
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshAll);
    }
}

// ==================== Initialization ====================

async function init() {
    console.log('TAO Analyzer initializing...');
    
    setupTabs();
    setupSearch();
    setupRefresh();
    
    // Initial load
    await loadAllData();
    
    // Set up auto-refresh
    setInterval(loadAllData, REFRESH_INTERVAL);
    
    console.log('TAO Analyzer initialized');
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', init);
