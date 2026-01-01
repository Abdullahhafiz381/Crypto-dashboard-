import ccxt
import pandas as pd
import numpy as np
import streamlit as st
import time
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
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #0a0a0a !important;
        border-right: 2px solid #ff0000 !important;
    }
    
    /* Divider */
    hr {
        border-color: #ff0000 !important;
        height: 2px !important;
        background: linear-gradient(90deg, transparent, #ff0000, transparent) !important;
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
                'defaultType': 'swap',  # Perpetual swaps on OKX
            }
        })
        # Test connection
        exchange.fetch_time()
        return exchange
    except Exception as e:
        st.error(f"❌ Exchange Connection Failed: {str(e)[:100]}")
        return None

# Initialize exchange
exchange = init_okx_exchange()

# ====================
# SESSION STATE SETUP
# ====================
if 'order_book_depth' not in st.session_state:
    st.session_state.order_book_depth = 10  # Default to 10 levels

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
    # Order Book Depth Selection
    depth = st.radio(
        "Order Book Analysis",
        ["10 Levels (Detailed)", "1 Level (Fast)"],
        horizontal=True
    )
    st.session_state.order_book_depth = 10 if "10" in depth else 1

with control_col2:
    # Trading Pair Selection
    symbol = st.selectbox(
        "Select Coin",
        ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        index=0
    )

with control_col3:
    # Manual Refresh Button
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
    """Fetch all required market data"""
    if not exchange:
        st.error("Exchange not connected. Please check API connection.")
        return None
    
    try:
        # Get symbol mapping for OKX
        coin_name = symbol.split('/')[0]
        
        # Fetch order book with selected depth
        order_book = exchange.fetch_order_book(
            symbol, 
            limit=st.session_state.order_book_depth
        )
        
        # Fetch recent OHLCV for volatility
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=50)
        
        return {
            'coin': coin_name,
            'order_book': order_book,
            'ohlcv': ohlcv,
            'timestamp': datetime.now()
        }
        
    except Exception as e:
        st.error(f"Data fetch failed: {str(e)[:100]}")
        return None

def calculate_advanced_signal(market_data):
    """Calculate trading signal based on order book analysis"""
    if not market_data:
        return None
    
    order_book = market_data['order_book']
    ohlcv = market_data['ohlcv']
    
    # Extract bids and asks
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])
    
    if not bids or not asks:
        return None
    
    # Calculate metrics based on selected depth
    if st.session_state.order_book_depth == 1:
        # Level 1 analysis
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        V_bid = float(bids[0][1])
        V_ask = float(asks[0][1])
    else:
        # Level 10 analysis (or selected depth)
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        V_bid = sum(float(bid[1]) for bid in bids[:10])
        V_ask = sum(float(ask[1]) for ask in asks[:10])
    
    # Core calculations
    P = (best_bid + best_ask) / 2
    total_volume = V_bid + V_ask
    I = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    S = best_ask - best_bid
    phi = S / P if P > 0 else 0.0001
    
    # Calculate volatility from OHLCV
    if len(ohlcv) > 20:
        closes = [candle[4] for candle in ohlcv]
        returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
        sigma = np.std(returns[-20:]) if len(returns) >= 20 else 0.01
    else:
        sigma = 0.01
    
    # Generate signal
    if phi > 0 and sigma > 0:
        signal_value = np.sign(I) * (abs(I) / (phi * sigma))
    else:
        signal_value = 0
    
    # Determine leverage based on signal strength
    abs_signal = abs(signal_value)
    if abs_signal > 1.5:
        leverage = "MAX LEVERAGE"
        confidence = "HIGH"
    elif abs_signal > 0.7:
        leverage = "MEDIUM LEVERAGE"
        confidence = "MODERATE"
    elif abs_signal > 0.3:
        leverage = "LOW LEVERAGE"
        confidence = "LOW"
    else:
        leverage = "NO LEVERAGE"
        confidence = "NEUTRAL"
    
    # Determine direction
    if signal_value > 0.1:
        direction = "LONG"
        direction_emoji = "📈"
    elif signal_value < -0.1:
        direction = "SHORT"
        direction_emoji = "📉"
    else:
        direction = "NEUTRAL"
        direction_emoji = "➖"
    
    return {
        'coin': market_data['coin'],
        'exchange': 'OKX',
        'leverage': leverage,
        'confidence': confidence,
        'direction': direction,
        'direction_emoji': direction_emoji,
        'signal_value': signal_value,
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread': S,
        'volume_ratio': V_bid / V_ask if V_ask > 0 else 1,
        'timestamp': market_data['timestamp']
    }

# ====================
# MAIN DISPLAY
# ====================
# Trigger data fetch on button click or initial load
if refresh_clicked or st.session_state.signal_data is None:
    with st.spinner("🔥 Analyzing Market Data..."):
        market_data = fetch_market_data()
        if market_data:
            signal_data = calculate_advanced_signal(market_data)
            st.session_state.signal_data = signal_data
            st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
            st.rerun()

# Display signal if available
if st.session_state.signal_data:
    signal = st.session_state.signal_data
    
    # SIGNAL DISPLAY SECTION
    st.markdown("### ⚡ LIVE TRADING SIGNAL")
    
    # Create signal card with GODZILLERS styling
    st.markdown(f"""
    <div class='signal-card'>
        <div style='text-align: center;'>
            <h1 style='color: {'#00ff00' if signal['direction'] == 'LONG' else '#ff0000' if signal['direction'] == 'SHORT' else '#cccccc'};'>
                {signal['direction_emoji']} {signal['direction']} SIGNAL DETECTED
            </h1>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Signal Details in Columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Coin", signal['coin'])
        st.metric("Exchange", signal['exchange'])
    
    with col2:
        st.metric("Recommended Leverage", signal['leverage'])
        st.metric("Confidence", signal['confidence'])
    
    with col3:
        st.metric("Direction", f"{signal['direction_emoji']} {signal['direction']}")
        color = "#00ff00" if signal['signal_value'] > 0 else "#ff0000" if signal['signal_value'] < 0 else "#cccccc"
        st.markdown(f"<h3 style='color: {color};'>Signal Strength: {abs(signal['signal_value']):.2f}</h3>", unsafe_allow_html=True)
    
    with col4:
        st.metric("Best Bid", f"{signal['best_bid']:,.2f}")
        st.metric("Best Ask", f"{signal['best_ask']:,.2f}")
    
    # Market Context
    st.markdown("---")
    st.markdown("#### 📊 MARKET CONTEXT")
    
    ctx_col1, ctx_col2, ctx_col3 = st.columns(3)
    
    with ctx_col1:
        spread_color = "#ff0000" if signal['spread'] > signal['best_bid'] * 0.001 else "#00ff00"
        st.markdown(f"**Spread:** <span style='color:{spread_color}'>{signal['spread']:.4f}</span>", unsafe_allow_html=True)
        st.progress(min(signal['spread'] / (signal['best_bid'] * 0.01), 1.0))
    
    with ctx_col2:
        vol_ratio = signal['volume_ratio']
        vol_color = "#00ff00" if vol_ratio > 1.2 else "#ff9900" if vol_ratio > 0.8 else "#ff0000"
        st.markdown(f"**Bid/Ask Volume Ratio:** <span style='color:{vol_color}'>{vol_ratio:.2f}</span>", unsafe_allow_html=True)
        st.progress(min(vol_ratio / 3, 1.0))
    
    with ctx_col3:
        st.markdown(f"**Order Book Depth:** {st.session_state.order_book_depth} Levels")
        st.markdown(f"**Analysis Time:** {st.session_state.last_refresh}")
    
    # Order Book Preview
    st.markdown("---")
    st.markdown("#### 📖 ORDER BOOK SNAPSHOT")
    
    if exchange and st.session_state.signal_data:
        try:
            order_book = exchange.fetch_order_book(symbol, limit=5)
            
            # Display top 5 bids and asks
            book_col1, book_col2 = st.columns(2)
            
            with book_col1:
                st.markdown("##### 🟢 **TOP BIDS**")
                for i, (price, volume) in enumerate(order_book['bids'][:5]):
                    st.markdown(f"`{price:>12.2f} | {volume:>12.4f}`")
            
            with book_col2:
                st.markdown("##### 🔴 **TOP ASKS**")
                for i, (price, volume) in enumerate(order_book['asks'][:5]):
                    st.markdown(f"`{price:>12.2f} | {volume:>12.4f}`")
                    
        except Exception as e:
            st.info("Order book data temporarily unavailable")

# ====================
# FOOTER & BRANDING
# ====================
st.markdown("---")
st.markdown("")

footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.markdown("""
    <div style='text-align: center; padding: 20px; border-top: 2px solid #ff0000;'>
        <h3 style='color: #ff0000;'>GODZILLERS TRADING SIGNALS</h3>
        <p style='color: #cccccc;'>Professional Algorithmic Trading Intelligence</p>
        <p style='color: #666666; font-size: 0.9em;'>
            Signals update on manual refresh only. Past performance does not guarantee future results.<br>
            Trade responsibly. Use appropriate risk management.
        </p>
        <p style='color: #ff0000; font-weight: bold;'>MADE BY GODZILLERS TEAM</p>
    </div>
    """, unsafe_allow_html=True)

# ====================
# AUTO-REFRESH DISABLED
# ====================
# No while loop or auto-refresh logic exists
# All updates are manual via the refresh button