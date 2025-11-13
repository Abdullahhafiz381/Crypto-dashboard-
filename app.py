import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

# ... (keep all your existing CSS and setup code) ...

class CryptoAnalyzer:
    def __init__(self, data_file="network_data.json"):
        self.data_file = data_file
        self.bitnodes_api = "https://bitnodes.io/api/v1/snapshots/latest/"
        self.load_node_data()
    
    def load_node_data(self):
        """Load only current and previous node data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.current_data = data.get('current_data')
                    self.previous_data = data.get('previous_data')
            else:
                self.current_data = None
                self.previous_data = None
        except:
            self.current_data = None
            self.previous_data = None
    
    def save_node_data(self):
        """Save current and previous node data"""
        try:
            data = {
                'current_data': self.current_data,
                'previous_data': self.previous_data,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            st.error(f"Error saving data: {e}")
    
    def fetch_node_data(self):
        """Fetch current node data from Bitnodes API"""
        try:
            response = requests.get(self.bitnodes_api, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            total_nodes = data['total_nodes']
            
            # Count active nodes (nodes that responded)
            active_nodes = 0
            tor_nodes = 0
            
            for node_address, node_info in data['nodes'].items():
                # Check if node is active (has response data)
                if node_info and isinstance(node_info, list) and len(node_info) > 0:
                    active_nodes += 1
                
                # Count Tor nodes
                if '.onion' in str(node_address) or '.onion' in str(node_info):
                    tor_nodes += 1
            
            tor_percentage = (tor_nodes / total_nodes) * 100 if total_nodes > 0 else 0
            active_ratio = active_nodes / total_nodes if total_nodes > 0 else 0
            
            return {
                'timestamp': datetime.now().isoformat(),
                'total_nodes': total_nodes,
                'active_nodes': active_nodes,
                'tor_nodes': tor_nodes,
                'tor_percentage': tor_percentage,
                'active_ratio': active_ratio
            }
        except Exception as e:
            st.error(f"Error fetching node data: {e}")
            return None
    
    def update_node_data(self):
        """Fetch new data and shift current to previous"""
        new_data = self.fetch_node_data()
        if not new_data:
            return False
        
        # Shift current to previous, set new data as current
        self.previous_data = self.current_data
        self.current_data = new_data
        
        self.save_node_data()
        return True
    
    def calculate_high_confidence_signal(self):
        """Calculate signal with confidence levels based on multiple factors"""
        if not self.current_data or not self.previous_data:
            return {
                'current_tor': self.current_data['tor_nodes'] if self.current_data else 0,
                'previous_tor': self.previous_data['tor_nodes'] if self.previous_data else 0,
                'tor_change': 0,
                'percentage_change': 0,
                'signal': "INSUFFICIENT_DATA",
                'confidence': "LOW",
                'bias': "NEED MORE DATA",
                'reasoning': "Need at least 2 data points for comparison"
            }
        
        current_tor = self.current_data['tor_nodes']
        previous_tor = self.previous_data['tor_nodes']
        current_total = self.current_data['total_nodes']
        active_ratio = self.current_data['active_ratio']
        
        # Calculate changes
        tor_change = current_tor - previous_tor
        percentage_change = (tor_change / previous_tor) * 100 if previous_tor > 0 else 0
        
        # Calculate confidence factors
        confidence_factors = []
        
        # Factor 1: Absolute Tor change magnitude
        if abs(tor_change) > 50:
            confidence_factors.append("LARGE_TOR_CHANGE")
        elif abs(tor_change) > 25:
            confidence_factors.append("MEDIUM_TOR_CHANGE")
        else:
            confidence_factors.append("SMALL_TOR_CHANGE")
        
        # Factor 2: Percentage change magnitude
        if abs(percentage_change) > 5:
            confidence_factors.append("LARGE_PERCENTAGE_CHANGE")
        elif abs(percentage_change) > 2.5:
            confidence_factors.append("MEDIUM_PERCENTAGE_CHANGE")
        else:
            confidence_factors.append("SMALL_PERCENTAGE_CHANGE")
        
        # Factor 3: Network size stability
        if current_total > 10000:
            confidence_factors.append("LARGE_NETWORK")
        elif current_total > 8000:
            confidence_factors.append("MEDIUM_NETWORK")
        else:
            confidence_factors.append("SMALL_NETWORK")
        
        # Factor 4: Active ratio health
        if 0.7 <= active_ratio <= 0.9:
            confidence_factors.append("HEALTHY_ACTIVE_RATIO")
        elif 0.6 <= active_ratio <= 0.95:
            confidence_factors.append("MODERATE_ACTIVE_RATIO")
        else:
            confidence_factors.append("POOR_ACTIVE_RATIO")
        
        # Determine overall confidence
        high_confidence_count = sum(1 for factor in confidence_factors 
                                  if factor.startswith(('LARGE', 'HEALTHY')))
        medium_confidence_count = sum(1 for factor in confidence_factors 
                                    if factor.startswith(('MEDIUM', 'MODERATE')))
        
        if high_confidence_count >= 3:
            confidence = "HIGH"
        elif (high_confidence_count + medium_confidence_count) >= 3:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        # Calculate signal with confidence
        # HIGH CONFIDENCE SIGNALS
        if tor_change > 50 and percentage_change > 5 and confidence == "HIGH":
            signal = "STRONG SELL"
            bias = "HIGHLY BEARISH"
            reasoning = f"Large Tor increase ({tor_change:+,} nodes, {percentage_change:+.1f}%) with high confidence factors"
        elif tor_change < -50 and percentage_change < -5 and confidence == "HIGH":
            signal = "STRONG BUY"
            bias = "HIGHLY BULLISH"
            reasoning = f"Large Tor decrease ({tor_change:+,} nodes, {percentage_change:+.1f}%) with high confidence factors"
        
        # MEDIUM CONFIDENCE SIGNALS
        elif tor_change > 25 and percentage_change > 2.5 and confidence in ["MEDIUM", "HIGH"]:
            signal = "SELL"
            bias = "BEARISH"
            reasoning = f"Moderate Tor increase ({tor_change:+,} nodes, {percentage_change:+.1f}%) with medium confidence"
        elif tor_change < -25 and percentage_change < -2.5 and confidence in ["MEDIUM", "HIGH"]:
            signal = "BUY"
            bias = "BULLISH"
            reasoning = f"Moderate Tor decrease ({tor_change:+,} nodes, {percentage_change:+.1f}%) with medium confidence"
        
        # LOW CONFIDENCE SIGNALS
        elif tor_change > 10:
            signal = "SLIGHT SELL"
            bias = "SLIGHTLY BEARISH"
            reasoning = f"Small Tor increase ({tor_change:+,} nodes) - low confidence signal"
        elif tor_change < -10:
            signal = "SLIGHT BUY"
            bias = "SLIGHTLY BULLISH"
            reasoning = f"Small Tor decrease ({tor_change:+,} nodes) - low confidence signal"
        
        # NO CLEAR SIGNAL
        else:
            signal = "HOLD"
            bias = "NEUTRAL"
            reasoning = f"Minimal Tor change ({tor_change:+,} nodes) - no clear signal"
        
        return {
            'current_tor': current_tor,
            'previous_tor': previous_tor,
            'tor_change': tor_change,
            'percentage_change': percentage_change,
            'signal': signal,
            'confidence': confidence,
            'bias': bias,
            'reasoning': reasoning,
            'confidence_factors': confidence_factors,
            'total_nodes': current_total,
            'active_ratio': active_ratio
        }
    
    def calculate_network_signal(self):
        """Calculate signal based on total node changes"""
        if not self.current_data or not self.previous_data:
            return {
                'current_total': self.current_data['total_nodes'] if self.current_data else 0,
                'previous_total': self.previous_data['total_nodes'] if self.previous_data else 0,
                'total_change': 0,
                'network_signal': "INSUFFICIENT_DATA"
            }
        
        current_total = self.current_data['total_nodes']
        previous_total = self.previous_data['total_nodes']
        total_change = current_total - previous_total
        
        # Network health signal
        if total_change > 100:
            network_signal = "NETWORK STRONG GROWTH"
        elif total_change > 50:
            network_signal = "NETWORK GROWING"
        elif total_change > 0:
            network_signal = "NETWORK STABLE" 
        else:
            network_signal = "NETWORK SHRINKING"
        
        return {
            'current_total': current_total,
            'previous_total': previous_total,
            'total_change': total_change,
            'network_signal': network_signal
        }

# ... (keep get_crypto_prices, get_coin_display_name, get_coin_emoji functions) ...

def main():
    # Initialize analyzer
    analyzer = CryptoAnalyzer()
    
    # Futuristic Header
    st.markdown('<h1 class="cyber-header">🚀 ABDULLAH\'S CRYPTO TRACKER</h1>', unsafe_allow_html=True)
    st.markdown('<p class="cyber-subheader">CONFIDENCE-BASED TOR SIGNALS • LIVE PRICES • SMART ANALYSIS</p>', unsafe_allow_html=True)
    
    # LIVE CRYPTO PRICES SECTION
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">💰 LIVE CRYPTO PRICES</h2>', unsafe_allow_html=True)
    
    # Get all crypto prices
    prices = get_crypto_prices()
    
    if prices:
        # Display BTC price prominently
        btc_price = prices.get('BTCUSDT')
        if btc_price:
            st.markdown('<div class="price-glow">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f'<div style="text-align: center;"><span style="font-family: Orbitron; font-size: 3rem; font-weight: 900; background: linear-gradient(90deg, #00ffff, #ff00ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${btc_price:,.2f}</span></div>', unsafe_allow_html=True)
                st.markdown('<p style="text-align: center; color: #8892b0; font-family: Rajdhani;">BITCOIN PRICE (USD)</p>', unsafe_allow_html=True)
            
            with col2:
                st.metric(
                    label="24H STATUS",
                    value="🟢 LIVE",
                    delta="ACTIVE"
                )
            
            with col3:
                st.metric(
                    label="DATA SOURCE", 
                    value="BINANCE API",
                    delta="PRIMARY"
                )
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Display all coins in a grid
        st.markdown('<h3 style="font-family: Orbitron; color: #00ffff; margin: 1rem 0;">📊 ALTCOIN MARKET</h3>', unsafe_allow_html=True)
        
        # Create columns for coin grid
        coins_to_display = {k: v for k, v in prices.items() if k != 'BTCUSDT'}
        cols = st.columns(4)
        
        for idx, (symbol, price) in enumerate(coins_to_display.items()):
            if price:
                with cols[idx % 4]:
                    emoji = get_coin_emoji(symbol)
                    name = get_coin_display_name(symbol)            
                    st.markdown(f'''
                    <div class="coin-card">
                        <div style="text-align: center;">
                            <h4 style="font-family: Orbitron; color: #00ffff; margin: 0.5rem 0; font-size: 1.1rem;">{emoji} {name}</h4>
                            <p style="font-family: Orbitron; font-size: 1.3rem; font-weight: 700; color: #ffffff; margin: 0.5rem 0;">${price:,.2f}</p>
                            <p style="color: #8892b0; font-family: Rajdhani; font-size: 0.9rem; margin: 0;">{symbol}</p>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
        
        st.markdown(f'<p style="text-align: center; color: #8892b0; font-family: Rajdhani;">🕒 Prices updated: {datetime.now().strftime("%H:%M:%S")}</p>', unsafe_allow_html=True)
    else:
        st.error("❌ Could not fetch crypto prices")
    
    # AUTO-REFRESH NODE DATA SECTION
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<h2 class="section-header">🔄 CONFIDENCE-BASED SIGNALS</h2>', unsafe_allow_html=True)
    with col2:
        if st.button("🔄 UPDATE NODE DATA", key="refresh_main", use_container_width=True):
            with st.spinner("🔄 Updating node data..."):
                if analyzer.update_node_data():
                    st.success("✅ Node data updated successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to update node data")
    
    # Display current node data status
    if analyzer.current_data:
        current_time = datetime.fromisoformat(analyzer.current_data['timestamp'])
        st.markdown(f'<p style="text-align: center; color: #00ffff; font-family: Rajdhani;">📊 Current data from: {current_time.strftime("%Y-%m-%d %H:%M:%S")}</p>', unsafe_allow_html=True)
    
    # CONFIDENCE-BASED SIGNAL ANALYSIS
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">🎯 CONFIDENCE-BASED SIGNAL ANALYSIS</h2>', unsafe_allow_html=True)
    
    # Main content in two columns
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # CONFIDENCE FACTORS ANALYSIS
        st.markdown('<div class="cyber-card">', unsafe_allow_html=True)
        st.markdown('<h3 style="font-family: Orbitron; color: #00ffff; text-align: center;">📊 CONFIDENCE ANALYSIS</h3>', unsafe_allow_html=True)
        
        tor_signal = analyzer.calculate_high_confidence_signal()
        network_signal = analyzer.calculate_network_signal()
        
        # Display confidence level with color coding
        confidence = tor_signal['confidence']
        if confidence == "HIGH":
            confidence_color = "#00ff00"
            confidence_emoji = "🟢"
        elif confidence == "MEDIUM":
            confidence_color = "#ffff00" 
            confidence_emoji = "🟡"
        else:
            confidence_color = "#ff4444"
            confidence_emoji = "🔴"
        
        st.markdown(f'''
        <div style="text-align: center; margin: 1rem 0;">
            <h3 style="font-family: Orbitron; color: {confidence_color}; margin: 0.5rem 0;">
                {confidence_emoji} CONFIDENCE LEVEL: {confidence}
            </h3>
        </div>
        ''', unsafe_allow_html=True)
        
        # Display node comparison
        if analyzer.previous_data:
            col1a, col2a = st.columns(2)
            
            with col1a:
                st.metric("🕒 PREVIOUS TOR NODES", f"{tor_signal['previous_tor']:,}")
                st.metric("🕒 PREVIOUS TOTAL", f"{network_signal['previous_total']:,}")
                st.metric("📊 ACTIVE RATIO", f"{tor_signal['active_ratio']:.3f}")
            
            with col2a:
                st.metric("🟢 CURRENT TOR NODES", f"{tor_signal['current_tor']:,}")
                st.metric("🟢 CURRENT TOTAL", f"{tor_signal['total_nodes']:,}")
                st.metric("🌐 NETWORK SIZE", "LARGE" if tor_signal['total_nodes'] > 10000 else "MEDIUM" if tor_signal['total_nodes'] > 8000 else "SMALL")
            
            # Display changes
            st.markdown('<div style="text-align: center; margin: 1rem 0;">', unsafe_allow_html=True)
            st.metric("📈 TOR NODE CHANGE", f"{tor_signal['tor_change']:+,}", delta=f"{tor_signal['percentage_change']:+.1f}%")
            st.metric("📈 TOTAL NODE CHANGE", f"{network_signal['total_change']:+,}", delta="nodes")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("🔄 Update node data to see comparison (current → previous)")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        # SIGNAL RESULTS WITH CONFIDENCE
        st.markdown('<div class="cyber-card">', unsafe_allow_html=True)
        st.markdown('<h3 style="font-family: Orbitron; color: #00ffff; text-align: center;">🎯 SIGNAL RESULTS</h3>', unsafe_allow_html=True)
        
        if analyzer.current_data:
            # Display confidence factors
            st.markdown('<h4 style="font-family: Orbitron; color: #00ffff; margin: 1rem 0 0.5rem 0;">Confidence Factors:</h4>', unsafe_allow_html=True)
            
            for factor in tor_signal['confidence_factors']:
                if factor.startswith('LARGE') or factor == 'HEALTHY_ACTIVE_RATIO':
                    factor_emoji = "✅"
                    factor_color = "#00ff00"
                elif factor.startswith('MEDIUM') or factor == 'MODERATE_ACTIVE_RATIO':
                    factor_emoji = "⚠️"
                    factor_color = "#ffff00"
                else:
                    factor_emoji = "❌"
                    factor_color = "#ff4444"
                
                # Convert factor to readable text
                readable_factor = factor.replace('_', ' ').title()
                st.markdown(f'<p style="color: {factor_color}; font-family: Rajdhani; margin: 0.2rem 0;">{factor_emoji} {readable_factor}</p>', unsafe_allow_html=True)
            
            # Display signals
            st.markdown('<div style="text-align: center; margin: 1rem 0;">', unsafe_allow_html=True)
            st.metric("🎯 TRADING SIGNAL", tor_signal['signal'])
            st.metric("📡 MARKET BIAS", tor_signal['bias'])
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Display reasoning
            st.markdown(f'''
            <div style="background: rgba(0, 0, 0, 0.3); padding: 1rem; border-radius: 10px; margin: 1rem 0;">
                <p style="color: #8892b0; font-family: Rajdhani; font-size: 0.9rem; margin: 0;">
                <strong>Reasoning:</strong> {tor_signal['reasoning']}
                </p>
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.info("🔄 Update node data to see signals")
        
        st.markdown('</div>', unsafe_allow_html=True)
              # MAIN SIGNAL DISPLAY WITH CONFIDENCE
    if analyzer.current_data and analyzer.previous_data:
        tor_signal_data = analyzer.calculate_high_confidence_signal()
        
        # Determine signal styling based on confidence and direction
        if "SELL" in tor_signal_data['signal']:
            if tor_signal_data['confidence'] == "HIGH":
                signal_class = "signal-sell"
                emoji = "🔴"
                confidence_text = "HIGH CONFIDENCE"
            elif tor_signal_data['confidence'] == "MEDIUM":
                signal_class = "signal-sell"
                emoji = "🔴"
                confidence_text = "MEDIUM CONFIDENCE"
            else:
                signal_class = "signal-neutral"
                emoji = "🟡"
                confidence_text = "LOW CONFIDENCE"
        elif "BUY" in tor_signal_data['signal']:
            if tor_signal_data['confidence'] == "HIGH":
                signal_class = "signal-buy"
                emoji = "🟢"
                confidence_text = "HIGH CONFIDENCE"
            elif tor_signal_data['confidence'] == "MEDIUM":
                signal_class = "signal-buy"
                emoji = "🟢"
                confidence_text = "MEDIUM CONFIDENCE"
            else:
                signal_class = "signal-neutral"
                emoji = "🟡"
                confidence_text = "LOW CONFIDENCE"
        else:
            signal_class = "signal-neutral"
            emoji = "🟡"
            confidence_text = "NEUTRAL"
        
        st.markdown(f'<div class="{signal_class}">', unsafe_allow_html=True)
        st.markdown(f'<h2 style="font-family: Orbitron; text-align: center; margin: 0.5rem 0;">🚀 {tor_signal_data["signal"]} {emoji}</h2>', unsafe_allow_html=True)
        st.markdown(f'<h3 style="font-family: Orbitron; text-align: center; margin: 0.5rem 0;">{confidence_text} • {tor_signal_data["bias"]}</h3>', unsafe_allow_html=True)
        st.markdown(f'<p style="text-align: center; color: #8892b0; font-family: Rajdhani; margin: 0.5rem 0;">{tor_signal_data["reasoning"]}</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="text-align: center; font-family: Orbitron; color: #ffffff; margin: 0.5rem 0;">Tor Change: {tor_signal_data["tor_change"]:+,} nodes ({tor_signal_data["percentage_change"]:+.1f}%)</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # MULTI-COIN SIGNALS WITH CONFIDENCE
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">🎯 CONFIDENCE-BASED COIN SIGNALS</h2>', unsafe_allow_html=True)
    
    if analyzer.current_data and analyzer.previous_data:
        tor_signal_data = analyzer.calculate_high_confidence_signal()
        
        # Apply Tor trend analysis to all coins
        coins_list = [
            'BTCUSDT', 'ETHUSDT', 'LTCUSDT', 'BCHUSDT', 'SOLUSDT', 
            'ADAUSDT', 'AVAXUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'BNBUSDT'
        ]
        
        # Create columns for coin signals
        signal_cols = st.columns(4)
        
        for idx, symbol in enumerate(coins_list):
            if prices.get(symbol):
                with signal_cols[idx % 4]:
                    emoji = get_coin_emoji(symbol)
                    name = get_coin_display_name(symbol)
                    price = prices[symbol]
                    
                    # Apply confidence-based styling
                    if "SELL" in tor_signal_data['signal']:
                        if tor_signal_data['confidence'] == "HIGH":
                            signal_class = "signal-sell"
                            signal_text = "HIGH CONF SELL"
                            signal_emoji = "🔴"
                        elif tor_signal_data['confidence'] == "MEDIUM":
                            signal_class = "signal-sell"
                            signal_text = "MED CONF SELL"
                            signal_emoji = "🔴"
                        else:
                            signal_class = "signal-neutral"
                            signal_text = "LOW CONF SELL"
                            signal_emoji = "🟡"
                    elif "BUY" in tor_signal_data['signal']:
                        if tor_signal_data['confidence'] == "HIGH":
                            signal_class = "signal-buy"
                            signal_text = "HIGH CONF BUY"
                            signal_emoji = "🟢"
                        elif tor_signal_data['confidence'] == "MEDIUM":
                            signal_class = "signal-buy"
                            signal_text = "MED CONF BUY"
                            signal_emoji = "🟢"
                        else:
                            signal_class = "signal-neutral"
                            signal_text = "LOW CONF BUY"
                            signal_emoji = "🟡"
                    else:
                        signal_class = "signal-neutral"
                        signal_text = tor_signal_data['signal']
                        signal_emoji = "🟡"
                    
                    st.markdown(f'''
                    <div class="{signal_class}" style="padding: 1rem; margin: 0.5rem 0;">
                        <div style="text-align: center;">
                            <h4 style="font-family: Orbitron; margin: 0.5rem 0; font-size: 1.1rem;">{emoji} {name}</h4>
                            <p style="font-family: Orbitron; font-size: 1.2rem; font-weight: 700; margin: 0.5rem 0;">${price:,.2f}</p>
                            <p style="font-family: Orbitron; font-size: 1rem; margin: 0.5rem 0;">{signal_emoji} {signal_text}</p>
                            <p style="color: #8892b0; font-family: Rajdhani; font-size: 0.8rem; margin: 0.2rem 0;">Confidence: {tor_signal_data['confidence']}</p>
                            <p style="color: #8892b0; font-family: Rajdhani; font-size: 0.7rem; margin: 0;">Δ Tor: {tor_signal_data['tor_change']:+,}</p>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
    else:
        st.info("🔄 Update node data to see multi-coin signals")
    
    # CONFIDENCE EXPLANATION SECTION
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="cyber-card">
    <h3 style="font-family: Orbitron; color: #00ffff; text-align: center;">⚡ CONFIDENCE LEVELS EXPLAINED</h3>
    <div style="text-align: center;">
        <p style="color: #8892b0; font-family: Rajdhani; margin: 0.5rem 0;">
        <span style="color: #00ff00;">🟢 HIGH CONFIDENCE:</span> Large Tor changes (>50 nodes, >5%) + Healthy network<br>
        <span style="color: #ffff00;">🟡 MEDIUM CONFIDENCE:</span> Moderate changes (25-50 nodes, 2.5-5%) + Stable network<br>
        <span style="color: #ff4444;">🔴 LOW CONFIDENCE:</span> Small changes or unstable network conditions<br>
        <strong>Recommendation:</strong> Only trade on MEDIUM or HIGH confidence signals
        </p>
    </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Abdullah's Futuristic Trademark Footer
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="trademark">
    <p>⚡ CONFIDENCE-BASED TOR SIGNAL ANALYZER ⚡</p>
    <p>© 2025 ABDULLAH'S CRYPTO TRACKER • SMART SIGNAL CONFIDENCE SYSTEM</p>
    <p style="font-size: 0.7rem; color: #556699;">TRADE ONLY ON MEDIUM/HIGH CONFIDENCE SIGNALS FOR BETTER RESULTS</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()