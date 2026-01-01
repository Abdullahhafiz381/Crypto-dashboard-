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
    st.markdown("<h3 style='text-align: center; color: #cccccc;'>Advanced GARCH Volatility Forecasting</h3>", unsafe_allow_html=True)

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

if 'leverage_params' not in st.session_state:
    st.session_state.leverage_params = {
        'alpha': 50.0,  # Leverage scaling factor
        'L0': 5.0,      # Base leverage
        'min_vol': 0.001,  # Minimum volatility (prevent division by zero)
        'max_leverage': 100.0  # Safety cap
    }

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

# Leverage Parameters Configuration
with st.expander("⚙️ Dynamic Leverage Parameters"):
    params_col1, params_col2 = st.columns(2)
    
    with params_col1:
        st.session_state.leverage_params['alpha'] = st.slider(
            "Alpha (α) - Leverage Sensitivity",
            min_value=1.0,
            max_value=200.0,
            value=st.session_state.leverage_params['alpha'],
            step=1.0,
            help="Higher alpha = more aggressive leverage scaling"
        )
    
    with params_col2:
        st.session_state.leverage_params['L0'] = st.slider(
            "Base Leverage (L₀)",
            min_value=1.0,
            max_value=20.0,
            value=st.session_state.leverage_params['L0'],
            step=0.5,
            help="Minimum leverage when volatility is very high"
        )
    
    st.caption("Dynamic Leverage Formula: MaxLeverage = 1 + (α × L₀ ÷ θₜ)")
    st.caption("θₜ = GARCH forecasted volatility | Higher volatility → Lower leverage")

st.markdown("---")

# ====================
# ADVANCED FUNCTIONS
# ====================
def calculate_garch_volatility(ohlcv_data, forecast_periods=1):
    """
    Calculate GARCH(1,1) forecasted volatility (θₜ²)
    Engle-style variance forecasting
    """
    try:
        if len(ohlcv_data) < 100:
            # Fallback: Use simple rolling volatility if insufficient data
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
        
        if len(returns) < 100:
            return np.std(returns)
        
        # Implement GARCH(1,1) manually
        # θₜ² = ω + α₁ * rₜ₋₁² + β₁ * θₜ₋₁²
        
        # Initialize parameters (simplified estimation)
        omega = 0.000001  # Long-run variance
        alpha = 0.1       # ARCH parameter (news impact)
        beta = 0.85       # GARCH parameter (persistence)
        
        # Initialize variance array
        variance = np.zeros(len(returns))
        variance[0] = np.var(returns[:50])  # Initial variance
        
        # GARCH(1,1) recursion
        for t in range(1, len(returns)):
            variance[t] = omega + alpha * (returns[t-1]**2) + beta * variance[t-1]
        
        # Forecast next period variance (θₜ²)
        last_variance = variance[-1]
        forecasted_variance = omega + (alpha + beta) * last_variance
        
        # Ensure variance is positive
        forecasted_variance = max(forecasted_variance, 1e-10)
        
        # Return forecasted volatility (θₜ = sqrt(θₜ²))
        forecasted_volatility = np.sqrt(forecasted_variance)
        
        return float(forecasted_volatility)
        
    except Exception as e:
        # Fallback to simple volatility
        try:
            closes = [candle[4] for candle in ohlcv_data]
            returns = np.log(np.array(closes[1:]) / np.array(closes[:-1]))
            return np.std(returns[-20:]) if len(returns) >= 20 else 0.01
        except:
            return 0.01

def calculate_dynamic_leverage(theta_t, params):
    """
    Calculate maximum leverage based on forecasted volatility
    Formula: MaxLeverageₜ = 1 + (α × L₀ ÷ θₜ)
    Higher volatility → Lower allowed leverage
    """
    alpha = params['alpha']
    L0 = params['L0']
    min_vol = params['min_vol']
    max_leverage = params['max_leverage']
    
    # Ensure theta_t is not too small (avoid division by zero)
    theta_t = max(theta_t, min_vol)
    
    # Calculate leverage: 1 + (α * L₀ / θₜ)
    raw_leverage = 1 + (alpha * L0 / theta_t)
    
    # Apply safety caps
    capped_leverage = min(max(1.0, raw_leverage), max_leverage)
    
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
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=500)  # More data for GARCH
        
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
    
    # ========================================
    # CORE FORMULA CALCULATIONS
    # ========================================
    
    # 1. Current mid-price: Pₜ = (best_bid + best_ask) / 2
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    P_t = (best_bid + best_ask) / 2
    
    # 2. Volumes: V_bid and V_ask (top few levels)
    if depth == 1:
        V_bid = float(bids[0][1])
        V_ask = float(asks[0][1])
    else:
        V_bid = sum(float(bid[1]) for bid in bids[:depth])
        V_ask = sum(float(ask[1]) for ask in asks[:depth])
    
    # 3. Bid-ask spread: Sₜ = Askₜ - Bidₜ
    S_t = best_ask - best_bid
    
    # 4. Relative spread (friction cost): φₜ = Sₜ / Pₜ
    phi_t = S_t / P_t if P_t > 0 else 0.0001
    
    # 5. Volume imbalance (direction): Iₜ = (V_bid - V_ask) / (V_bid + V_ask)
    total_volume = V_bid + V_ask
    I_t = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    
    # 6. GARCH forecasted volatility: θₜ = sqrt(θₜ²)
    theta_t = calculate_garch_volatility(ohlcv)
    
    # 7. Dynamic maximum leverage: MaxLeverageₜ = 1 + (α × L₀ ÷ θₜ)
    max_leverage = calculate_dynamic_leverage(theta_t, st.session_state.leverage_params)
    
    # 8. Trading signal calculation
    if phi_t > 0 and theta_t > 0:
        # Enhanced signal formula with GARCH volatility
        raw_signal = I_t * (abs(I_t) / (phi_t * theta_t))
    else:
        raw_signal = 0
    
    # 9. Strength percentage (0-100%)
    raw_strength = abs(raw_signal)
    strength_percentage = min(100.0, np.tanh(raw_strength) * 100)
    
    # 10. Determine direction based on Iₜ
    if I_t > 0:
        direction = "LONG"
        direction_emoji = "📈"
        direction_explanation = "Buyers heavier (up-pressure)"
    elif I_t < 0:
        direction = "SHORT"
        direction_emoji = "📉"
        direction_explanation = "Sellers heavier (down-pressure)"
    else:
        direction = "NEUTRAL"
        direction_emoji = "➖"
        direction_explanation = "Market balanced"
    
    # 11. Determine confidence based on strength
    if strength_percentage > 70:
        confidence = "HIGH"
        leverage_recommendation = f"Use {max_leverage:.1f}x (Max)"
    elif strength_percentage > 40:
        confidence = "MODERATE"
        leverage_recommendation = f"Use {min(max_leverage * 0.7, max_leverage):.1f}x"
    elif strength_percentage > 15:
        confidence = "LOW"
        leverage_recommendation = f"Use {min(max_leverage * 0.3, max_leverage):.1f}x"
    else:
        confidence = "VERY LOW"
        leverage_recommendation = "No leverage recommended"
    
    return {
        'coin': market_data['coin'],
        'exchange': 'OKX',
        
        # Core Formula Values
        'P_t': P_t,                    # Current mid-price
        'S_t': S_t,                    # Bid-ask spread
        'phi_t': phi_t,                # Relative spread
        'I_t': I_t,                    # Volume imbalance (direction)
        'theta_t': theta_t,            # GARCH forecasted volatility
        'max_leverage_raw': max_leverage,  # Calculated max leverage
        
        # Derived Values
        'direction': direction,
        'direction_emoji': direction_emoji,
        'direction_explanation': direction_explanation,
        'strength_percentage': strength_percentage,
        'confidence': confidence,
        'leverage_recommendation': leverage_recommendation,
        
        # Market Data
        'best_bid': best_bid,
        'best_ask': best_ask,
        'total_bid_volume': V_bid,
        'total_ask_volume': V_ask,
        'volume_ratio': V_bid / V_ask if V_ask > 0 else 1,
        'depth_analysis': depth,
        'raw_signal': raw_signal,
        'timestamp': market_data['timestamp']
    }

# ====================
# MAIN DISPLAY
# ====================
if refresh_clicked or st.session_state.signal_data is None:
    with st.spinner("🔥 Running GARCH Volatility Forecasting..."):
        market_data = fetch_market_data()
        if market_data:
            signal_data = calculate_advanced_signal(market_data)
            st.session_state.signal_data = signal_data
            st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
            st.rerun()

if st.session_state.signal_data:
    signal = st.session_state.signal_data
    
    # ========================================
    # MAIN SIGNAL DISPLAY
    # ========================================
    st.markdown("### ⚡ ADVANCED TRADING SIGNAL")
    
    # Format price display
    current_price = signal['P_t']
    price_display = f"{current_price:,.0f}" if current_price > 1000 else f"{current_price:.2f}"
    
    # Direction color
    direction_color = '#00ff00' if signal['direction'] == 'LONG' else '#ff0000' if signal['direction'] == 'SHORT' else '#cccccc'
    
    # Main signal display: "COIN PRICE DIRECTION"
    st.markdown(f"""
    <div class='signal-card'>
        <div style='text-align: center;'>
            <div class='price-signal' style='color: {direction_color};'>
                {signal['coin']} {price_display} {signal['direction']}
            </div>
            <p style='color: #cccccc; font-size: 1.2rem;'>
                {signal['direction_explanation']}
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ========================================
    # FORMULA VALUES DISPLAY
    # ========================================
    st.markdown("#### 📐 FORMULA VALUES")
    formula_col1, formula_col2, formula_col3, formula_col4 = st.columns(4)
    
    with formula_col1:
        st.metric("Pₜ (Mid-Price)", f"{signal['P_t']:,.2f}")
        st.metric("Sₜ (Spread)", f"{signal['S_t']:.4f}")
    
    with formula_col2:
        st.metric("φₜ (Rel. Spread)", f"{signal['phi_t']:.6f}")
        st.metric("Iₜ (Imbalance)", f"{signal['I_t']:.4f}")
    
    with formula_col3:
        st.metric("θₜ (GARCH Vol)", f"{signal['theta_t']:.6f}")
        st.metric("Volatility σ", f"{signal['theta_t']*100:.2f}%")
    
    with formula_col4:
        st.metric("Max Leverage", f"{signal['max_leverage_raw']:.1f}x")
        st.metric("Direction", signal['direction_emoji'])
    
    # ========================================
    # STRENGTH & LEVERAGE DISPLAY
    # ========================================
    st.markdown("---")
    st.markdown("#### 💪 SIGNAL STRENGTH & LEVERAGE")
    
    col_strength, col_leverage = st.columns(2)
    
    with col_strength:
        st.markdown(f"**Signal Strength:** <span style='color: #ff0000; font-size: 1.5rem;'>{signal['strength_percentage']:.1f}%</span>", unsafe_allow_html=True)
        
        # Strength visualization
        strength_color = "#00ff00" if signal['strength_percentage'] > 70 else "#ffaa00" if signal['strength_percentage'] > 40 else "#ff4444"
        
        st.markdown(f"""
        <div style='margin: 15px 0;'>
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
        
        st.markdown(f"**Confidence Level:** {signal['confidence']}")
    
    with col_leverage:
        st.markdown("##### 🎯 DYNAMIC LEVERAGE CALCULATION")
        st.markdown(f"**Formula:** `MaxLeverageₜ = 1 + (α × L₀ ÷ θₜ)`")
        st.markdown(f"**Calculation:** `1 + ({st.session_state.leverage_params['alpha']} × {st.session_state.leverage_params['L0']} ÷ {signal['theta_t']:.6f})`")
        st.markdown(f"**Result:** `{signal['max_leverage_raw']:.1f}x`")
        st.markdown(f"**Recommendation:** `{signal['leverage_recommendation']}`")
        
        # Volatility-Leverage Relationship
        if signal['theta_t'] > 0.02:
            st.warning("⚠️ High volatility detected - Lower leverage recommended")
        elif signal['theta_t'] < 0.005:
            st.success("✅ Low volatility - Higher leverage possible")
    
    # ========================================
    # MARKET DATA & ORDER BOOK
    # ========================================
    st.markdown("---")
    st.markdown("#### 📊 MARKET DATA")
    
    market_col1, market_col2, market_col3 = st.columns(3)
    
    with market_col1:
        st.markdown(f"**Order Book Depth:** {signal['depth_analysis']} levels")
        st.markdown(f"**Best Bid:** `{signal['best_bid']:,.2f}`")
        st.markdown(f"**Best Ask:** `{signal['best_ask']:,.2f}`")
    
    with market_col2:
        st.markdown(f"**Bid Volume:** `{signal['total_bid_volume']:.2f}`")
        st.markdown(f"**Ask Volume:** `{signal['total_ask_volume']:.2f}`")
        st.markdown(f"**Volume Ratio:** `{signal['volume_ratio']:.2f}`")
    
    with market_col3:
        st.markdown(f"**Analysis Time:** {st.session_state.last_refresh}")
        st.markdown(f"**Exchange:** {signal['exchange']}")
        st.markdown(f"**Raw Signal:** `{signal['raw_signal']:.4f}`")
    
    # ========================================
    # FOOTER & BRANDING
# ====================
st.markdown("---")

footer_col1, footer_col2, footer_col3 = st.columns([1, 2, 1])

with footer_col2:
    st.markdown("""
    <div style='text-align: center; padding: 20px; border-top: 2px solid #ff0000;'>
        <h3 style='color: #ff0000;'>GODZILLERS ADVANCED TRADING SYSTEM</h3>
        <p style='color: #cccccc;'>GARCH Volatility Forecasting • Dynamic Leverage</p>
        <p style='color: #666666; font-size: 0.9em;'>
            Features: Engle-GARCH volatility • Dynamic leverage scaling • Order book analysis<br>
            Manual refresh only • Trade with proper risk management
        </p>
        <p style='color: #ff0000; font-weight: bold; font-size: 1.2em;'>MADE BY GODZILLERS TEAM</p>
    </div>
    """, unsafe_allow_html=True)