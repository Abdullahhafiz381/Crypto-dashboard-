import ccxt
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

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
        transition: width 0.3s ease-in-out;
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
    st.markdown("<h3 style='text-align: center; color: #cccccc;'>Real-Time Lightning Fast Analysis</h3>", unsafe_allow_html=True)

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
        "⚡ INSTANT REFRESH",
        use_container_width=True,
        type="primary"
    )

with control_col4:
    st.metric("Last Update", st.session_state.last_refresh)

st.markdown("---")

# ====================
# LEVERAGE PARAMETERS (FIXED - AUTOMATIC)
# ====================
LEVERAGE_PARAMS = {
    'alpha': 50.0,      # Fixed: Leverage scaling factor
    'L0': 5.0,          # Fixed: Base leverage
    'min_vol': 0.001,   # Fixed: Minimum volatility
    'max_leverage': 100.0,  # Fixed: Safety cap
    'min_leverage': 1.0     # Fixed: Minimum leverage
}

# ====================
# FAST FUNCTIONS (OPTIMIZED FOR SPEED)
# ====================
def calculate_fast_volatility(ohlcv_data):
    """
    FAST volatility calculation - uses recent data only
    """
    try:
        if len(ohlcv_data) < 20:
            return 0.01
        
        # Use only last 50 candles for speed
        recent_candles = ohlcv_data[-50:] if len(ohlcv_data) > 50 else ohlcv_data
        closes = [candle[4] for candle in recent_candles]
        
        # Fast returns calculation
        returns = []
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                returns.append(np.log(closes[i] / closes[i-1]))
        
        if len(returns) < 10:
            return 0.01
        
        # Fast standard deviation
        return float(np.std(returns))
        
    except Exception as e:
        return 0.01

def calculate_automatic_leverage(theta_t):
    """
    AUTOMATIC leverage calculation (optimized)
    """
    alpha = LEVERAGE_PARAMS['alpha']
    L0 = LEVERAGE_PARAMS['L0']
    min_vol = LEVERAGE_PARAMS['min_vol']
    max_leverage = LEVERAGE_PARAMS['max_leverage']
    min_leverage = LEVERAGE_PARAMS['min_leverage']
    
    theta_t = max(theta_t, min_vol)
    raw_leverage = 1 + (alpha * L0 / theta_t)
    return min(max(min_leverage, raw_leverage), max_leverage)

# ====================
# ULTRA-FAST DATA FETCHING
# ====================
def fetch_real_time_data():
    """
    FETCH REAL-TIME DATA - OPTIMIZED FOR SPEED
    Returns data at exact refresh moment
    """
    if not exchange:
        st.error("Exchange not connected.")
        return None
    
    try:
        coin_name = symbol.split('/')[0]
        
        # 1. Get TICKER FIRST for real-time price (fastest)
        ticker = exchange.fetch_ticker(symbol)
        ticker_price = ticker['last'] if ticker and 'last' in ticker else 0
        
        # 2. Get order book data
        depth_limit = st.session_state.order_book_depth
        order_book = exchange.fetch_order_book(symbol, limit=depth_limit)
        
        # 3. Get minimal OHLCV for volatility (fast)
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=50)
        
        # Capture exact timestamp
        exact_time = datetime.now()
        
        return {
            'coin': coin_name,
            'ticker_price': ticker_price,  # REAL-TIME PRICE
            'order_book': order_book,
            'ohlcv': ohlcv,
            'exact_timestamp': exact_time,
            'depth': depth_limit
        }
        
    except Exception as e:
        st.error(f"⚠️ Data fetch error: {str(e)[:100]}")
        return None

def calculate_instant_signal(market_data):
    """
    ULTRA-FAST signal calculation
    Returns signal in milliseconds
    """
    if not market_data:
        return None
    
    order_book = market_data['order_book']
    ohlcv = market_data['ohlcv']
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])
    
    if not bids or not asks:
        return None
    
    depth = market_data['depth']
    
    # 1. REAL-TIME PRICE from ticker
    real_time_price = market_data['ticker_price']
    
    # 2. Order book data
    best_bid = float(bids[0][0]) if bids and len(bids) > 0 else 0
    best_ask = float(asks[0][0]) if asks and len(asks) > 0 else 0
    
    # Fast volume calculation
    if depth == 1:
        V_bid = float(bids[0][1]) if bids and len(bids) > 0 else 0
        V_ask = float(asks[0][1]) if asks and len(asks) > 0 else 0
    else:
        V_bid = sum(float(bid[1]) for bid in bids[:depth])
        V_ask = sum(float(ask[1]) for ask in asks[:depth])
    
    # 3. Spread calculations
    spread = best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0.01
    relative_spread = spread / real_time_price if real_time_price > 0 else 0.0001
    
    # 4. Volume imbalance
    total_volume = V_bid + V_ask
    imbalance = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    
    # 5. FAST volatility calculation
    theta_t = calculate_fast_volatility(ohlcv)
    
    # 6. AUTOMATIC leverage
    max_leverage = calculate_automatic_leverage(theta_t)
    
    # 7. FAST signal calculation
    if relative_spread > 0 and theta_t > 0:
        raw_signal = imbalance * (abs(imbalance) / (relative_spread * theta_t))
    else:
        raw_signal = 0
    
    # 8. Strength percentage
    raw_strength = abs(raw_signal)
    strength_percentage = min(100.0, np.tanh(raw_strength) * 100)
    
    # 9. FAST direction detection
    if imbalance > 0.05:  # Threshold for clear direction
        direction = "LONG"
        direction_emoji = "📈"
        direction_text = "STRONG BUY PRESSURE"
    elif imbalance < -0.05:
        direction = "SHORT"
        direction_emoji = "📉"
        direction_text = "STRONG SELL PRESSURE"
    elif imbalance > 0.01:
        direction = "LONG"
        direction_emoji = "↗️"
        direction_text = "MODERATE BUY PRESSURE"
    elif imbalance < -0.01:
        direction = "SHORT"
        direction_emoji = "↘️"
        direction_text = "MODERATE SELL PRESSURE"
    else:
        direction = "NEUTRAL"
        direction_emoji = "➖"
        direction_text = "MARKET BALANCED"
    
    # 10. FAST leverage recommendation
    if strength_percentage > 70:
        confidence = "HIGH"
        leverage_multiplier = 0.9
    elif strength_percentage > 40:
        confidence = "MODERATE"
        leverage_multiplier = 0.6
    elif strength_percentage > 15:
        confidence = "LOW"
        leverage_multiplier = 0.3
    else:
        confidence = "VERY LOW"
        leverage_multiplier = 0.1
    
    recommended_leverage = max_leverage * leverage_multiplier
    recommended_leverage = round(max(1.0, recommended_leverage), 1)
    
    return {
        # REAL-TIME DATA
        'coin': market_data['coin'],
        'current_price': real_time_price,  # EXACT PRICE AT REFRESH
        'direction': direction,
        'direction_emoji': direction_emoji,
        'direction_text': direction_text,
        'strength_percentage': strength_percentage,
        'confidence': confidence,
        'recommended_leverage': recommended_leverage,
        'max_leverage': max_leverage,
        
        # Market metrics
        'volatility': theta_t,
        'imbalance': imbalance,
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread': spread,
        'total_bid_volume': V_bid,
        'total_ask_volume': V_ask,
        'depth_analysis': depth,
        'exact_timestamp': market_data['exact_timestamp'],
        'order_book_timestamp': datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Milliseconds
    }

# ====================
# INSTANT REFRESH SYSTEM
# ====================
if refresh_clicked or st.session_state.signal_data is None:
    with st.spinner("⚡ INSTANT ANALYSIS..."):
        # Clear cache for fresh data
        st.cache_data.clear()
        
        # Fetch real-time data
        market_data = fetch_real_time_data()
        
        if market_data:
            # Calculate signal instantly
            signal_data = calculate_instant_signal(market_data)
            
            if signal_data:
                st.session_state.signal_data = signal_data
                st.session_state.last_refresh = signal_data['exact_timestamp'].strftime("%H:%M:%S.%f")[:-3]
                st.rerun()
        else:
            st.error("Failed to fetch real-time data")

# ====================
# REAL-TIME DISPLAY
# ====================
if st.session_state.signal_data is not None:
    signal = st.session_state.signal_data
    
    # ========================================
    # REAL-TIME SIGNAL DISPLAY
    # ========================================
    st.markdown("### ⚡ REAL-TIME TRADING SIGNAL")
    
    # EXACT PRICE at refresh moment
    current_price = signal.get('current_price', 0)
    price_display = f"{current_price:,.0f}" if current_price > 1000 else f"{current_price:.2f}"
    
    # Direction color
    direction_color = '#00ff00' if signal.get('direction') == 'LONG' else '#ff0000' if signal.get('direction') == 'SHORT' else '#cccccc'
    
    # REAL-TIME PRICE with timestamp
    exact_time = signal.get('exact_timestamp', datetime.now())
    timestamp_str = exact_time.strftime("%H:%M:%S.%f")[:-3]  # Milliseconds
    
    st.markdown(f"""
    <div class='signal-card'>
        <div style='text-align: center;'>
            <div class='price-signal' style='color: {direction_color};'>
                {signal.get('coin', 'N/A')} {price_display} {signal.get('direction', 'NEUTRAL')}
            </div>
            <p style='color: #cccccc; font-size: 1.2rem;'>
                ⏱️ Price captured at: {timestamp_str} | {signal.get('direction_text', '')}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ========================================
    # FAST METRICS DISPLAY
    # ========================================
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Signal Strength", f"{signal.get('strength_percentage', 0):.1f}%")
        st.metric("Confidence", signal.get('confidence', 'N/A'))
    
    with col2:
        st.metric("Leverage", f"{signal.get('recommended_leverage', 0):.1f}x")
        st.metric("Max Allowed", f"{signal.get('max_leverage', 0):.1f}x")
    
    with col3:
        st.metric("Current Price", f"{signal.get('current_price', 0):,.2f}")
        st.metric("Volatility", f"{signal.get('volatility', 0)*100:.2f}%")
    
    with col4:
        st.metric("Bid/Ask", f"{signal.get('best_bid', 0):,.2f} / {signal.get('best_ask', 0):,.2f}")
        st.metric("Imbalance", f"{signal.get('imbalance', 0):.4f}")
    
    # ========================================
    # SPEED INDICATOR
    # ========================================
    st.markdown("---")
    
    speed_col1, speed_col2, speed_col3 = st.columns(3)
    
    with speed_col1:
        st.markdown("##### ⚡ PERFORMANCE")
        st.success("✅ Real-Time Analysis")
        st.info("🎯 Exact Price Capture")
    
    with speed_col2:
        st.markdown("##### 📊 ORDER BOOK")
        depth = signal.get('depth_analysis', 0)
        if depth == 1:
            st.success(f"🚀 Ultra Fast ({depth} level)")
        elif depth <= 10:
            st.info(f"⚡ Fast ({depth} levels)")
        elif depth <= 50:
            st.info(f"📊 Detailed ({depth} levels)")
        else:
            st.warning(f"🧠 Deep Analysis ({depth} levels)")
        
        st.metric("Bid Volume", f"{signal.get('total_bid_volume', 0):.1f}")
        st.metric("Ask Volume", f"{signal.get('total_ask_volume', 0):.1f}")
    
    with speed_col3:
        st.markdown("##### 🕒 TIMING")
        st.metric("Last Refresh", st.session_state.last_refresh)
        st.metric("Data Age", "Real-Time")

# ====================
# FOOTER & BRANDING
# ====================
st.markdown("---")

footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.markdown("""
    <div style='text-align: center; padding: 20px; border-top: 2px solid #ff0000;'>
        <h3 style='color: #ff0000;'>GODZILLERS REAL-TIME SIGNALS</h3>
        <p style='color: #cccccc;'>Lightning Fast • Exact Price Capture</p>
        <p style='color: #666666; font-size: 0.9em;'>
            ⚡ Instant analysis on every refresh<br>
            🎯 Exact price captured at refresh moment<br>
            🔄 No delays • Real-time data only<br>
            ⏱️ Millisecond precision timing
        </p>
        <p style='color: #ff0000; font-weight: bold; font-size: 1.2em;'>MADE BY GODZILLERS TEAM</p>
    </div>
    """, unsafe_allow_html=True)