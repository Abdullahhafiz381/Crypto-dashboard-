import ccxt
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime

# ====================
# GODZILLERS BRANDING & PAGE CONFIG
# ====================
st.set_page_config(
    page_title="GODZILLERS Trading Signals",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inject custom CSS for red/black theme
st.markdown("""
<style>
    /* Main GODZILLERS Theme */
    .stApp {
        background: linear-gradient(180deg, #0a0a0a 0%, #1a0a0a 100%);
        color: #ffffff;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #ff0000 !important;
        font-family: 'Arial Black', sans-serif;
        text-shadow: 0 0 10px rgba(255, 0, 0, 0.3);
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        color: #ff0000 !important;
        font-size: 2rem !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #ff0000, #8b0000) !important;
        color: white !important;
        border: 2px solid #ff0000 !important;
        border-radius: 10px !important;
        font-weight: bold !important;
        transition: all 0.3s !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(90deg, #8b0000, #ff0000) !important;
        box-shadow: 0 0 15px #ff0000 !important;
        transform: scale(1.05) !important;
    }
    
    /* Signal Cards */
    .signal-card {
        background: rgba(10, 10, 10, 0.9) !important;
        border: 2px solid #ff0000 !important;
        border-radius: 15px !important;
        padding: 20px !important;
        margin: 10px 0 !important;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.2) !important;
    }
    
    /* Strength Bar */
    .strength-bar-container {
        height: 30px;
        background: #333;
        border-radius: 15px;
        margin: 15px 0;
        overflow: hidden;
    }
    
    .strength-bar-fill {
        height: 100%;
        border-radius: 15px;
        transition: width 1s ease-in-out;
    }
    
    /* Price Signal Display */
    .price-signal {
        font-size: 3.5rem !important;
        font-weight: bold !important;
        text-align: center !important;
        margin: 20px 0 !important;
        text-shadow: 0 0 20px rgba(255, 0, 0, 0.5) !important;
    }
</style>
""", unsafe_allow_html=True)

# ====================
# GODZILLERS HEADER
# ====================
col1, col2, col3 = st.columns([1, 3, 1])
with col2:
    st.markdown("<h1 style='text-align: center;'>🔥 GODZILLERS TRADING SIGNALS 🔥</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: #cccccc;'>Professional Crypto Futures Intelligence</h3>", unsafe_allow_html=True)

st.markdown("---")

# ====================
# INITIALIZATION
# ====================
@st.cache_resource
def init_okx_exchange():
    """Initialize OKX exchange connection"""
    try:
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        })
        exchange.fetch_time()
        return exchange
    except Exception as e:
        st.error(f"❌ Exchange Connection Failed: {str(e)[:100]}")
        return None

exchange = init_okx_exchange()

# ====================
# SESSION STATE SETUP
# ====================
if 'order_book_depth' not in st.session_state:
    st.session_state.order_book_depth = 10

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = "Never"

if 'signal_data' not in st.session_state:
    st.session_state.signal_data = None

# ====================
# CONTROL PANEL
# ====================
st.markdown("### 🎮 CONTROL PANEL")

control_col1, control_col2, control_col3, control_col4 = st.columns(4)

with control_col1:
    # Order Book Depth Selection - ALL LEVELS INCLUDED
    depth = st.radio(
        "Order Book Analysis",
        ["1 Level (Fast)", "10 Levels", "50 Levels", "100 Levels (Deep)"],
        horizontal=False
    )
    
    # Map selection to numerical value
    if depth == "1 Level (Fast)":
        st.session_state.order_book_depth = 1
    elif depth == "10 Levels":
        st.session_state.order_book_depth = 10
    elif depth == "50 Levels":
        st.session_state.order_book_depth = 50
    elif depth == "100 Levels (Deep)":
        st.session_state.order_book_depth = 100

with control_col2:
    symbol = st.selectbox(
        "Select Coin",
        ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        index=0
    )

with control_col3:
    refresh_clicked = st.button(
        "🔄 REFRESH SIGNALS",
        use_container_width=True,
        type="primary"
    )

with control_col4:
    st.metric("Last Update", st.session_state.last_refresh)

st.markdown("---")

# ====================
# DATA FETCHING FUNCTIONS
# ====================
def fetch_market_data():
    if not exchange:
        st.error("Exchange not connected.")
        return None
    
    try:
        coin_name = symbol.split('/')[0]
        # Fetch order book with selected depth (1, 10, 50, or 100 levels)
        order_book = exchange.fetch_order_book(
            symbol, 
            limit=st.session_state.order_book_depth
        )
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=50)
        
        return {
            'coin': coin_name,
            'order_book': order_book,
            'ohlcv': ohlcv,
            'timestamp': datetime.now(),
            'depth': st.session_state.order_book_depth
        }
        
    except Exception as e:
        st.error(f"Data fetch failed: {str(e)[:100]}")
        return None

def calculate_advanced_signal(market_data):
    if not market_data:
        return None
    
    order_book = market_data['order_book']
    ohlcv = market_data['ohlcv']
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])
    
    if not bids or not asks:
        return None
    
    # Extract data based on selected depth
    depth = market_data['depth']
    
    # Calculate volumes based on selected depth
    if depth == 1:
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        V_bid = float(bids[0][1])
        V_ask = float(asks[0][1])
    else:
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        # Sum volumes up to selected depth
        V_bid = sum(float(bid[1]) for bid in bids[:depth])
        V_ask = sum(float(ask[1]) for ask in asks[:depth])
    
    # Core calculations
    P = (best_bid + best_ask) / 2  # Current price
    total_volume = V_bid + V_ask
    I = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    S = best_ask - best_bid
    phi = S / P if P > 0 else 0.0001
    
    # Calculate volatility
    if len(ohlcv) > 20:
        closes = [candle[4] for candle in ohlcv]
        returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
        sigma = np.std(returns[-20:]) if len(returns) >= 20 else 0.01
    else:
        sigma = 0.01
    
    # Generate signal value
    if phi > 0 and sigma > 0:
        signal_value = np.sign(I) * (abs(I) / (phi * sigma))
    else:
        signal_value = 0
    
    # CALCULATE STRENGTH PERCENTAGE (0-100%)
    raw_strength = abs(signal_value)
    strength_percentage = min(100.0, np.tanh(raw_strength) * 100)
    
    # Determine leverage based on strength percentage
    if strength_percentage > 70:
        leverage = "MAX LEVERAGE"
        confidence = "HIGH"
    elif strength_percentage > 40:
        leverage = "MEDIUM LEVERAGE"
        confidence = "MODERATE"
    elif strength_percentage > 15:
        leverage = "LOW LEVERAGE"
        confidence = "LOW"
    else:
        leverage = "NO LEVERAGE"
        confidence = "NEUTRAL"
    
    # DETERMINE DIRECTION AND CURRENT PRICE
    current_price = P  # Using mid price as current price
    
    if signal_value > 0.1:
        direction = "LONG"
        direction_emoji = "📈"
    elif signal_value < -0.1:
        direction = "SHORT"
        direction_emoji = "📉"
    else:
        direction = "NEUTRAL"
        direction_emoji = "➖"
    
    # Calculate volume at different depth segments for analysis
    if depth >= 50:
        # Volume in first 10 levels
        V_bid_10 = sum(float(bid[1]) for bid in bids[:10])
        V_ask_10 = sum(float(ask[1]) for ask in asks[:10])
        # Volume in levels 11-50
        V_bid_11_50 = sum(float(bid[1]) for bid in bids[10:50]) if depth >= 50 else 0
        V_ask_11_50 = sum(float(ask[1]) for ask in asks[10:50]) if depth >= 50 else 0
    else:
        V_bid_10 = V_bid
        V_ask_10 = V_ask
        V_bid_11_50 = 0
        V_ask_11_50 = 0
    
    return {
        'coin': market_data['coin'],
        'exchange': 'OKX',
        'leverage': leverage,
        'confidence': confidence,
        'direction': direction,
        'direction_emoji': direction_emoji,
        'signal_value': signal_value,
        'strength_percentage': strength_percentage,
        'current_price': current_price,
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread': S,
        'total_bid_volume': V_bid,
        'total_ask_volume': V_ask,
        'volume_ratio': V_bid / V_ask if V_ask > 0 else 1,
        'depth_analysis': depth,
        'v_bid_10': V_bid_10,
        'v_ask_10': V_ask_10,
        'v_bid_11_50': V_bid_11_50,
        'v_ask_11_50': V_ask_11_50,
        'timestamp': market_data['timestamp']
    }

# ====================
# MAIN DISPLAY
# ====================
if refresh_clicked or st.session_state.signal_data is None:
    with st.spinner("🔥 Analyzing Market Data..."):
        market_data = fetch_market_data()
        if market_data:
            signal_data = calculate_advanced_signal(market_data)
            st.session_state.signal_data = signal_data
            st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
            st.rerun()

if st.session_state.signal_data:
    signal = st.session_state.signal_data
    
    # PRICE SIGNAL DISPLAY (MAIN FEATURE)
    st.markdown("### ⚡ LIVE TRADING SIGNAL")
    
    # Calculate price and format it
    current_price = signal['current_price']
    price_display = f"{current_price:,.0f}" if current_price > 1000 else f"{current_price:.2f}"
    
    # Direction color
    direction_color = '#00ff00' if signal['direction'] == 'LONG' else '#ff0000' if signal['direction'] == 'SHORT' else '#cccccc'
    
    # Main price signal display - format: "BTC 87888 LONG"
    st.markdown(f"""
    <div class='signal-card'>
        <div style='text-align: center;'>
            <div class='price-signal' style='color: {direction_color};'>
                {signal['coin']} {price_display} {signal['direction']}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Strength percentage display
    st.markdown(f"""
    <div style='text-align: center; margin: 20px 0;'>
        <h2>Signal Strength: <span style='color: #ff0000;'>{signal['strength_percentage']:.1f}%</span></h2>
    </div>
    """, unsafe_allow_html=True)
    
    # Strength visualization
    strength_color = "#00ff00" if signal['strength_percentage'] > 70 else "#ffaa00" if signal['strength_percentage'] > 40 else "#ff4444"
    
    st.markdown(f"""
    <div style='margin: 20px 0;'>
        <div class='strength-bar-container'>
            <div class='strength-bar-fill' style='width: {signal['strength_percentage']}%; background: {strength_color};'></div>
        </div>
        <div style='display: flex; justify-content: space-between; color: #ccc; font-size: 12px;'>
            <span>0%</span>
            <span>25%</span>
            <span>50%</span>
            <span>75%</span>
            <span>100%</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Trading Details in Columns
    st.markdown("#### 📊 TRADING DETAILS")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Coin", signal['coin'])
        st.metric("Exchange", signal['exchange'])
    
    with col2:
        st.metric("Recommended Leverage", signal['leverage'])
        st.metric("Confidence", signal['confidence'])
    
    with col3:
        st.metric("Direction", f"{signal['direction_emoji']} {signal['direction']}")
        st.metric("Current Price", f"{signal['current_price']:,.2f}")
    
    with col4:
        st.metric("Bid/Ask Spread", f"{signal['spread']:.4f}")
        st.metric("Volume Ratio", f"{signal['volume_ratio']:.2f}")
    
    # Order Book Analysis Details
    st.markdown("---")
    st.markdown("#### 📖 ORDER BOOK ANALYSIS")
    
    depth = signal['depth_analysis']
    analysis_col1, analysis_col2, analysis_col3 = st.columns(3)
    
    with analysis_col1:
        st.markdown(f"**Analysis Depth:** {depth} Levels")
        if depth == 100:
            st.success("✅ Deep analysis (100 levels)")
        elif depth == 50:
            st.info("📊 Moderate depth (50 levels)")
        elif depth == 10:
            st.info("⚡ Standard depth (10 levels)")
        else:
            st.info("🚀 Fast analysis (1 level)")
        
        st.metric("Total Bid Volume", f"{signal['total_bid_volume']:.2f}")
        st.metric("Total Ask Volume", f"{signal['total_ask_volume']:.2f}")
    
    with analysis_col2:
        st.markdown("**Price Levels**")
        st.markdown(f"**Best Bid:** `{signal['best_bid']:,.2f}`")
        st.markdown(f"**Best Ask:** `{signal['best_ask']:,.2f}`")
        st.markdown(f"**Mid Price:** `{signal['current_price']:,.2f}`")
        
        if depth >= 10:
            # Show depth distribution
            st.markdown("**Volume Distribution**")
            if depth >= 50:
                st.markdown(f"• Levels 1-10: {signal['v_bid_10'] + signal['v_ask_10']:.1f}")
                st.markdown(f"• Levels 11-50: {signal['v_bid_11_50'] + signal['v_ask_11_50']:.1f}")
    
    with analysis_col3:
        st.markdown("**Signal Info**")
        st.markdown(f"**Analysis Time:** {st.session_state.last_refresh}")
        st.markdown(f"**Raw Signal Value:** `{signal['signal_value']:.4f}`")
        st.markdown(f"**Imbalance (I):** `{((signal['total_bid_volume'] - signal['total_ask_volume']) / (signal['total_bid_volume'] + signal['total_ask_volume']) if (signal['total_bid_volume'] + signal['total_ask_volume']) > 0 else 0):.4f}`")
    
    # Quick Order Book Preview
    try:
        if exchange and st.session_state.signal_data:
            # Show top 5 levels for preview
            preview_depth = min(5, depth)
            order_book = exchange.fetch_order_book(symbol, limit=preview_depth)
            
            st.markdown(f"##### 👁️ TOP {preview_depth} ORDER BOOK LEVELS")
            book_col1, book_col2 = st.columns(2)
            
            with book_col1:
                st.markdown("**🟢 BIDS**")
                for i, (price, volume) in enumerate(order_book['bids'][:preview_depth]):
                    st.code(f"{price:>12.2f} | {volume:>10.4f}")
            
            with book_col2:
                st.markdown("**🔴 ASKS**")
                for i, (price, volume) in enumerate(order_book['asks'][:preview_depth]):
                    st.code(f"{price:>12.2f} | {volume:>10.4f}")
    except:
        st.info("Order book preview temporarily unavailable")

# ====================
# FOOTER & BRANDING
# ====================
st.markdown("---")

footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.markdown("""
    <div style='text-align: center; padding: 20px; border-top: 2px solid #ff0000;'>
        <h3 style='color: #ff0000;'>GODZILLERS TRADING SIGNALS</h3>
        <p style='color: #cccccc;'>Professional Algorithmic Trading Intelligence</p>
        <p style='color: #666666; font-size: 0.9em;'>
            Signals update on manual refresh only. Trade responsibly with proper risk management.<br>
            High order book depth (50/100 levels) provides deeper market liquidity analysis.
        </p>
        <p style='color: #ff0000; font-weight: bold; font-size: 1.2em;'>MADE BY GODZILLERS TEAM</p>
    </div>
    """, unsafe_allow_html=True)

# ====================
# MANUAL REFRESH ONLY - NO AUTO-REFRESH
# ====================
# The application only updates when the refresh button is clicked
# No while loops or automatic refresh mechanisms