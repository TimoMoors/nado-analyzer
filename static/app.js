/**
 * Nado Trading Setup Analyzer - Frontend Application
 * 
 * A real-time dashboard for analyzing trading setups on Nado perpetual markets.
 */

// ==================== State Management ====================
const state = {
    markets: [],
    setups: [],
    summary: null,
    lastUpdate: null,
    selectedDirection: 'any',
    searchQuery: '',
    sortColumn: 'overall_score',
    sortDirection: 'desc',
    isLoading: true
};

// ==================== API Functions ====================
const API = {
    baseUrl: '',
    
    async fetchSummary() {
        const response = await fetch(`${this.baseUrl}/api/summary`);
        if (!response.ok) throw new Error('Failed to fetch summary');
        return response.json();
    },
    
    async fetchMarkets() {
        const response = await fetch(`${this.baseUrl}/api/markets`);
        if (!response.ok) throw new Error('Failed to fetch markets');
        return response.json();
    },
    
    async fetchSetups(direction = 'any', limit = 5) {
        const response = await fetch(`${this.baseUrl}/api/best-setups?direction=${direction}&limit=${limit}`);
        if (!response.ok) throw new Error('Failed to fetch setups');
        return response.json();
    },
    
    async fetchSetupDetail(symbol) {
        const response = await fetch(`${this.baseUrl}/api/setups/${symbol}`);
        if (!response.ok) throw new Error('Failed to fetch setup detail');
        return response.json();
    },
    
    async refreshData() {
        const response = await fetch(`${this.baseUrl}/api/refresh`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to refresh data');
        return response.json();
    },
    
    async checkHealth() {
        const response = await fetch(`${this.baseUrl}/api/health`);
        if (!response.ok) throw new Error('API unavailable');
        return response.json();
    },
    
    async fetchDatabaseStats() {
        const response = await fetch(`${this.baseUrl}/api/database/stats`);
        if (!response.ok) throw new Error('Failed to fetch database stats');
        return response.json();
    },
    
    async triggerDataCollection() {
        const response = await fetch(`${this.baseUrl}/api/database/collect`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to trigger data collection');
        return response.json();
    },
    
    async fetchMultiTimeframeSignals() {
        const response = await fetch(`${this.baseUrl}/api/signals`);
        if (!response.ok) throw new Error('Failed to fetch multi-timeframe signals');
        return response.json();
    },
    
    async fetchSignalDetail(symbol) {
        const response = await fetch(`${this.baseUrl}/api/signals/${symbol}`);
        if (!response.ok) throw new Error('Failed to fetch signal detail');
        return response.json();
    }
};

// ==================== Utility Functions ====================
const Utils = {
    formatNumber(num, decimals = 2) {
        if (num === null || num === undefined || isNaN(num) || num === 0) return 'tbd';
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }).format(num);
    },
    
    formatPrice(price) {
        if (price === null || price === undefined || isNaN(price) || price === 0) return 'tbd';
        if (price >= 1000) return this.formatNumber(price, 2);
        if (price >= 1) return this.formatNumber(price, 4);
        return this.formatNumber(price, 6);
    },
    
    formatVolume(volume) {
        if (volume === null || volume === undefined || isNaN(volume) || volume === 0) return 'tbd';
        if (volume >= 1e9) return `$${(volume / 1e9).toFixed(2)}B`;
        if (volume >= 1e6) return `$${(volume / 1e6).toFixed(2)}M`;
        if (volume >= 1e3) return `$${(volume / 1e3).toFixed(2)}K`;
        return `$${volume.toFixed(2)}`;
    },
    
    formatPercent(percent, showSign = true) {
        if (percent === null || percent === undefined || isNaN(percent)) return 'tbd';
        const sign = showSign && percent > 0 ? '+' : '';
        return `${sign}${percent.toFixed(2)}%`;
    },
    
    formatFunding(rate) {
        if (rate === null || rate === undefined || isNaN(rate)) return 'tbd';
        return `${(rate * 100).toFixed(4)}%`;
    },
    
    formatTime(timestamp) {
        if (!timestamp) return '--';
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
    },
    
    getSignalClass(signal) {
        return signal ? signal.toLowerCase().replace(' ', '_') : 'neutral';
    },
    
    getQualityClass(quality) {
        return quality ? quality.toLowerCase() : 'average';
    },
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};

// ==================== UI Components ====================
const UI = {
    // Summary Cards
    updateSummary(summary) {
        if (!summary) return;
        
        document.getElementById('total-markets').textContent = summary.total_markets || '--';
        document.getElementById('total-volume').textContent = Utils.formatVolume(summary.total_volume_24h);
        
        const bestSetup = summary.best_setups?.[0];
        if (bestSetup) {
            document.getElementById('best-score').textContent = bestSetup.overall_score?.toFixed(1) || '--';
        }
        
        const strongSignals = summary.best_setups?.filter(s => 
            s.signal === 'strong_buy' || s.signal === 'strong_sell'
        ).length || 0;
        document.getElementById('strong-signals').textContent = strongSignals;
    },
    
    // Best Setups Grid
    renderSetupCard(setup) {
        const circumference = 2 * Math.PI * 30;
        const scoreOffset = circumference - (setup.overall_score / 100) * circumference;
        const signalClass = Utils.getSignalClass(setup.signal);
        
        return `
            <div class="setup-card signal-${signalClass}" data-symbol="${setup.symbol}" onclick="App.showDetail('${setup.symbol}')">
                <div class="setup-card-header">
                    <span class="setup-symbol">${setup.symbol}</span>
                    <span class="setup-badge ${signalClass}">${setup.signal?.replace('_', ' ') || 'neutral'}</span>
                </div>
                
                <div class="setup-score">
                    <div class="score-circle">
                        <svg viewBox="0 0 72 72">
                            <circle class="score-circle-bg" cx="36" cy="36" r="30"/>
                            <circle class="score-circle-progress" cx="36" cy="36" r="30"
                                stroke-dasharray="${circumference}"
                                stroke-dashoffset="${scoreOffset}"/>
                        </svg>
                        <span class="score-value">${setup.overall_score?.toFixed(0) || '--'}</span>
                    </div>
                    <div class="score-details">
                        <div class="score-detail">
                            <span class="score-detail-label">Risk</span>
                            <span class="score-detail-value">${setup.risk_level || '--'}</span>
                        </div>
                        <div class="score-detail">
                            <span class="score-detail-label">Leverage</span>
                            <span class="score-detail-value">${setup.suggested_leverage || '--'}x</span>
                        </div>
                        <div class="score-detail">
                            <span class="score-detail-label">Funding</span>
                            <span class="score-detail-value">${Utils.formatFunding(setup.funding_rate)}</span>
                        </div>
                    </div>
                </div>
                
                <div class="setup-price">
                    <div>
                        <span class="price-label">Entry</span>
                        <span class="price-value">${Utils.formatPrice(setup.suggested_entry)}</span>
                    </div>
                    <div>
                        <span class="price-label">Target</span>
                        <span class="price-value positive">${Utils.formatPrice(setup.suggested_take_profit)}</span>
                    </div>
                    <div>
                        <span class="price-label">Stop</span>
                        <span class="price-value negative">${Utils.formatPrice(setup.suggested_stop_loss)}</span>
                    </div>
                </div>
                
                ${setup.bullish_factors?.length || setup.bearish_factors?.length || setup.warnings?.length ? `
                <div class="setup-factors">
                    ${setup.bullish_factors?.slice(0, 2).map(f => `
                        <div class="factor-item bullish">
                            <svg class="factor-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            <span>${f}</span>
                        </div>
                    `).join('') || ''}
                    ${setup.bearish_factors?.slice(0, 2).map(f => `
                        <div class="factor-item bearish">
                            <svg class="factor-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            <span>${f}</span>
                        </div>
                    `).join('') || ''}
                    ${setup.warnings?.slice(0, 1).map(w => `
                        <div class="factor-item warning">
                            <span>${w}</span>
                        </div>
                    `).join('') || ''}
                </div>
                ` : `
                <div class="setup-factors">
                    <div class="factor-item neutral">
                        <span>No clear setup - waiting for confluence</span>
                    </div>
                </div>
                `}
            </div>
        `;
    },
    
    updateSetupsGrid(setups) {
        const container = document.getElementById('best-setups-grid');
        if (!container) return;
        
        if (!setups || setups.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); padding: 20px;">No setups available</p>';
            return;
        }
        
        container.innerHTML = setups.map(s => this.renderSetupCard(s)).join('');
    },
    
    // Markets Table
    renderMarketRow(market) {
        const changeClass = market.price_change_24h >= 0 ? 'positive' : 'negative';
        const fundingClass = market.funding_rate >= 0 ? 'positive' : 'negative';
        const signalClass = Utils.getSignalClass(market.signal);
        const qualityClass = Utils.getQualityClass(market.quality);
        const baseAsset = market.symbol?.replace('USDT0', '').replace('USDT', '') || '??';
        
        return `
            <tr data-symbol="${market.symbol}">
                <td>
                    <div class="market-symbol">
                        <div class="market-symbol-icon">${baseAsset.slice(0, 3)}</div>
                        <span class="market-symbol-text">${market.symbol}</span>
                    </div>
                </td>
                <td class="market-price">${Utils.formatPrice(market.last_price)}</td>
                <td class="market-change ${changeClass}">${Utils.formatPercent(market.price_change_24h)}</td>
                <td class="market-volume">${Utils.formatVolume(market.volume_24h)}</td>
                <td class="market-funding ${fundingClass}">${Utils.formatFunding(market.funding_rate)}</td>
                <td>
                    <div class="market-score">
                        <span>${market.overall_score?.toFixed(0) || '--'}</span>
                        <div class="score-bar">
                            <div class="score-bar-fill ${qualityClass}" style="width: ${market.overall_score || 0}%"></div>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="market-signal ${signalClass}">${market.signal?.replace('_', ' ') || 'neutral'}</span>
                </td>
                <td>
                    <button class="btn-view" onclick="App.showDetail('${market.symbol}')">View</button>
                </td>
            </tr>
        `;
    },
    
    updateMarketsTable(markets) {
        const tbody = document.getElementById('markets-table-body');
        if (!tbody) return;
        
        // Filter by search
        let filtered = markets;
        if (state.searchQuery) {
            const query = state.searchQuery.toLowerCase();
            filtered = markets.filter(m => 
                m.symbol?.toLowerCase().includes(query) ||
                m.base_asset?.toLowerCase().includes(query)
            );
        }
        
        // Sort
        filtered.sort((a, b) => {
            let aVal = a[state.sortColumn];
            let bVal = b[state.sortColumn];
            
            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }
            
            if (state.sortDirection === 'asc') {
                return aVal > bVal ? 1 : -1;
            } else {
                return aVal < bVal ? 1 : -1;
            }
        });
        
        tbody.innerHTML = filtered.map(m => this.renderMarketRow(m)).join('');
    },
    
    // Detail Modal
    showModal(html) {
        const modal = document.getElementById('detail-modal');
        const body = document.getElementById('modal-body');
        if (!modal || !body) return;
        
        body.innerHTML = html;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    },
    
    hideModal() {
        const modal = document.getElementById('detail-modal');
        if (!modal) return;
        
        modal.classList.remove('active');
        document.body.style.overflow = '';
    },
    
    renderDetailModal(setup) {
        const signalClass = Utils.getSignalClass(setup.signal);
        const baseAsset = setup.symbol?.replace('USDT0', '').replace('USDT', '') || '??';
        
        return `
            <div class="detail-header">
                <div class="detail-symbol">
                    <div class="detail-symbol-icon">${baseAsset.slice(0, 3)}</div>
                    <span class="detail-symbol-name">${setup.symbol}</span>
                </div>
                <span class="detail-signal setup-badge ${signalClass}">${setup.signal?.replace('_', ' ') || 'neutral'}</span>
            </div>
            
            <div class="detail-grid">
                <div class="detail-section">
                    <h3 class="detail-section-title">Market Data</h3>
                    <div class="detail-row">
                        <span class="detail-label">Last Price</span>
                        <span class="detail-value">${Utils.formatPrice(setup.market_data?.last_price)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Mark Price</span>
                        <span class="detail-value">${Utils.formatPrice(setup.market_data?.mark_price)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Index Price</span>
                        <span class="detail-value">${Utils.formatPrice(setup.market_data?.index_price)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">24h Change</span>
                        <span class="detail-value ${setup.market_data?.price_change_percent_24h >= 0 ? 'positive' : 'negative'}" style="color: ${setup.market_data?.price_change_percent_24h >= 0 ? 'var(--accent-success)' : 'var(--accent-danger)'}">
                            ${Utils.formatPercent(setup.market_data?.price_change_percent_24h)}
                        </span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">24h Volume</span>
                        <span class="detail-value">${Utils.formatVolume(setup.market_data?.volume_24h)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Spread</span>
                        <span class="detail-value">${Utils.formatPercent(setup.market_data?.spread_percent, false)}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h3 class="detail-section-title">Scores</h3>
                    <div class="detail-row">
                        <span class="detail-label">Overall Score</span>
                        <span class="detail-value" style="color: var(--accent-primary); font-weight: 700;">${setup.overall_score?.toFixed(1)}/100</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Trend Score</span>
                        <span class="detail-value">${setup.trend_score?.toFixed(1)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Momentum Score</span>
                        <span class="detail-value">${setup.momentum_score?.toFixed(1)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Funding Score</span>
                        <span class="detail-value">${setup.funding_score?.toFixed(1)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Liquidity Score</span>
                        <span class="detail-value">${setup.liquidity_score?.toFixed(1)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Volatility Score</span>
                        <span class="detail-value">${setup.volatility_score?.toFixed(1)}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h3 class="detail-section-title">Technical Indicators</h3>
                    <div class="detail-row">
                        <span class="detail-label">RSI (14)</span>
                        <span class="detail-value">${setup.indicators?.rsi_14 != null ? setup.indicators.rsi_14.toFixed(2) : 'tbd'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">MACD</span>
                        <span class="detail-value">${setup.indicators?.macd != null ? setup.indicators.macd.toFixed(4) : 'tbd'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">SMA 20</span>
                        <span class="detail-value">${setup.indicators?.sma_20 != null ? Utils.formatPrice(setup.indicators.sma_20) : 'tbd'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">SMA 50</span>
                        <span class="detail-value">${setup.indicators?.sma_50 != null ? Utils.formatPrice(setup.indicators.sma_50) : 'tbd'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">BB Upper</span>
                        <span class="detail-value">${setup.indicators?.bollinger_upper != null ? Utils.formatPrice(setup.indicators.bollinger_upper) : 'tbd'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">BB Lower</span>
                        <span class="detail-value">${setup.indicators?.bollinger_lower != null ? Utils.formatPrice(setup.indicators.bollinger_lower) : 'tbd'}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h3 class="detail-section-title">Risk Management</h3>
                    <div class="detail-row">
                        <span class="detail-label">Risk Level</span>
                        <span class="detail-value">${setup.risk_level || '--'}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Suggested Leverage</span>
                        <span class="detail-value">${setup.suggested_leverage || '--'}x</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Entry Price</span>
                        <span class="detail-value">${Utils.formatPrice(setup.recommended_entry)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Stop Loss</span>
                        <span class="detail-value" style="color: var(--accent-danger);">${Utils.formatPrice(setup.recommended_stop_loss)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Take Profit</span>
                        <span class="detail-value" style="color: var(--accent-success);">${Utils.formatPrice(setup.recommended_take_profit)}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Funding Rate</span>
                        <span class="detail-value">${Utils.formatFunding(setup.funding_analysis?.current_rate)}</span>
                    </div>
                </div>
            </div>
            
            <div class="detail-factors">
                <div class="factors-list bullish">
                    <h4 class="factors-title">✓ Bullish Factors</h4>
                    ${setup.bullish_factors?.map(f => `<div class="factor-list-item">${f}</div>`).join('') || '<div class="factor-list-item">None</div>'}
                </div>
                <div class="factors-list bearish">
                    <h4 class="factors-title">✗ Bearish Factors</h4>
                    ${setup.bearish_factors?.map(f => `<div class="factor-list-item">${f}</div>`).join('') || '<div class="factor-list-item">None</div>'}
                </div>
            </div>
            
            ${setup.warnings?.length ? `
            <div class="detail-warnings">
                <h4 class="warnings-title">⚠️ Warnings</h4>
                ${setup.warnings.map(w => `<div class="warning-item">${w}</div>`).join('')}
            </div>
            ` : ''}
        `;
    },
    
    // Toast Notifications
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        
        const iconMap = {
            success: '<polyline points="20 6 9 17 4 12"/>',
            error: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
            info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'
        };
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${iconMap[type] || iconMap.info}
            </svg>
            <span class="toast-message">${message}</span>
        `;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },
    
    // Connection Status
    updateConnectionStatus(connected) {
        const badge = document.getElementById('connection-status');
        const text = badge?.querySelector('.status-text');
        
        if (badge && text) {
            if (connected) {
                badge.classList.add('connected');
                text.textContent = 'Connected';
            } else {
                badge.classList.remove('connected');
                text.textContent = 'Disconnected';
            }
        }
    },
    
    // Last Update Time
    updateLastUpdate(timestamp) {
        const el = document.getElementById('last-update');
        if (el) {
            el.textContent = `Updated: ${Utils.formatTime(timestamp)}`;
        }
    },
    
    // Multi-Timeframe Signals Grid
    renderTimeframeCard(market) {
        const baseAsset = market.ticker_id?.replace('-PERP_USDT0', '').replace('USDT0', '') || '??';
        const overallClass = this.getOverallSignalClass(market.overall_signal);
        
        return `
            <div class="tf-card ${overallClass}" data-symbol="${market.ticker_id}" onclick="App.showSignalDetail('${market.ticker_id}')">
                <div class="tf-card-header">
                    <div class="tf-symbol">
                        <div class="tf-symbol-icon">${baseAsset.slice(0, 3)}</div>
                        <span class="tf-symbol-text">${market.ticker_id}</span>
                    </div>
                    <div class="tf-price">
                        <span class="tf-price-value">${Utils.formatPrice(market.current_price)}</span>
                        <span class="tf-price-change ${market.price_change_24h >= 0 ? 'positive' : 'negative'}">${Utils.formatPercent(market.price_change_24h)}</span>
                    </div>
                </div>
                
                <div class="tf-signals-row">
                    ${this.renderTimeframeSignal('1H', market.timeframes?.['1h'])}
                    ${this.renderTimeframeSignal('4H', market.timeframes?.['4h'])}
                    ${this.renderTimeframeSignal('12H', market.timeframes?.['12h'])}
                    ${this.renderTimeframeSignal('1D', market.timeframes?.['1d'])}
                </div>
                
                <div class="tf-confluence">
                    <span class="tf-confluence-label">Confluence:</span>
                    <span class="tf-confluence-value ${overallClass}">${market.overall_signal?.replace('_', ' ') || 'neutral'}</span>
                    <span class="tf-confluence-count">(${market.bullish_count || 0}↑ ${market.bearish_count || 0}↓)</span>
                </div>
            </div>
        `;
    },
    
    renderTimeframeSignal(label, data) {
        if (!data || data.signal === 'tbd') {
            return `
                <div class="tf-signal tbd">
                    <span class="tf-signal-label">${label}</span>
                    <span class="tf-signal-indicator">
                        <span class="tf-signal-dot tbd"></span>
                        <span class="tf-signal-text">tbd</span>
                    </span>
                    <span class="tf-signal-st">ST: tbd</span>
                </div>
            `;
        }
        
        const signalClass = data.signal || 'neutral';
        const stClass = data.supertrend || 'tbd';
        const rsiValue = data.rsi != null ? data.rsi.toFixed(0) : 'tbd';
        
        return `
            <div class="tf-signal ${signalClass}">
                <span class="tf-signal-label">${label}</span>
                <span class="tf-signal-indicator">
                    <span class="tf-signal-dot ${signalClass}"></span>
                    <span class="tf-signal-text">${signalClass}</span>
                </span>
                <span class="tf-signal-st ${stClass}">ST: ${stClass}</span>
                <span class="tf-signal-rsi">RSI: ${rsiValue}</span>
            </div>
        `;
    },
    
    getOverallSignalClass(signal) {
        if (!signal) return 'neutral';
        if (signal.includes('bullish')) return 'bullish';
        if (signal.includes('bearish')) return 'bearish';
        return 'neutral';
    },
    
    updateTimeframeGrid(signals) {
        const container = document.getElementById('timeframe-grid');
        if (!container) return;
        
        if (!signals || signals.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted); padding: 20px;">Loading multi-timeframe signals...</p>';
            return;
        }
        
        // Sort by confluence strength
        const sorted = signals.sort((a, b) => {
            const aStrength = Math.abs((a.bullish_count || 0) - (a.bearish_count || 0));
            const bStrength = Math.abs((b.bullish_count || 0) - (b.bearish_count || 0));
            return bStrength - aStrength;
        });
        
        container.innerHTML = sorted.map(s => this.renderTimeframeCard(s)).join('');
    },
    
    // Render detail modal with timeframe signals
    renderSignalDetailModal(signalData) {
        const baseAsset = signalData.ticker_id?.replace('-PERP_USDT0', '').replace('USDT0', '') || '??';
        const overallClass = this.getOverallSignalClass(signalData.confluence?.overall_signal);
        
        return `
            <div class="detail-header">
                <div class="detail-symbol">
                    <div class="detail-symbol-icon">${baseAsset.slice(0, 3)}</div>
                    <span class="detail-symbol-name">${signalData.ticker_id}</span>
                </div>
                <span class="detail-signal setup-badge ${overallClass}">${signalData.confluence?.overall_signal?.replace('_', ' ') || 'neutral'}</span>
            </div>
            
            <div class="detail-price-row">
                <span class="detail-price-value">${Utils.formatPrice(signalData.current_price)}</span>
            </div>
            
            <div class="detail-confluence-summary">
                <h3>Confluence Analysis</h3>
                <div class="confluence-stats">
                    <div class="confluence-stat bullish">
                        <span class="confluence-stat-value">${signalData.confluence?.bullish_count || 0}</span>
                        <span class="confluence-stat-label">Bullish</span>
                    </div>
                    <div class="confluence-stat bearish">
                        <span class="confluence-stat-value">${signalData.confluence?.bearish_count || 0}</span>
                        <span class="confluence-stat-label">Bearish</span>
                    </div>
                    <div class="confluence-stat neutral">
                        <span class="confluence-stat-value">${signalData.confluence?.neutral_count || 0}</span>
                        <span class="confluence-stat-label">Neutral</span>
                    </div>
                </div>
            </div>
            
            <div class="detail-timeframes">
                ${this.renderTimeframeDetail('1 Hour', signalData.timeframes?.['1h'])}
                ${this.renderTimeframeDetail('4 Hours', signalData.timeframes?.['4h'])}
                ${this.renderTimeframeDetail('12 Hours', signalData.timeframes?.['12h'])}
                ${this.renderTimeframeDetail('Daily', signalData.timeframes?.['1d'])}
            </div>
        `;
    },
    
    renderTimeframeDetail(label, data) {
        if (!data || data.signal === 'tbd') {
            return `
                <div class="tf-detail-section tbd">
                    <h4 class="tf-detail-title">${label}</h4>
                    <div class="tf-detail-signal">
                        <span class="tf-detail-badge tbd">tbd</span>
                        <span class="tf-detail-reason">Insufficient data for analysis</span>
                    </div>
                </div>
            `;
        }
        
        const signalClass = data.signal || 'neutral';
        const indicators = data.indicators || {};
        
        return `
            <div class="tf-detail-section ${signalClass}">
                <div class="tf-detail-header">
                    <h4 class="tf-detail-title">${label}</h4>
                    <span class="tf-detail-badge ${signalClass}">${data.signal}</span>
                </div>
                
                <div class="tf-detail-indicators">
                    <div class="tf-indicator">
                        <span class="tf-indicator-label">Supertrend</span>
                        <span class="tf-indicator-value ${indicators.supertrend_trend || 'tbd'}">${indicators.supertrend_trend || 'tbd'}</span>
                    </div>
                    <div class="tf-indicator">
                        <span class="tf-indicator-label">RSI (14)</span>
                        <span class="tf-indicator-value">${indicators.rsi_14 != null ? indicators.rsi_14.toFixed(1) : 'tbd'}</span>
                    </div>
                    <div class="tf-indicator">
                        <span class="tf-indicator-label">MACD</span>
                        <span class="tf-indicator-value ${indicators.macd > (indicators.macd_signal || 0) ? 'bullish' : 'bearish'}">${indicators.macd != null ? indicators.macd.toFixed(4) : 'tbd'}</span>
                    </div>
                    <div class="tf-indicator">
                        <span class="tf-indicator-label">EMA 9/21</span>
                        <span class="tf-indicator-value ${indicators.ema_9 > (indicators.ema_21 || 0) ? 'bullish' : 'bearish'}">
                            ${indicators.ema_9 != null && indicators.ema_21 != null ? (indicators.ema_9 > indicators.ema_21 ? '↑ Bullish' : '↓ Bearish') : 'tbd'}
                        </span>
                    </div>
                </div>
                
                ${data.reasons?.length ? `
                <div class="tf-detail-reasons">
                    ${data.reasons.map(r => `<span class="tf-reason">${r}</span>`).join('')}
                </div>
                ` : ''}
                
                <div class="tf-detail-meta">
                    <span class="tf-meta-item">Candles: ${indicators.candle_count || 0}</span>
                    <span class="tf-meta-item">Score: ${data.score || 0}</span>
                </div>
            </div>
        `;
    }
};

// ==================== Main Application ====================
const App = {
    async init() {
        console.log('Initializing Nado Trading Setup Analyzer...');
        
        this.setupEventListeners();
        await this.loadData();
        await this.loadDatabaseStats();
        await this.loadMultiTimeframeSignals();
        
        // Refresh data every 60 seconds
        setInterval(() => this.loadData(), 60000);
        // Refresh database stats every 30 seconds
        setInterval(() => this.loadDatabaseStats(), 30000);
        // Refresh multi-timeframe signals every 60 seconds
        setInterval(() => this.loadMultiTimeframeSignals(), 60000);
    },
    
    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.handleRefresh());
        }
        
        // Collect data button
        const collectBtn = document.getElementById('collect-btn');
        if (collectBtn) {
            collectBtn.addEventListener('click', () => this.handleCollectData());
        }
        
        // Direction toggle
        document.querySelectorAll('.toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                state.selectedDirection = e.target.dataset.direction;
                this.loadSetups();
            });
        });
        
        // Search input
        const searchInput = document.getElementById('market-search');
        if (searchInput) {
            searchInput.addEventListener('input', Utils.debounce((e) => {
                state.searchQuery = e.target.value;
                UI.updateMarketsTable(state.markets);
            }, 300));
        }
        
        // Table sorting
        document.querySelectorAll('.markets-table th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const column = th.dataset.sort;
                if (state.sortColumn === column) {
                    state.sortDirection = state.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    state.sortColumn = column;
                    state.sortDirection = 'desc';
                }
                
                // Update sort indicators
                document.querySelectorAll('.markets-table th.sortable').forEach(t => t.classList.remove('sorted'));
                th.classList.add('sorted');
                
                UI.updateMarketsTable(state.markets);
            });
        });
        
        // Modal close
        const modalClose = document.getElementById('modal-close');
        const modalBackdrop = document.querySelector('.modal-backdrop');
        
        if (modalClose) {
            modalClose.addEventListener('click', () => UI.hideModal());
        }
        if (modalBackdrop) {
            modalBackdrop.addEventListener('click', () => UI.hideModal());
        }
        
        // ESC key to close modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                UI.hideModal();
            }
        });
    },
    
    async loadData() {
        try {
            state.isLoading = true;
            
            // Check health first
            const health = await API.checkHealth();
            UI.updateConnectionStatus(true);
            
            // Load all data in parallel
            const [summary, markets, setups] = await Promise.all([
                API.fetchSummary(),
                API.fetchMarkets(),
                API.fetchSetups(state.selectedDirection)
            ]);
            
            state.summary = summary;
            state.markets = markets;
            state.setups = setups;
            state.lastUpdate = new Date();
            
            // Update UI
            UI.updateSummary(summary);
            UI.updateMarketsTable(markets);
            UI.updateSetupsGrid(setups);
            UI.updateLastUpdate(state.lastUpdate);
            
            state.isLoading = false;
            
        } catch (error) {
            console.error('Failed to load data:', error);
            UI.updateConnectionStatus(false);
            UI.showToast('Failed to load data. Retrying...', 'error');
            state.isLoading = false;
        }
    },
    
    async loadSetups() {
        try {
            const setups = await API.fetchSetups(state.selectedDirection);
            state.setups = setups;
            UI.updateSetupsGrid(setups);
        } catch (error) {
            console.error('Failed to load setups:', error);
            UI.showToast('Failed to load setups', 'error');
        }
    },
    
    async handleRefresh() {
        const btn = document.getElementById('refresh-btn');
        if (btn) btn.classList.add('loading');
        
        try {
            await API.refreshData();
            await this.loadData();
            UI.showToast('Data refreshed successfully', 'success');
        } catch (error) {
            console.error('Failed to refresh:', error);
            UI.showToast('Failed to refresh data', 'error');
        } finally {
            if (btn) btn.classList.remove('loading');
        }
    },
    
    async showDetail(symbol) {
        try {
            const setup = await API.fetchSetupDetail(symbol);
            const html = UI.renderDetailModal(setup);
            UI.showModal(html);
        } catch (error) {
            console.error('Failed to load detail:', error);
            UI.showToast('Failed to load market details', 'error');
        }
    },
    
    async loadDatabaseStats() {
        try {
            const stats = await API.fetchDatabaseStats();
            
            document.getElementById('db-trades').textContent = stats.total_trades?.toLocaleString() || '0';
            document.getElementById('db-candles-1h').textContent = stats.candles_by_timeframe?.['1h'] || '0';
            document.getElementById('db-candles-4h').textContent = stats.candles_by_timeframe?.['4h'] || '0';
            document.getElementById('db-candles-12h').textContent = stats.candles_by_timeframe?.['12h'] || '0';
            document.getElementById('db-candles-1d').textContent = stats.candles_by_timeframe?.['1d'] || '0';
            
        } catch (error) {
            console.error('Failed to load database stats:', error);
        }
    },
    
    async handleCollectData() {
        const btn = document.getElementById('collect-btn');
        if (btn) {
            btn.classList.add('loading');
            btn.disabled = true;
        }
        
        UI.showToast('Collecting data... This may take a minute.', 'info');
        
        try {
            await API.triggerDataCollection();
            await this.loadDatabaseStats();
            await this.loadData();
            await this.loadMultiTimeframeSignals();
            UI.showToast('Data collection complete!', 'success');
        } catch (error) {
            console.error('Failed to collect data:', error);
            UI.showToast('Failed to collect data', 'error');
        } finally {
            if (btn) {
                btn.classList.remove('loading');
                btn.disabled = false;
            }
        }
    },
    
    async loadMultiTimeframeSignals() {
        try {
            const signals = await API.fetchMultiTimeframeSignals();
            UI.updateTimeframeGrid(signals);
        } catch (error) {
            console.error('Failed to load multi-timeframe signals:', error);
            // Don't show toast for this - it's a background refresh
        }
    },
    
    async showSignalDetail(symbol) {
        try {
            const signalData = await API.fetchSignalDetail(symbol);
            const html = UI.renderSignalDetailModal(signalData);
            UI.showModal(html);
        } catch (error) {
            console.error('Failed to load signal detail:', error);
            UI.showToast('Failed to load signal details', 'error');
        }
    }
};

// ==================== Initialize App ====================
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

