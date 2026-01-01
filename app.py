import ccxt
import pandas as pd
import numpy as np
import streamlit as st
import time
from datetime import datetime

# ====================
# PAGE CONFIGURATION
# ====================
st.set_page_config(
    page_title="BTC Futures Signal Bot",
    page_icon="📈",
    layout="wide"
)

st.title("📈 BTC Futures Trading Signal Bot")
st.markdown("""
**Real-time signal calculator for BTC/USDT futures**
- **Signal Formula**: `sign(I) × (|I| ÷ (φ × σ))`
- **Strength**: `min(100, |Signal| × 100)`
""")

# ====================
# SIDEBAR CONFIGURATION
# ====================
st.sidebar.header("⚙️ Configuration")

# Marketplace selection (CRITICAL FIX for 451 error)
marketplace = st.sidebar.radio(
    "Select Marketplace",
    ["Binance International", "Binance US"],
    index=0,
    help="Choose based on your location. Binance US for United States users."
)

symbol = st.sidebar.selectbox(
    "Trading Pair",
    ["BTC/USDT", "ETH/USDT"],
    index=0
)

refresh_rate = st.sidebar.slider(
    "Update Frequency (seconds)",
    min_value=5,
    max_value=60,
    value=10
)

# ====================
# EXCHANGE CONNECTION
# ====================
@st.cache_resource
def init_exchange(marketplace_choice):
    """Initialize exchange with proper configuration"""
    
    config = {
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',  # USDⓈ-M Futures
        }
    }
    
    # Select correct exchange ID based on marketplace
    if marketplace_choice == "Binance US":
        exchange_id = 'binanceus'
        st.sidebar.info("Using Binance.US Futures API")
    else:
        exchange_id = 'binance'
        st.sidebar.info("Using Binance International Futures API")
    
    try:
        # Dynamically create exchange instance
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class(config)
        
        # Test connection
        exchange.fetch_time()
        st.sidebar.success("✅ API Connected")
        return exchange
        
    except Exception as e:
        st.sidebar.error(f"❌ Connection failed: {str(e)[:100]}")
        return None

# Initialize exchange
exchange = init_exchange(marketplace)

# ====================
# DATA FUNCTIONS
# ====================
@st.cache_data(ttl=30)
def fetch_order_book_data(_exchange, symbol, retries=3):
    """Fetch order book with retry logic"""
    if not _exchange:
        return None
    
    for attempt in range(retries):
        try:
            # Fetch top 10 levels of order book
            order_book = _exchange.fetch_order_book(symbol, limit=10)
            
            if order_book and 'bids' in order_book and 'asks' in order_book:
                if len(order_book['bids']) > 0 and len(order_book['asks']) > 0:
                    return order_book
            
            time.sleep(1)  # Brief pause before retry
            
        except ccxt.NetworkError:
            if attempt < retries - 1:
                time.sleep(2)
                continue
        except Exception:
            break
    
    return None

@st.cache_data(ttl=60)
def fetch_historical_data(_exchange, symbol):
    """Fetch OHLCV data for volatility calculation"""
    if not _exchange:
        return pd.DataFrame()
    
    try:
        # Fetch 50 candles of 5-minute data
        ohlcv = _exchange.fetch_ohlcv(symbol, '5m', limit=50)
        
        if ohlcv and len(ohlcv) > 20:
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
    except Exception:
        pass
    
    return pd.DataFrame()

# ====================
# CALCULATION FUNCTIONS
# ====================
def calculate_metrics(order_book):
    """Calculate all metrics from the order book"""
    if not order_book:
        return None
    
    bids = order_book['bids']
    asks = order_book['asks']
    
    if not bids or not asks:
        return None
    
    # Best bid/ask prices
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    
    # Mid price (P)
    P = (best_bid + best_ask) / 2
    
    # Volume sums (top 10 levels)
    V_bid = sum(float(bid[1]) for bid in bids[:10])
    V_ask = sum(float(ask[1]) for ask in asks[:10])
    
    # Volume imbalance (I)
    total_volume = V_bid + V_ask
    I = (V_bid - V_ask) / total_volume if total_volume > 0 else 0
    
    # Spread calculations
    S = best_ask - best_bid  # Absolute spread
    phi = S / P if P > 0 else 0.0001  # Relative spread
    
    return {
        'best_bid': best_bid,
        'best_ask': best_ask,
        'P': P,
        'V_bid': V_bid,
        'V_ask': V_ask,
        'I': I,
        'S': S,
        'phi': phi
    }

def calculate_volatility(df):
    """Calculate 20-period volatility of log returns"""
    if len(df) < 20:
        return 0.005  # Default reasonable volatility
    
    try:
        # Calculate log returns
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        
        # 20-period rolling standard deviation
        sigma = df['log_return'].rolling(window=20).std().iloc[-1]
        
        # Ensure reasonable bounds
        return max(min(float(sigma), 0.05), 0.001) if not np.isnan(sigma) else 0.005
        
    except Exception:
        return 0.005

def compute_signal(I, phi, sigma):
    """Compute final trading signal and strength"""
    if phi <= 0 or sigma <= 0:
        return 0.0, 0.0
    
    try:
        # Core signal formula
        Signal = np.sign(I) * (abs(I) / (phi * sigma))
        Strength = min(100.0, abs(Signal) * 100)
        
        return float(Signal), float(Strength)
        
    except Exception:
        return 0.0, 0.0

# ====================
# DISPLAY FUNCTIONS
# ====================
def display_price_metrics(metrics):
    """Display price-related metrics"""
    if not metrics:
        st.warning("Waiting for market data...")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Best Bid", f"{metrics['best_bid']:,.2f}")
    with col2:
        st.metric("Best Ask", f"{metrics['best_ask']:,.2f}")
    with col3:
        st.metric("Mid Price (P)", f"{metrics['P']:,.2f}")
    with col4:
        st.metric("Spread (S)", f"{metrics['S']:.4f}")

def display_volume_metrics(metrics):
    """Display volume-related metrics"""
    if not metrics:
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Bid Volume", f"{metrics['V_bid']:.3f}")
    with col2:
        st.metric("Ask Volume", f"{metrics['V_ask']:.3f}")
    with col3:
        imbalance_color = "green" if metrics['I'] > 0 else "red" if metrics['I'] < 0 else "gray"
        st.markdown(
            f"**Volume Imbalance (I):** "
            f"<span style='color:{imbalance_color}'>{metrics['I']:.4f}</span>",
            unsafe_allow_html=True
        )

def display_signal(signal, strength, phi, sigma):
    """Display the trading signal"""
    st.markdown("---")
    
    # Signal strength bar
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Determine signal color and direction
        if signal > 0.1:
            signal_text = "🟢 STRONG BUY"
            color = "green"
        elif signal > 0:
            signal_text = "🟡 WEAK BUY"
            color = "orange"
        elif signal < -0.1:
            signal_text = "🔴 STRONG SELL"
            color = "red"
        elif signal < 0:
            signal_text = "🟠 WEAK SELL"
            color = "darkorange"
        else:
            signal_text = "⚪ NEUTRAL"
            color = "gray"
        
        st.markdown(
            f"### 📡 **Signal:** "
            f"<span style='color:{color}; font-size: 1.5em;'>{signal_text}</span>",
            unsafe_allow_html=True
        )
        
        # Numerical values
        st.markdown(f"**Signal Value:** `{signal:.4f}`")
        st.markdown(f"**Relative Spread (φ):** `{phi:.6f}` | **Volatility (σ):** `{sigma:.6f}`")
    
    with col2:
        # Strength gauge
        st.metric("💪 **Signal Strength**", f"{strength:.1f}%")
        
        # Visual progress bar
        progress_color = "green" if strength > 70 else "orange" if strength > 30 else "red"
        
        # Custom colored progress bar
        st.markdown(
            f"""
            <div style="background: #ddd; border-radius: 10px; height: 20px; margin: 10px 0;">
                <div style="background: {progress_color}; 
                          width: {strength}%; 
                          height: 100%; 
                          border-radius: 10px;">
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Strength interpretation
        if strength > 70:
            st.caption("High confidence signal")
        elif strength > 30:
            st.caption("Moderate confidence")
        else:
            st.caption("Low confidence")

# ====================
# MAIN APPLICATION LOOP
# ====================
def main():
    """Main application loop"""
    
    # Status indicator
    status_placeholder = st.empty()
    
    # Create containers for organized display
    price_container = st.container()
    volume_container = st.container()
    signal_container = st.container()
    
    # Initialize error counter
    error_count = 0
    
    while True:
        try:
            # Update status
            current_time = datetime.now().strftime("%H:%M:%S")
            status_placeholder.caption(f"🟢 Live | Last update: {current_time} | Pair: {symbol}")
            
            # Check exchange connection
            if not exchange:
                status_placeholder.error("❌ Exchange not connected. Check marketplace selection.")
                time.sleep(refresh_rate)
                continue
            
            # Fetch data
            order_book = fetch_order_book_data(exchange, symbol)
            df_historical = fetch_historical_data(exchange, symbol)
            
            if not order_book:
                error_count += 1
                if error_count > 3:
                    status_placeholder.warning("⚠️ Unable to fetch data. Retrying...")
                time.sleep(refresh_rate)
                continue
            
            # Reset error counter on success
            error_count = 0
            
            # Calculate metrics
            metrics = calculate_metrics(order_book)
            
            if not metrics:
                time.sleep(refresh_rate)
                continue
            
            # Calculate volatility
            sigma = calculate_volatility(df_historical)
            
            # Calculate signal
            signal, strength = compute_signal(
                metrics['I'], 
                metrics['phi'], 
                sigma
            )
            
            # Update displays
            with price_container:
                display_price_metrics(metrics)
            
            with volume_container:
                display_volume_metrics(metrics)
            
            with signal_container:
                display_signal(signal, strength, metrics['phi'], sigma)
            
            # Brief pause before next update
            time.sleep(refresh_rate)
            
        except KeyboardInterrupt:
            st.info("Application stopped by user")
            break
        except Exception as e:
            error_count += 1
            if error_count <= 3:
                status_placeholder.error(f"Error: {str(e)[:100]}...")
            time.sleep(refresh_rate)

# ====================
# APPLICATION START
# ====================
if __name__ == "__main__":
    # Add a restart button in sidebar
    if st.sidebar.button("🔄 Restart Application"):
        st.rerun()
    
    # Information panel
    with st.sidebar.expander("ℹ️ How it works"):
        st.markdown("""
        **Formula Components:**
        1. **I (Volume Imbalance)**: `(V_bid - V_ask) / (V_bid + V_ask)`
        2. **φ (Relative Spread)**: `(Ask - Bid) / Mid_Price`
        3. **σ (Volatility)**: Std. dev. of 20-period log returns
        
        **Marketplace Note:**
        - Use **Binance International** if accessible in your region
        - Use **Binance US** if you're in the United States
        """)
    
    # Start the main loop
    main()