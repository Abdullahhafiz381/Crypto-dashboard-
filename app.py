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
    st.markdown("<h3 style='text-align: center; color: #cccccc;'>Fully Automatic Leverage Calculation</h3>", unsafe_allow_html=True)

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
    # Order Book Depth Selection
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
# LEVERAGE PARAMETERS (FIXED - NOT USER CONFIGURABLE)
# ====================
# These are automatically calculated by the bot based on volatility
LEVERAGE_PARAMS = {
    'alpha': 50.0,      # Fixed: Leverage scaling factor
    'L0': 5.0,          # Fixed: Base leverage
    'min_vol': 0.001,   # Fixed: Minimum volatility
    'max_leverage': 100.0,  # Fixed: Safety cap
    'min_leverage': 1.0     # Fixed: Minimum leverage
}

# ====================
# ADVANCED FUNCTIONS
# ====================
def calculate_garch_volatility(ohlcv_data):
    """
    Calculate GARCH forecasted volatility AUTOMATICALLY
    """
    try:
        if len(ohlcv_data) < 100:
            # Fallback to simple volatility
            closes = [candle[4] for candle in ohlcv_data]
            returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
            if len(returns) >= 20:
                return np.std(returns[-20:])
            return 0.01
        
        # Extract closing prices
        closes = [candle[4] for candle in ohlcv_data]
        
        # Calculate returns
        prices = pd.Series(closes)
        returns = np.log(prices / prices.shift(1)).dropna()
        
        if len(returns) < 50:
            return np.std(returns)
        
        # GARCH estimation (AUTOMATIC - no user input)
        omega = 0.000001
        alpha = 0.1
        beta = 0.85
        
        variance = np.zeros(len(returns))
        variance[0] = np.var(returns[:20])
        
        # GARCH recursion
        for t in range(1, len(returns)):
            variance[t] = omega + alpha * (returns[t-1]**2) + beta * variance[t-1]
        
        # Forecast next period variance
        last_variance = variance[-1]
        forecasted_variance = omega + (alpha + beta) * last_variance
        forecasted_variance = max(forecasted_variance, 1e-10)
        
        return float(np.sqrt(forecasted_variance))
        
    except Exception as e:
        # Fallback to simple volatility
        try:
            closes = [candle[4] for candle in ohlcv_data]
            returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
            return np.std(returns[-20:]) if len(returns) >= 20 else 0.01
        except:
            return 0.01

def calculate_automatic_leverage(theta_t):
    """
    AUTOMATICALLY calculate maximum leverage based on forecasted volatility
    Formula: MaxLeverageₜ = 1 + (α × L₀ ÷ θₜ)
    Higher volatility → Lower leverage (AUTOMATIC)
    Lower volatility → Higher leverage (AUTOMATIC)
    """
    # Use FIXED parameters (not user-configurable)
    alpha = LEVERAGE_PARAMS['alpha']
    L0 = LEVERAGE_PARAMS['L0']
    min_vol = LEVERAGE_PARAMS['min_vol']
    max_leverage = LEVERAGE_PARAMS['max_leverage']
    min_leverage = LEVERAGE_PARAMS['min_leverage']
    
    # Ensure theta_t is not too small
    theta_t = max(theta_t, min_vol)
    
    # AUTOMATIC leverage calculation
    # Formula: 1 + (α × L₀ ÷ θₜ)
    raw_leverage = 1 + (alpha * L0 / theta_t)
    
    # Apply safety caps (AUTOMATIC)
    capped_leverage = min(max(min_leverage, raw_leverage), max_leverage)
    
    return capped_leverage

# ====================
# DATA FETCHING & SIGNAL CALCULATION
# ====================
def fetch_market_data():
    if not exchange:
        st.error("Exchange not connected.")
        return None
    
    try:
        coin_name = symbol.split('/')[0]
        order_book = exchange.fetch_order_book(
            symbol, 
            limit=st.session_state.order_book_depth
        )
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=200)
        
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
    
    depth = market_data['depth']
    
    # Core calculations
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid_price = (best_bid + best_ask) / 2
    
    # Calculate volumes based on selected depth
    if depth == 1:
        V_bid = float(bids[0][1])
        V_ask = float(asks[0][1])
    else:
        V_bid = sum(float(bid[1]) for bid in bids[:depth])
        V_ask = sum(float(ask[1]) for ask in asks[:depth])
    
    # Bid-ask spread
    spread = best_ask - best_bid
    relative_spread = spread / mid_price if mid_price > 0 else 0.0001
    
    # Volume imbalance (direction)
    total_volume = V_bid + V_ask
    imbalance = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    
    # AUTOMATIC GARCH forecasted volatility
    theta_t = calculate_garch_volatility(ohlcv)
    
    # AUTOMATIC maximum leverage calculation
    max_leverage = calculate_automatic_leverage(theta_t)
    
    # Trading signal
    if relative_spread > 0 and theta_t > 0:
        raw_signal = imbalance * (abs(imbalance) / (relative_spread * theta_t))
    else:
        raw_signal = 0
    
    # Strength percentage (0-100%)
    raw_strength = abs(raw_signal)
    strength_percentage = min(100.0, np.tanh(raw_strength) * 100)
    
    # Determine direction
    if imbalance > 0:
        direction = "LONG"
        direction_emoji = "📈"
        direction_text = "Buyers Dominating"
    elif imbalance < 0:
        direction = "SHORT"
        direction_emoji = "📉"
        direction_text = "Sellers Dominating"
    else:
        direction = "NEUTRAL"
        direction_emoji = "➖"
        direction_text = "Market Balanced"
    
    # AUTOMATIC leverage recommendation based on strength
    if strength_percentage > 70:
        confidence = "HIGH"
        leverage_multiplier = 0.9  # Use 90% of max leverage
    elif strength_percentage > 40:
        confidence = "MODERATE"
        leverage_multiplier = 0.6  # Use 60% of max leverage
    elif strength_percentage > 15:
        confidence = "LOW"
        leverage_multiplier = 0.3  # Use 30% of max leverage
    else:
        confidence = "VERY LOW"
        leverage_multiplier = 0.1  # Use 10% of max leverage
    
    # Calculate recommended leverage (AUTOMATIC)
    recommended_leverage = max_leverage * leverage_multiplier
    recommended_leverage = round(max(1.0, recommended_leverage), 1)
    
    return {
        # Main display values
        'coin': market_data['coin'],
        'current_price': mid_price,
        'direction': direction,
        'direction_emoji': direction_emoji,
        'direction_text': direction_text,
        'strength_percentage': strength_percentage,
        'confidence': confidence,
        'recommended_leverage': recommended_leverage,
        'max_leverage': max_leverage,
        
        # Market data
        'volatility': theta_t,
        'imbalance': imbalance,
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread': spread,
        'total_bid_volume': V_bid,
        'total_ask_volume': V_ask,
        'depth_analysis': depth,
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

# Display signal if available
if st.session_state.signal_data is not None:
    signal = st.session_state.signal_data
    
    # ========================================
    # MAIN SIGNAL DISPLAY
    # ========================================
    st.markdown("### ⚡ LIVE TRADING SIGNAL")
    
    # Format price display
    current_price = signal.get('current_price', 0)
    price_display = f"{current_price:,.0f}" if current_price > 1000 else f"{current_price:.2f}"
    
    # Direction color
    direction_color = '#00ff00' if signal.get('direction') == 'LONG' else '#ff0000' if signal.get('direction') == 'SHORT' else '#cccccc'
    
    # Main signal display: "COIN PRICE DIRECTION"
    st.markdown(f"""
    <div class='signal-card'>
        <div style='text-align: center;'>
            <div class='price-signal' style='color: {direction_color};'>
                {signal.get('coin', 'N/A')} {price_display} {signal.get('direction', 'NEUTRAL')}
            </div>
            <p style='color: #cccccc; font-size: 1.2rem;'>
                {signal.get('direction_text', 'Analyzing market...')}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ========================================
    # STRENGTH & AUTOMATIC LEVERAGE DISPLAY
    # ========================================
    st.markdown("---")
    
    col_strength, col_leverage = st.columns(2)
    
    with col_strength:
        strength_pct = signal.get('strength_percentage', 0)
        st.markdown(f"**Signal Strength:** <span style='color: #ff0000; font-size: 1.5rem;'>{strength_pct:.1f}%</span>", unsafe_allow_html=True)
        
        # Strength visualization
        strength_color = "#00ff00" if strength_pct > 70 else "#ffaa00" if strength_pct > 40 else "#ff4444"
        
        st.markdown(f"""
        <div style='margin: 15px 0;'>
            <div class='strength-bar-container'>
                <div class='strength-bar-fill' style='width: {strength_pct}%; background: {strength_color};'></div>
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
        
        st.markdown(f"**Confidence:** {signal.get('confidence', 'N/A')}")
    
    with col_leverage:
        st.markdown("##### 🎯 AUTOMATIC LEVERAGE CALCULATION")
        
        # Show current volatility
        volatility = signal.get('volatility', 0)
        volatility_pct = volatility * 100
        
        st.markdown(f"**Current Volatility:** `{volatility_pct:.2f}%`")
        
        # Explain leverage calculation
        if volatility_pct > 3.0:
            st.markdown(f"**⚠️ High Volatility** → Lower leverage recommended")
            st.info(f"Automated Calculation: Higher volatility ({volatility_pct:.2f}%) = Safer leverage")
        elif volatility_pct < 1.0:
            st.markdown(f"**✅ Low Volatility** → Higher leverage possible")
            st.info(f"Automated Calculation: Lower volatility ({volatility_pct:.2f}%) = More aggressive leverage")
        else:
            st.markdown(f"**⚖️ Moderate Volatility** → Standard leverage")
            st.info(f"Automated Calculation: Moderate volatility ({volatility_pct:.2f}%) = Balanced leverage")
        
        # Show leverage results
        st.markdown(f"**Maximum Allowed:** `{signal.get('max_leverage', 0):.1f}x`")
        st.markdown(f"**Recommended Leverage:** `{signal.get('recommended_leverage', 0):.1f}x`")
    
    # ========================================
    # MARKET DATA
    # ========================================
    st.markdown("---")
    st.markdown("#### 📊 MARKET DATA")
    
    market_col1, market_col2, market_col3 = st.columns(3)
    
    with market_col1:
        st.metric("Best Bid", f"{signal.get('best_bid', 0):,.2f}")
        st.metric("Best Ask", f"{signal.get('best_ask', 0):,.2f}")
    
    with market_col2:
        st.metric("Spread", f"{signal.get('spread', 0):.4f}")
        st.metric("Volume Imbalance", f"{signal.get('imbalance', 0):.4f}")
    
    with market_col3:
        st.metric("Order Book Depth", f"{signal.get('depth_analysis', 0)} levels")
        st.metric("Bid/Ask Volume", f"{signal.get('total_bid_volume', 0):.1f} / {signal.get('total_ask_volume', 0):.1f}")

# ====================
# FOOTER & BRANDING
# ====================
st.markdown("---")

footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.markdown("""
    <div style='text-align: center; padding: 20px; border-top: 2px solid #ff0000;'>
        <h3 style='color: #ff0000;'>GODZILLERS TRADING SIGNALS</h3>
        <p style='color: #cccccc;'>Fully Automatic Leverage Calculation</p>
        <p style='color: #666666; font-size: 0.9em;'>
            ⚡ Leverage automatically adjusts to market volatility<br>
            📈 Higher volatility = Lower leverage (safer)<br>
            📉 Lower volatility = Higher leverage (aggressive)<br>
            🔄 Manual refresh only • Trade responsibly
        </p>
        <p style='color: #ff0000; font-weight: bold; font-size: 1.2em;'>MADE BY GODZILLERS TEAM</p>
    </div>
    """, unsafe_allow_html=True)