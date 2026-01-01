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
    page_title="Multi-Exchange Futures Signal Bot",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Multi-Exchange Futures Signal Bot")
st.markdown("""
**Real-time signal calculator supporting multiple exchanges**
- **Formula**: `Signal = sign(I) × (|I| ÷ (φ × σ))`
- **Exchanges**: Bybit, OKX, Binance, Binance US
- **Updates**: Every 10 seconds
""")

# ====================
# SIDEBAR CONFIGURATION
# ====================
st.sidebar.header("⚙️ Configuration")

# Exchange selection with detailed descriptions
exchange_info = {
    "Bybit": {
        "code": "bybit",
        "description": "Good liquidity, popular for derivatives",
        "future_type": "linear"  # USDT-M futures
    },
    "OKX": {
        "code": "okx", 
        "description": "Large exchange, good API reliability",
        "future_type": "future"
    },
    "Binance International": {
        "code": "binance",
        "description": "Global (if accessible in your region)",
        "future_type": "future"
    },
    "Binance US": {
        "code": "binanceus",
        "description": "For users in the United States",
        "future_type": "future"
    }
}

selected_exchange_name = st.sidebar.selectbox(
    "Select Exchange",
    list(exchange_info.keys()),
    index=0,  # Default to Bybit
    help="Choose based on API accessibility in your region"
)

# Show exchange description
selected_info = exchange_info[selected_exchange_name]
st.sidebar.info(f"**{selected_exchange_name}**: {selected_info['description']}")

# Trading pair configuration
symbol_mapping = {
    "Bybit": ["BTC/USDT:USDT", "ETH/USDT:USDT"],  # Bybit format for linear futures
    "OKX": ["BTC/USDT:USDT", "ETH/USDT:USDT"],    # OKX format
    "Binance International": ["BTC/USDT", "ETH/USDT"],
    "Binance US": ["BTC/USDT", "ETH/USDT"]
}

symbol = st.sidebar.selectbox(
    "Trading Pair",
    symbol_mapping[selected_exchange_name],
    index=0
)

# Update frequency
refresh_rate = st.sidebar.slider(
    "Update Frequency (seconds)",
    min_value=5,
    max_value=30,
    value=10
)

# ====================
# EXCHANGE CONNECTION
# ====================
@st.cache_resource
def init_exchange(exchange_name):
    """Initialize exchange with proper configuration"""
    
    exchange_data = exchange_info[exchange_name]
    exchange_code = exchange_data["code"]
    future_type = exchange_data["future_type"]
    
    # Common configuration
    config = {
        'enableRateLimit': True,
        'options': {
            'defaultType': future_type,
        }
    }
    
    # Exchange-specific adjustments
    exchange_configs = {
        "bybit": {
            **config,
            'options': {**config['options'], 'adjustForTimeDifference': True}
        },
        "okx": {
            **config,
            'options': {**config['options'], 'defaultType': 'SWAP'}  # OKX uses SWAP for perpetual
        },
        "binance": config,
        "binanceus": config
    }
    
    try:
        # Get exchange class from ccxt
        exchange_class = getattr(ccxt, exchange_code)
        
        # Create instance with appropriate config
        exchange_config = exchange_configs.get(exchange_code, config)
        exchange = exchange_class(exchange_config)
        
        # Test connection
        exchange.fetch_time()
        
        # Store exchange info in session for display
        st.session_state['current_exchange'] = exchange_name
        st.session_state['exchange_connected'] = True
        
        return exchange
        
    except Exception as e:
        error_msg = str(e)
        if "451" in error_msg or "unavailable" in error_msg.lower():
            st.sidebar.error(f"❌ {exchange_name} API blocked in this region. Try another exchange.")
        else:
            st.sidebar.error(f"❌ Connection failed: {error_msg[:100]}")
        return None

# Initialize exchange
exchange = init_exchange(selected_exchange_name)

# Connection status
status_container = st.sidebar.container()
with status_container:
    if exchange:
        st.success(f"✅ Connected to {selected_exchange_name}")
    else:
        st.error(f"❌ Not connected to {selected_exchange_name}")

# ====================
# DATA FETCHING FUNCTIONS
# ====================
def normalize_symbol(_exchange, symbol_input):
    """Ensure symbol format matches exchange requirements"""
    if selected_exchange_name == "Bybit":
        # Bybit uses BTC/USDT:USDT format for linear futures
        if "USDT" in symbol_input and ":USDT" not in symbol_input:
            return f"{symbol_input.split('/')[0]}/USDT:USDT"
    return symbol_input

@st.cache_data(ttl=15)
def fetch_order_book(_exchange, _symbol, retries=2):
    """Fetch order book with retry logic"""
    if not _exchange:
        return None
    
    normalized_symbol = normalize_symbol(_exchange, _symbol)
    
    for attempt in range(retries):
        try:
            # Fetch order book
            order_book = _exchange.fetch_order_book(normalized_symbol, limit=10)
            
            # Validate response
            if (order_book and 'bids' in order_book and 'asks' in order_book and
                len(order_book['bids']) > 0 and len(order_book['asks']) > 0):
                return order_book
            
            time.sleep(0.5)  # Brief pause
            
        except ccxt.BadSymbol:
            # Try with alternative symbol format
            alt_symbol = _symbol.replace(":USDT", "") if ":USDT" in _symbol else f"{_symbol}:USDT"
            try:
                order_book = _exchange.fetch_order_book(alt_symbol, limit=10)
                if order_book and 'bids' in order_book and 'asks' in order_book:
                    return order_book
            except:
                pass
            
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            else:
                st.warning(f"Order book fetch failed: {str(e)[:100]}")
    
    return None

@st.cache_data(ttl=60)
def fetch_historical_data(_exchange, _symbol):
    """Fetch OHLCV data for volatility calculation"""
    if not _exchange:
        return pd.DataFrame()
    
    normalized_symbol = normalize_symbol(_exchange, _symbol)
    
    try:
        # Different exchanges might prefer different timeframes
        timeframe = '5m'
        
        # Fetch data (more candles for better volatility calculation)
        ohlcv = _exchange.fetch_ohlcv(normalized_symbol, timeframe, limit=100)
        
        if ohlcv and len(ohlcv) > 20:
            df = pd.DataFrame(
                ohlcv, 
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
    except Exception as e:
        # Try with basic symbol format
        try:
            base_symbol = _symbol.split(':')[0] if ':' in _symbol else _symbol
            ohlcv = _exchange.fetch_ohlcv(base_symbol, '5m', limit=100)
            if ohlcv:
                df = pd.DataFrame(
                    ohlcv, 
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                return df
        except:
            pass
    
    return pd.DataFrame()

# ====================
# CALCULATION FUNCTIONS
# ====================
def calculate_metrics(order_book):
    """Calculate all metrics from order book data"""
    if not order_book:
        return None
    
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])
    
    if not bids or not asks:
        return None
    
    try:
        # Extract prices and volumes
        best_bid = float(bids[0][0]) if len(bids) > 0 else 0
        best_ask = float(asks[0][0]) if len(asks) > 0 else 0
        
        if best_bid <= 0 or best_ask <= 0:
            return None
        
        # Mid price (P)
        P = (best_bid + best_ask) / 2
        
        # Volume sums (top 10 levels)
        V_bid = sum(float(bid[1]) for bid in bids[:10]) if len(bids) >= 10 else sum(float(bid[1]) for bid in bids)
        V_ask = sum(float(ask[1]) for ask in asks[:10]) if len(asks) >= 10 else sum(float(ask[1]) for ask in asks)
        
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
        
    except Exception as e:
        st.warning(f"Metrics calculation error: {str(e)[:50]}")
        return None

def calculate_volatility(df):
    """Calculate 20-period volatility of log returns"""
    if len(df) < 20:
        return 0.005  # Default reasonable volatility
    
    try:
        # Calculate log returns
        df['log_return'] = np.log(df['close'] / df['close'].shift(1))
        
        # 20-period rolling standard deviation
        sigma = df['log_return'].rolling(window=20).std().iloc[-1]
        
        # Handle NaN and extreme values
        if pd.isna(sigma):
            return 0.005
        
        # Bound between reasonable values
        return max(min(float(sigma), 0.05), 0.001)
        
    except Exception:
        return 0.005

def compute_signal(I, phi, sigma):
    """Compute trading signal and strength"""
    if phi <= 0 or sigma <= 0 or abs(I) < 0.0001:
        return 0.0, 0.0
    
    try:
        # Core signal formula
        Signal = np.sign(I) * (abs(I) / (phi * sigma))
        
        # Cap extreme signals
        Signal = max(min(Signal, 10), -10)
        
        # Calculate strength percentage
        Strength = min(100.0, abs(Signal) * 100)
        
        return float(Signal), float(Strength)
        
    except Exception:
        return 0.0, 0.0

# ====================
# DISPLAY FUNCTIONS
# ====================
def display_header(metrics, symbol_display):
    """Display header with key metrics"""
    if not metrics:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.warning("⏳ Waiting for market data...")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Best Bid", f"{metrics['best_bid']:,.2f}")
    with col2:
        st.metric("Best Ask", f"{metrics['best_ask']:,.2f}")
    with col3:
        st.metric("Mid Price", f"{metrics['P']:,.2f}")
    with col4:
        st.metric("Spread", f"{metrics['S']:.4f}")

def display_volume_info(metrics):
    """Display volume and imbalance metrics"""
    if not metrics:
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Format volume based on size
        vol_display = f"{metrics['V_bid']:,.3f}" if metrics['V_bid'] < 1000 else f"{metrics['V_bid']/1000:,.2f}K"
        st.metric("Bid Volume", vol_display)
    
    with col2:
        vol_display = f"{metrics['V_ask']:,.3f}" if metrics['V_ask'] < 1000 else f"{metrics['V_ask']/1000:,.2f}K"
        st.metric("Ask Volume", vol_display)
    
    with col3:
        # Color-coded imbalance
        I_value = metrics['I']
        imbalance_color = "green" if I_value > 0.1 else "lightgreen" if I_value > 0 else \
                         "red" if I_value < -0.1 else "lightcoral" if I_value < 0 else "gray"
        
        st.markdown(
            f"**Volume Imbalance (I):** "
            f"<span style='color:{imbalance_color}; font-weight:bold'>{I_value:.4f}</span>",
            unsafe_allow_html=True
        )
        
        # Imbalance interpretation
        if I_value > 0.2:
            st.caption("Strong buying pressure")
        elif I_value > 0.05:
            st.caption("Moderate buying pressure")
        elif I_value < -0.2:
            st.caption("Strong selling pressure")
        elif I_value < -0.05:
            st.caption("Moderate selling pressure")
        else:
            st.caption("Balanced market")

def display_signal_panel(signal, strength, phi, sigma):
    """Display the main trading signal"""
    st.markdown("---")
    
    # Create two columns for signal display
    col1, col2 = st.columns([3, 2])
    
    with col1:
        # Determine signal strength and color
        if abs(signal) > 2:
            intensity = "STRONG"
            color = "darkgreen" if signal > 0 else "darkred"
            emoji = "🚀" if signal > 0 else "📉"
        elif abs(signal) > 0.5:
            intensity = "MODERATE"
            color = "green" if signal > 0 else "red"
            emoji = "📈" if signal > 0 else "📊"
        elif abs(signal) > 0.1:
            intensity = "WEAK"
            color = "lightgreen" if signal > 0 else "lightcoral"
            emoji = "↗️" if signal > 0 else "↘️"
        else:
            intensity = "NEUTRAL"
            color = "gray"
            emoji = "➖"
        
        # Signal direction
        direction = "BUY" if signal > 0 else "SELL" if signal < 0 else "NEUTRAL"
        
        # Display signal
        st.markdown(
            f"### {emoji} **{intensity} {direction} SIGNAL**  "
            f"<span style='color:{color}; font-size: 28px;'>{signal:+.4f}</span>",
            unsafe_allow_html=True
        )
        
        # Formula parameters
        st.markdown(f"**Relative Spread (φ):** `{phi:.6f}`")
        st.markdown(f"**Volatility (σ):** `{sigma:.6f}`")
        
        # Signal interpretation
        with st.expander("ℹ️ Signal Interpretation"):
            st.markdown("""
            **Signal Strength Guide:**
            - **|Signal| > 2**: Very strong trend signal
            - **0.5 < |Signal| ≤ 2**: Clear directional signal
            - **0.1 < |Signal| ≤ 0.5**: Weak but noticeable signal
            - **|Signal| ≤ 0.1**: Market noise, no clear direction
            
            **Calculation:** `Signal = sign(I) × (|I| ÷ (φ × σ))`
            """)
    
    with col2:
        # Strength gauge
        st.metric("💪 **Signal Strength**", f"{strength:.1f}%")
        
        # Progress bar with color gradient
        if strength > 70:
            bar_color = "#00cc00"  # Strong green
        elif strength > 30:
            bar_color = "#ffaa00"  # Orange
        else:
            bar_color = "#ff4444"  # Red
        
        # Custom progress bar
        st.markdown(
            f"""
            <div style="background: #e0e0e0; border-radius: 10px; height: 25px; margin: 15px 0;">
                <div style="background: {bar_color}; 
                          width: {strength}%; 
                          height: 100%; 
                          border-radius: 10px; 
                          transition: width 0.5s ease;">
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #666;">
                <span>0%</span>
                <span>25%</span>
                <span>50%</span>
                <span>75%</span>
                <span>100%</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Confidence level
        if strength > 80:
            st.success("High confidence signal")
        elif strength > 50:
            st.info("Moderate confidence")
        elif strength > 20:
            st.warning("Low confidence")
        else:
            st.caption("Very low confidence")

# ====================
# MAIN APPLICATION
# ====================
def main():
    """Main application controller"""
    
    # Initialize session state for tracking
    if 'data_refreshes' not in st.session_state:
        st.session_state.data_refreshes = 0
    
    # Status display
    status_text = st.empty()
    
    # Main content containers
    header_container = st.container()
    volume_container = st.container()
    signal_container = st.container()
    
    # Error tracking
    consecutive_errors = 0
    
    while True:
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Update status
            if exchange:
                status_text.caption(
                    f"🟢 Live | {selected_exchange_name} | {symbol} | "
                    f"Update #{st.session_state.data_refreshes + 1} | {current_time}"
                )
            else:
                status_text.error(
                    f"🔴 Disconnected | {selected_exchange_name} | {current_time}"
                )
                time.sleep(refresh_rate)
                continue
            
            # Fetch data
            order_book = fetch_order_book(exchange, symbol)
            df_historical = fetch_historical_data(exchange, symbol)
            
            if order_book:
                consecutive_errors = 0  # Reset error counter on success
                st.session_state.data_refreshes += 1
                
                # Calculate metrics
                metrics = calculate_metrics(order_book)
                
                if metrics:
                    # Calculate volatility and signal
                    sigma = calculate_volatility(df_historical)
                    signal, strength = compute_signal(metrics['I'], metrics['phi'], sigma)
                    
                    # Update displays
                    with header_container:
                        display_header(metrics, symbol)
                    
                    with volume_container:
                        display_volume_info(metrics)
                    
                    with signal_container:
                        display_signal_panel(signal, strength, metrics['phi'], sigma)
                else:
                    with header_container:
                        st.warning("Could not calculate metrics from order book data")
            
            else:
                consecutive_errors += 1
                if consecutive_errors > 2:
                    with header_container:
                        st.error(f"Failed to fetch data {consecutive_errors} times. Check exchange connection.")
            
            # Wait for next update
            time.sleep(refresh_rate)
            
        except KeyboardInterrupt:
            status_text.info("Application stopped")
            break
        except Exception as e:
            consecutive_errors += 1
            error_msg = str(e)
            if consecutive_errors <= 3:
                status_text.error(f"Error: {error_msg[:80]}...")
            time.sleep(refresh_rate)

# ====================
# SIDEBAR INFORMATION
# ====================
with st.sidebar.expander("📖 How to Use", expanded=False):
    st.markdown("""
    1. **Select Exchange**: Start with Bybit or OKX if Binance is blocked
    2. **Choose Pair**: BTC/USDT is recommended for testing
    3. **Wait for Data**: First load may take 10-20 seconds
    4. **Monitor Signal**: Green = Buy pressure, Red = Sell pressure
    
    **Troubleshooting**:
    - If connection fails, try another exchange
    - Bybit format: `BTC/USDT:USDT`
    - Ensure your region allows exchange access
    """)

with st.sidebar.expander("🔧 Technical Details", expanded=False):
    st.markdown("""
    **Formula Components**:
    - **I**: Volume Imbalance = (BidVol - AskVol) / TotalVol
    - **φ**: Relative Spread = (Ask - Bid) / MidPrice
    - **σ**: 20-period volatility of log returns
    
    **Exchange Notes**:
    - **Bybit**: Use `:USDT` suffix for linear futures
    - **OKX**: Perpetual swaps use `SWAP` type
    - **Binance**: May be blocked in some regions
    """)

# Restart button
if st.sidebar.button("🔄 Restart Data Feed", type="secondary"):
    st.session_state.data_refreshes = 0
    st.rerun()

# ====================
# APPLICATION START
# ====================
if __name__ == "__main__":
    main()