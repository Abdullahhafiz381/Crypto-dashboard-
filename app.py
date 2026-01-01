import ccxt
import pandas as pd
import numpy as np
import streamlit as st
import time
from datetime import datetime

# Title and configuration
st.set_page_config(
    page_title="BTC Futures Signal Bot",
    page_icon="📈",
    layout="wide"
)

st.title("📈 BTC Futures Trading Signal Bot")
st.markdown("""
Real-time signal calculator for BTC/USDT futures on Binance.
Signal updates every 10 seconds.
""")

# Sidebar settings
st.sidebar.header("Configuration")
refresh_rate = st.sidebar.slider("Update frequency (seconds)", 5, 30, 10)
symbol = st.sidebar.selectbox("Trading Pair", ["BTC/USDT", "ETH/USDT"], index=0)

# Initialize exchange connection
@st.cache_resource
def get_exchange():
    return ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

exchange = get_exchange()

# Price history for volatility calculation
@st.cache_data(ttl=60)
def get_ohlcv_data(_exchange, symbol=symbol):
    """Get historical data for volatility calculation"""
    try:
        ohlcv = _exchange.fetch_ohlcv(symbol, '5m', limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# Calculate volatility (σ)
def calculate_volatility(df):
    if len(df) < 20:
        return 0.001  # Default small value if not enough data
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    sigma = df['log_return'].rolling(window=20).std().iloc[-1]
    return max(sigma, 0.001)  # Avoid division by zero

# Create containers for live updates
price_container = st.container()
metrics_container = st.container()
signal_container = st.container()

# Main loop
while True:
    try:
        # Fetch current data
        order_book = exchange.fetch_order_book(symbol, 10)
        df_historical = get_ohlcv_data(exchange)
        
        # Extract bids and asks
        bids = order_book['bids']
        asks = order_book['asks']
        
        if not bids or not asks:
            st.warning("No data received, retrying...")
            time.sleep(refresh_rate)
            continue
        
        # Calculate metrics from your formula
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        
        P = (best_bid + best_ask) / 2  # Mid price
        V_bid = sum(bid[1] for bid in bids[:10])
        V_ask = sum(ask[1] for ask in asks[:10])
        
        I = (V_bid - V_ask) / (V_bid + V_ask) if (V_bid + V_ask) > 0 else 0
        S = best_ask - best_bid
        phi = S / P if P > 0 else 0.0001
        
        # Calculate volatility
        sigma = calculate_volatility(df_historical)
        
        # Calculate signal and strength
        if phi > 0 and sigma > 0:
            Signal = np.sign(I) * (abs(I) / (phi * sigma))
            Strength = min(100, abs(Signal) * 100)
        else:
            Signal = 0
            Strength = 0
        
        # Update display
        with price_container:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Best Bid", f"{best_bid:,.2f}")
            with col2:
                st.metric("Best Ask", f"{best_ask:,.2f}")
            with col3:
                st.metric("Mid Price (P)", f"{P:,.2f}")
        
        with metrics_container:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Bid Volume", f"{V_bid:.2f}")
            with col2:
                st.metric("Ask Volume", f"{V_ask:.2f}")
            with col3:
                st.metric("Spread (S)", f"{S:.2f}")
            with col4:
                st.metric("Volatility (σ)", f"{sigma:.6f}")
        
        with signal_container:
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            # Signal with color coding
            signal_color = "green" if Signal > 0 else "red" if Signal < 0 else "gray"
            with col1:
                st.markdown(f"### 📡 **Signal:** <span style='color:{signal_color};'>{Signal:.4f}</span>", 
                           unsafe_allow_html=True)
                st.caption("Positive = Buy | Negative = Sell")
            
            # Strength with progress bar
            with col2:
                st.metric("💪 **Strength %**", f"{Strength:.1f}%")
                st.progress(int(Strength))
            
            # Imbalance indicator
            st.info(f"**Volume Imbalance (I):** {I:.4f} | **Relative Spread (φ):** {phi:.6f}")
            
        # Timestamp
        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
        
    except Exception as e:
        st.error(f"Error: {str(e)[:100]}...")
    
    # Wait for next update
    time.sleep(refresh_rate)