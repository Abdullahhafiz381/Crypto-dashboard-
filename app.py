import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import time

# ============================================================================
# SILENT MULTI-EXCHANGE SCANNER MODULE - ADDED
# ============================================================================
import asyncio
import websockets
import threading
from collections import deque, defaultdict

class _InternalExchangeScanner:
    def __init__(self):
        # WebSocket endpoints
        self.endpoints = {
            'BINANCE': 'wss://fstream.binance.com/stream?streams=',
            'BYBIT': 'wss://stream.bybit.com/v5/public/spot',
            'OKX': 'wss://ws.okx.com:8443/ws/v5/public'
        }
        
        # Exchange-specific subscription formats
        self.sub_formats = {
            'BINANCE': lambda s: f"{s.lower()}@depth10@100ms",
            'BYBIT': lambda s: {"op": "subscribe", "args": [f"orderbook.10.{s}"]},
            'OKX': lambda s: {"op": "subscribe", "args": [{"channel": "books", "instId": s}]}
        }
        
        # State per symbol per exchange
        self.state = defaultdict(lambda: {
            'mid_prices': deque(maxlen=20),
            'current_book': None,
            'last_update': None
        })
        
        # Valid symbols per exchange
        self.symbols = defaultdict(list)
        
        # Current signal output
        self.current_signal = None
        self.last_emitted = {}
        self.cooldown_seconds = 300
        
        # Active connections
        self.connections = {}
        self.running = False
        
        # Hidden formula variables
        self._epsilon = 1e-10
        
    def _calculate_signal(self, exchange, symbol, book_data):
        """Internal signal calculation - NO EXPOSURE"""
        state_key = (exchange, symbol)
        state = self.state[state_key]
        
        try:
            # Extract bid/ask from exchange-specific format
            if exchange == 'BINANCE':
                bids = [(float(b[0]), float(b[1])) for b in book_data['b'][:10]]
                asks = [(float(a[0]), float(a[1])) for a in book_data['a'][:10]]
            elif exchange == 'BYBIT':
                bids = [(float(b[0]), float(b[1])) for b in book_data['data']['b'][:10]]
                asks = [(float(a[0]), float(a[1])) for a in book_data['data']['a'][:10]]
            elif exchange == 'OKX':
                bids = [(float(b[0]), float(b[1])) for b in book_data['data'][0]['bids'][:10]]
                asks = [(float(a[0]), float(a[1])) for a in book_data['data'][0]['asks'][:10]]
            else:
                return None, 0.0
            
            if not bids or not asks:
                return None, 0.0
            
            # Best bid/ask
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            
            # P = (Bid + Ask) / 2
            P = (best_bid + best_ask) / 2.0
            
            # V_bid = Σ Bid Volume (top 10)
            V_bid = sum(vol for _, vol in bids)
            
            # V_ask = Σ Ask Volume (top 10)
            V_ask = sum(vol for _, vol in asks)
            
            # I = (V_bid - V_ask) / (V_bid + V_ask)
            I = (V_bid - V_ask) / (V_bid + V_ask + self._epsilon)
            
            # S = Ask - Bid
            S = best_ask - best_bid
            
            # φ = S / P
            phi = S / (P + self._epsilon)
            
            # Update mid-price history
            state['mid_prices'].append(P)
            
            # Need at least 20 points for std dev
            if len(state['mid_prices']) < 20:
                return None, 0.0
            
            # σ = StdDev( ln(P_t / P_t-1) )
            prices = list(state['mid_prices'])
            returns = []
            for i in range(1, len(prices)):
                if prices[i-1] > 0:
                    returns.append(np.log(prices[i] / prices[i-1]))
            
            if len(returns) < 2:
                return None, 0.0
            
            sigma = np.std(returns) + self._epsilon
            
            # Signal = sign(I) * ( abs(I) / (φ * σ) )
            signal = np.sign(I) * (abs(I) / (phi * sigma + self._epsilon))
            
            # Strength% = min(100, abs(Signal) * 100)
            strength = min(100.0, abs(signal) * 100.0)
            
            return signal, strength
            
        except Exception:
            return None, 0.0
    
    async def _handle_binance(self, websocket, exchange_name):
        """Binance WebSocket handler"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    stream = data.get('stream', '')
                    
                    # Extract symbol from stream name
                    if '@depth10' in stream:
                        symbol = stream.split('@')[0].upper() + 'USDT'
                        
                        # Update state
                        state_key = (exchange_name, symbol)
                        self.state[state_key]['current_book'] = data['data']
                        self.state[state_key]['last_update'] = datetime.now()
                        
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue
        except Exception:
            pass
    
    async def _handle_bybit(self, websocket, exchange_name):
        """Bybit WebSocket handler"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if 'topic' in data and 'orderbook' in data['topic']:
                        symbol = data['topic'].split('.')[-1]
                        
                        # Update state
                        state_key = (exchange_name, symbol)
                        self.state[state_key]['current_book'] = data
                        self.state[state_key]['last_update'] = datetime.now()
                        
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue
        except Exception:
            pass
    
    async def _handle_okx(self, websocket, exchange_name):
        """OKX WebSocket handler"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if 'arg' in data and data['arg']['channel'] == 'books':
                        symbol = data['arg']['instId']
                        
                        # Update state
                        state_key = (exchange_name, symbol)
                        self.state[state_key]['current_book'] = data
                        self.state[state_key]['last_update'] = datetime.now()
                        
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue
        except Exception:
            pass
    
    async def _connect_exchange(self, exchange_name):
        """Connect to single exchange"""
        while self.running:
            try:
                if exchange_name == 'BINANCE':
                    # Binance requires combined streams
                    symbols = self.symbols.get(exchange_name, [])
                    streams = [self.sub_formats[exchange_name](s) for s in symbols[:100]]
                    stream_url = self.endpoints[exchange_name] + '/'.join(streams)
                    
                    async with websockets.connect(stream_url) as ws:
                        self.connections[exchange_name] = ws
                        await self._handle_binance(ws, exchange_name)
                        
                elif exchange_name == 'BYBIT':
                    async with websockets.connect(self.endpoints[exchange_name]) as ws:
                        self.connections[exchange_name] = ws
                        
                        # Subscribe to symbols
                        symbols = self.symbols.get(exchange_name, [])
                        for symbol in symbols[:100]:
                            sub_msg = self.sub_formats[exchange_name](symbol)
                            await ws.send(json.dumps(sub_msg))
                        
                        await self._handle_bybit(ws, exchange_name)
                        
                elif exchange_name == 'OKX':
                    async with websockets.connect(self.endpoints[exchange_name]) as ws:
                        self.connections[exchange_name] = ws
                        
                        # Subscribe to symbols
                        symbols = self.symbols.get(exchange_name, [])
                        for symbol in symbols[:100]:
                            sub_msg = self.sub_formats[exchange_name](symbol)
                            await ws.send(json.dumps(sub_msg))
                        
                        await self._handle_okx(ws, exchange_name)
                        
            except Exception:
                # Silently reconnect
                await asyncio.sleep(5)
                continue
    
    async def _fetch_symbols(self):
        """Fetch available symbols from exchanges"""
        import requests
        
        # Binance Futures symbols
        try:
            resp = requests.get('https://fapi.binance.com/fapi/v1/exchangeInfo', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.symbols['BINANCE'] = [
                    s['symbol'] for s in data['symbols'] 
                    if s['status'] == 'TRADING' and s['symbol'].endswith('USDT')
                ][:150]
        except Exception:
            self.symbols['BINANCE'] = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        
        # Bybit symbols
        try:
            resp = requests.get('https://api.bybit.com/v5/market/instruments-info?category=spot', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.symbols['BYBIT'] = [
                    s['symbol'] for s in data['result']['list']
                    if s['status'] == 'Trading' and s['quoteCoin'] == 'USDT'
                ][:150]
        except Exception:
            self.symbols['BYBIT'] = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT']
        
        # OKX symbols
        try:
            resp = requests.get('https://www.okx.com/api/v5/public/instruments?instType=SWAP', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.symbols['OKX'] = [
                    s['instId'] for s in data['data']
                    if s['state'] == 'live' and '-USDT-' in s['instId']
                ][:150]
        except Exception:
            self.symbols['OKX'] = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP']
    
    async def _scanning_loop(self):
        """Main scanning loop"""
        await self._fetch_symbols()
        
        # Start exchange connections
        tasks = []
        for exchange in ['BINANCE', 'BYBIT', 'OKX']:
            task = asyncio.create_task(self._connect_exchange(exchange))
            tasks.append(task)
        
        # Main processing loop
        while self.running:
            try:
                # Scan all symbols
                candidates = []
                
                for (exchange, symbol), state in list(self.state.items()):
                    book = state.get('current_book')
                    if not book:
                        continue
                    
                    # Calculate signal
                    signal, strength = self._calculate_signal(exchange, symbol, book)
                    
                    if signal is not None and strength > 0:
                        candidates.append({
                            'exchange': exchange,
                            'symbol': symbol,
                            'signal': signal,
                            'strength': strength
                        })
                
                # Select global winner
                if candidates:
                    # Sort by strength
                    candidates.sort(key=lambda x: x['strength'], reverse=True)
                    winner = candidates[0]
                    
                    # Check cooldown
                    last_emit = self.last_emitted.get(winner['symbol'])
                    now = time.time()
                    
                    if not last_emit or (now - last_emit) > self.cooldown_seconds:
                        # Determine direction
                        direction = "BUY" if winner['signal'] > 0 else "SELL"
                        
                        # Determine leverage (MAX for highest confidence)
                        leverage = "MAX" if winner['strength'] >= 85.0 else "LOW"
                        
                        # Update output
                        self.current_signal = {
                            'symbol': winner['symbol'],
                            'direction': direction,
                            'leverage': leverage,
                            'exchange': winner['exchange']
                        }
                        
                        # Update cooldown
                        self.last_emitted[winner['symbol']] = now
                
                await asyncio.sleep(0.1)
                
            except Exception:
                await asyncio.sleep(1)
                continue
    
    def start(self):
        """Start the scanner in background"""
        if not self.running:
            self.running = True
            
            def run_async():
                asyncio.run(self._run())
            
            thread = threading.Thread(target=run_async, daemon=True)
            thread.start()
    
    async def _run(self):
        """Async entry point"""
        await self._scanning_loop()
    
    def stop(self):
        """Stop the scanner"""
        self.running = False
    
    def get_signal(self):
        """Get current signal - ONLY ALLOWED OUTPUT"""
        return self.current_signal

# ============================================================================
# PUBLIC INTERFACE - ONLY THIS IS EXPOSED
# ============================================================================

_scanner_instance = None

def initialize_scanner():
    """Initialize the scanner module"""
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = _InternalExchangeScanner()
        _scanner_instance.start()

def get_market_signal():
    """Get current market signal - ONLY ALLOWED OUTPUT"""
    global _scanner_instance
    if _scanner_instance is None:
        initialize_scanner()
    return _scanner_instance.get_signal()

# ============================================================================
# EXISTING CODE CONTINUES
# ============================================================================

# GODZILLERS Streamlit setup
st.set_page_config(
    page_title="🔥 GODZILLERS CRYPTO TRACKER",
    page_icon="🐲",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# GODZILLERS CSS with red and black theme - UPDATED FOR BETTER LOGIN
st.markdown("""
<style>
    /* Hide all Streamlit elements on login page */
    .login-page .main > div {
        padding: 0 !important;
        margin: 0 !important;
    }
    
    .login-page #MainMenu {visibility: hidden;}
    .login-page header {visibility: hidden;}
    .login-page footer {visibility: hidden;}
    .login-page .stAppView {padding: 0 !important; margin: 0 !important;}
    
    .main {
        background: linear-gradient(135deg, #000000 0%, #1a0000 50%, #330000 100%);
        color: #ffffff;
        font-family: 'Rajdhani', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #000000 0%, #1a0000 50%, #330000 100%);
    }
    
    .godzillers-header {
        background: linear-gradient(90deg, #ff0000 0%, #ff4444 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Orbitron', monospace;
        font-weight: 900;
        text-align: center;
        font-size: 4rem;
        margin-bottom: 0.5rem;
        text-shadow: 0 0 30px rgba(255, 0, 0, 0.7);
        letter-spacing: 3px;
    }
    
    .godzillers-subheader {
        color: #ff6666;
        font-family: 'Orbitron', monospace;
        text-align: center;
        font-size: 1.4rem;
        margin-bottom: 2rem;
        letter-spacing: 3px;
        text-transform: uppercase;
    }
    
    .godzillers-card {
        background: rgba(20, 0, 0, 0.9);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 0, 0, 0.5);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 8px 32px rgba(255, 0, 0, 0.3);
        transition: all 0.3s ease;
    }
    
    .godzillers-card:hover {
        border-color: #ff4444;
        box-shadow: 0 8px 32px rgba(255, 0, 0, 0.5);
        transform: translateY(-2px);
    }
    
    .signal-buy {
        background: linear-gradient(135deg, rgba(0, 255, 0, 0.1) 0%, rgba(0, 100, 0, 0.3) 100%);
        border: 1px solid #00ff00;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 20px rgba(0, 255, 0, 0.3);
    }
    
    .signal-sell {
        background: linear-gradient(135deg, rgba(255, 0, 0, 0.2) 0%, rgba(100, 0, 0, 0.4) 100%);
        border: 1px solid #ff0000;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.4);
    }
    
    .signal-neutral {
        background: linear-gradient(135deg, rgba(255, 165, 0, 0.1) 0%, rgba(100, 65, 0, 0.3) 100%);
        border: 1px solid #ffa500;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 20px rgba(255, 165, 0, 0.3);
    }
    
    .scalp-signal-urgent {
        background: linear-gradient(135deg, rgba(255, 215, 0, 0.2) 0%, rgba(255, 140, 0, 0.4) 100%);
        border: 2px solid #ffd700;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 25px rgba(255, 215, 0, 0.6);
        animation: pulse-urgent 1s infinite;
    }
    
    @keyframes pulse-urgent {
        0% { box-shadow: 0 0 25px rgba(255, 215, 0, 0.6); }
        50% { box-shadow: 0 0 40px rgba(255, 215, 0, 0.9); }
        100% { box-shadow: 0 0 25px rgba(255, 215, 0, 0.6); }
    }
    
    .scalp-signal-confirmed {
        background: linear-gradient(135deg, rgba(0, 255, 0, 0.15) 0%, rgba(0, 100, 0, 0.3) 100%);
        border: 2px solid #00ff00;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 30px rgba(0, 255, 0, 0.5);
        animation: pulse-confirmed 2s infinite;
    }
    
    @keyframes pulse-confirmed {
        0% { box-shadow: 0 0 20px rgba(0, 255, 0, 0.5); }
        50% { box-shadow: 0 0 35px rgba(0, 255, 0, 0.8); }
        100% { box-shadow: 0 0 20px rgba(0, 255, 0, 0.5); }
    }
    
    .scalp-signal-warning {
        background: linear-gradient(135deg, rgba(255, 0, 0, 0.15) 0%, rgba(100, 0, 0, 0.3) 100%);
        border: 2px solid #ff0000;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 0 30px rgba(255, 0, 0, 0.5);
        animation: pulse-warning 2s infinite;
    }
    
    @keyframes pulse-warning {
        0% { box-shadow: 0 0 20px rgba(255, 0, 0, 0.5); }
        50% { box-shadow: 0 0 35px rgba(255, 0, 0, 0.8); }
        100% { box-shadow: 0 0 20px rgba(255, 0, 0, 0.5); }
    }
    
    .price-glow {
        background: linear-gradient(135deg, rgba(255, 0, 0, 0.15) 0%, rgba(139, 0, 0, 0.25) 100%);
        border: 1px solid rgba(255, 0, 0, 0.6);
        border-radius: 15px;
        padding: 2rem;
        margin: 1rem 0;
        box-shadow: 0 0 40px rgba(255, 0, 0, 0.4);
        position: relative;
        overflow: hidden;
    }
    
    .price-glow::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(45deg, transparent, rgba(255, 0, 0, 0.1), transparent);
        animation: shine 3s infinite linear;
    }
    
    @keyframes shine {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    
    .godzillers-button {
        background: linear-gradient(90deg, #ff0000 0%, #cc0000 100%);
        border: none;
        border-radius: 25px;
        color: #000000;
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        padding: 0.75rem 2rem;
        transition: all 0.3s ease;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .godzillers-button:hover {
        background: linear-gradient(90deg, #ff4444 0%, #ff0000 100%);
        transform: scale(1.05);
        box-shadow: 0 0 30px rgba(255, 0, 0, 0.7);
        color: #000000;
    }
    
    .metric-godzillers {
        background: rgba(0, 0, 0, 0.7);
        border: 1px solid rgba(255, 0, 0, 0.3);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .trademark {
        text-align: center;
        color: #ff6666;
        font-family: 'Orbitron', monospace;
        font-size: 0.9rem;
        margin-top: 2rem;
        letter-spacing: 2px;
        text-transform: uppercase;
    }
    
    .section-header {
        font-family: 'Orbitron', monospace;
        font-size: 2rem;
        background: linear-gradient(90deg, #ff0000 0%, #ff4444 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 2rem 0 1rem 0;
        text-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    .divider {
        height: 3px;
        background: linear-gradient(90deg, transparent 0%, #ff0000 50%, transparent 100%);
        margin: 2rem 0;
    }
    
    .pulse {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    
    .coin-card {
        background: rgba(30, 0, 0, 0.9);
        border: 1px solid rgba(255, 0, 0, 0.3);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem;
        transition: all 0.3s ease;
    }
    
    .coin-card:hover {
        border-color: #ff0000;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.4);
        transform: translateY(-3px);
    }
    
    .fire-effect {
        background: linear-gradient(45deg, #ff0000, #ff4400, #ff0000);
        background-size: 200% 200%;
        animation: fire 2s ease infinite;
    }
    
    @keyframes fire {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .alert-banner {
        background: linear-gradient(90deg, #ff0000, #cc0000);
        border: 2px solid #ff4444;
        border-radius: 10px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
        animation: pulse 2s infinite;
    }
    
    /* Login Page Styles - SIMPLIFIED AND CENTERED */
    .login-container {
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        background: linear-gradient(135deg, #000000 0%, #1a0000 50%, #330000 100%);
        padding: 20px;
    }
    
    .login-card {
        background: rgba(20, 0, 0, 0.95);
        backdrop-filter: blur(10px);
        border: 2px solid rgba(255, 0, 0, 0.6);
        border-radius: 20px;
        padding: 3rem;
        width: 100%;
        max-width: 450px;
        box-shadow: 0 0 50px rgba(255, 0, 0, 0.5);
        text-align: center;
    }
    
    .login-header {
        background: linear-gradient(90deg, #ff0000 0%, #ff4444 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Orbitron', monospace;
        font-weight: 900;
        font-size: 2.5rem;
        margin-bottom: 1rem;
        text-shadow: 0 0 20px rgba(255, 0, 0, 0.7);
    }
    
    .login-subheader {
        color: #ff6666;
        font-family: 'Orbitron', monospace;
        font-size: 1rem;
        margin-bottom: 2rem;
        letter-spacing: 2px;
    }
    
    .login-input {
        background: rgba(0, 0, 0, 0.8);
        border: 1px solid rgba(255, 0, 0, 0.5);
        border-radius: 10px;
        color: white;
        font-family: 'Rajdhani', sans-serif;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        width: 100%;
        font-size: 1rem;
    }
    
    .login-input:focus {
        outline: none;
        border-color: #ff0000;
        box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
    }
    
    .login-button {
        background: linear-gradient(90deg, #ff0000 0%, #cc0000 100%);
        border: none;
        border-radius: 25px;
        color: #000000;
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        padding: 0.75rem 2rem;
        margin: 1rem 0;
        width: 100%;
        transition: all 0.3s ease;
        box-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 1.1rem;
    }
    
    .login-button:hover {
        background: linear-gradient(90deg, #ff4444 0%, #ff0000 100%);
        transform: scale(1.05);
        box-shadow: 0 0 30px rgba(255, 0, 0, 0.7);
    }
    
    .logout-button {
        background: linear-gradient(90deg, #ff0000 0%, #cc0000 100%);
        border: none;
        border-radius: 10px;
        color: #000000;
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        padding: 0.5rem 1rem;
        margin: 1rem;
        transition: all 0.3s ease;
        box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
        text-transform: uppercase;
        letter-spacing: 1px;
        font-size: 0.8rem;
        position: fixed;
        top: 10px;
        right: 10px;
        z-index: 1000;
    }
    
    /* Custom metric styling */
    [data-testid="stMetricValue"] {
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        color: #ff4444;
    }
    
    [data-testid="stMetricLabel"] {
        font-family: 'Rajdhani', sans-serif;
        font-weight: 600;
        color: #ff8888;
    }
    
    [data-testid="stMetricDelta"] {
        font-family: 'Orbitron', monospace;
    }
    
    .dragon-emoji {
        font-size: 2rem;
        text-shadow: 0 0 10px #ff0000;
    }
    
    .confirmation-badge {
        display: inline-block;
        background: linear-gradient(90deg, #00ff00, #00cc00);
        color: #000000;
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.8rem;
        margin: 0.2rem;
        box-shadow: 0 0 10px rgba(0, 255, 0, 0.5);
    }
    
    .warning-badge {
        display: inline-block;
        background: linear-gradient(90deg, #ff0000, #cc0000);
        color: #ffffff;
        font-family: 'Orbitron', monospace;
        font-weight: 700;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.8rem;
        margin: 0.2rem;
        box-shadow: 0 0 10px rgba(255, 0, 0, 0.5);
    }
</style>
""", unsafe_allow_html=True)

# Simple authentication system
def check_credentials(username, password):
    """Check if username and password are correct"""
    # In a real application, use proper password hashing and secure storage
    valid_users = {
        "godziller": "dragonfire2025",
        "admin": "cryptoking",
        "trader": "bullmarket"
    }
    return username in valid_users and valid_users[username] == password

def login_page():
    """Display login page - SIMPLIFIED VERSION"""
    # Clear any existing content
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create centered login form directly
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
        <div style='
            background: rgba(20, 0, 0, 0.95);
            border: 2px solid rgba(255, 0, 0, 0.6);
            border-radius: 20px;
            padding: 3rem;
            box-shadow: 0 0 50px rgba(255, 0, 0, 0.5);
            text-align: center;
            margin: 2rem 0;
        '>
            <h1 style='
                background: linear-gradient(90deg, #ff0000 0%, #ff4444 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-family: Orbitron, monospace;
                font-weight: 900;
                font-size: 2.5rem;
                margin-bottom: 1rem;
                text-shadow: 0 0 20px rgba(255, 0, 0, 0.7);
            '>🐲 GODZILLERS</h1>
            <p style='
                color: #ff6666;
                font-family: Orbitron, monospace;
                font-size: 1rem;
                margin-bottom: 2rem;
                letter-spacing: 2px;
            '>PRIVATE CRYPTO WARFARE SYSTEM</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("👤 DRAGON NAME", placeholder="Enter your dragon name...")
            password = st.text_input("🔐 FIRE BREATH", type="password", placeholder="Enter your fire breath...")
            
            login_button = st.form_submit_button("🔥 IGNITE DRAGON FIRE", use_container_width=True)
            
            if login_button:
                if check_credentials(username, password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success("✅ Dragon fire ignited! Access granted.")
                    st.rerun()
                else:
                    st.error("❌ Invalid dragon name or fire breath!")

def get_crypto_prices():
    """Get crypto prices from multiple sources with fallback"""
    coins = {
        'BTCUSDT': 'bitcoin',
        'ETHUSDT': 'ethereum'
    }
    
    prices = {}
    
    try:
        # Try Binance first for all coins
        for symbol in coins.keys():
            try:
                response = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    prices[symbol] = float(data['price'])
                else:
                    prices[symbol] = None
            except Exception as e:
                prices[symbol] = None
        
        # Fill missing prices with CoinGecko
        missing_coins = [coin_id for symbol, coin_id in coins.items() if prices.get(symbol) is None]
        if missing_coins:
            try:
                coin_ids = ','.join(missing_coins)
                response = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids}&vs_currencies=usd", timeout=5)
                if response.status_code == 200:
                    gecko_data = response.json()
                    for symbol, coin_id in coins.items():
                        if prices.get(symbol) is None and coin_id in gecko_data:
                            prices[symbol] = float(gecko_data[coin_id]['usd'])
            except Exception as e:
                # If CoinGecko fails, set default prices
                for symbol in coins:
                    if prices.get(symbol) is None:
                        prices[symbol] = 0.0
                
    except Exception as e:
        st.error(f"Error fetching prices: {str(e)}")
        # Set default prices if everything fails
        for symbol in coins:
            prices[symbol] = 0.0
    
    return prices

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
                    self.last_snapshot_check = data.get('last_snapshot_check')
            else:
                self.current_data = None
                self.previous_data = None
                self.last_snapshot_check = None
        except Exception as e:
            self.current_data = None
            self.previous_data = None
            self.last_snapshot_check = None
    
    def save_node_data(self):
        """Save current and previous node data"""
        try:
            data = {
                'current_data': self.current_data,
                'previous_data': self.previous_data,
                'last_snapshot_check': self.last_snapshot_check,
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
            if response.status_code == 200:
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
            else:
                st.error(f"API returned status code: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"Error fetching node data: {e}")
            return None
    
    def update_node_data(self):
        """Fetch new data and shift current to previous"""
        new_data = self.fetch_node_data()
        if not new_data:
            return False
        
        # Update snapshot check time
        self.last_snapshot_check = datetime.now().isoformat()
        
        # Shift current to previous, set new data as current
        self.previous_data = self.current_data
        self.current_data = new_data
        
        self.save_node_data()
        return True
    
    def calculate_tor_signal(self):
        """Calculate signal based on Tor percentage changes - HIDDEN ANALYSIS"""
        if not self.current_data or not self.previous_data:
            return {
                'signal': "🔄 NEED DATA",
                'bias': "UPDATE_REQUIRED",
                'strength': "NEUTRAL",
                'tor_change': 0,
                'momentum': 0
            }
        
        current_tor_pct = self.current_data['tor_percentage']
        previous_tor_pct = self.previous_data['tor_percentage']
        
        # Calculate percentage change in Tor nodes
        tor_pct_change = current_tor_pct - previous_tor_pct
        
        # Calculate momentum (rate of change)
        tor_momentum = tor_pct_change * 100  # Amplify for scoring
        
        # TOR PERCENTAGE SIGNAL LOGIC (HIDDEN FROM USER)
        if tor_pct_change >= 1.0:  # Tor percentage increased by 1.0% or more
            signal = "🐲 GODZILLA DUMP 🐲"
            bias = "EXTREME_BEARISH"
            strength = "EXTREME"
        elif tor_pct_change >= 0.5:  # Tor percentage increased by 0.5-0.99%
            signal = "🔥 STRONG SELL 🔥"
            bias = "VERY_BEARISH"
            strength = "STRONG"
        elif tor_pct_change >= 0.1:  # Tor percentage increased by 0.1-0.49%
            signal = "SELL"
            bias = "BEARISH"
            strength = "MODERATE"
        elif tor_pct_change <= -1.0:  # Tor percentage decreased by 1.0% or more
            signal = "🐲 GODZILLA PUMP 🐲"
            bias = "EXTREME_BULLISH"
            strength = "EXTREME"
        elif tor_pct_change <= -0.5:  # Tor percentage decreased by 0.5-0.99%
            signal = "🚀 STRONG BUY 🚀"
            bias = "VERY_BULLISH"
            strength = "STRONG"
        elif tor_pct_change <= -0.1:  # Tor percentage decreased by 0.1-0.49%
            signal = "BUY"
            bias = "BULLISH"
            strength = "MODERATE"
        else:  # Change between -0.1% and +0.1%
            signal = "HOLD"
            bias = "NEUTRAL"
            strength = "WEAK"
        
        return {
            'signal': signal,
            'bias': bias,
            'strength': strength,
            'tor_change': tor_pct_change,
            'momentum': tor_momentum
        }
    
    def generate_bitnodes_scalp_signal(self, symbol, current_price):
        """Generate scalp signal based ONLY on Bitnodes Tor analysis"""
        tor_signal = self.calculate_tor_signal()
        
        # Determine signal based on Bitnodes bias
        if "BULLISH" in tor_signal['bias']:
            if tor_signal['strength'] == "EXTREME":
                composite_signal = "🚨 EXTREME BULLISH"
                signal_class = "scalp-signal-confirmed"
                urgency = "EXTREME"
            elif tor_signal['strength'] == "STRONG":
                composite_signal = "🔥 STRONG BULLISH"
                signal_class = "scalp-signal-urgent"
                urgency = "HIGH"
            elif tor_signal['strength'] == "MODERATE":
                composite_signal = "🟢 BULLISH BIAS"
                signal_class = "signal-buy"
                urgency = "MEDIUM"
            else:
                composite_signal = "⚡ NEUTRAL BULLISH"
                signal_class = "signal-neutral"
                urgency = "LOW"
        elif "BEARISH" in tor_signal['bias']:
            if tor_signal['strength'] == "EXTREME":
                composite_signal = "🚨 EXTREME BEARISH"
                signal_class = "scalp-signal-warning"
                urgency = "EXTREME"
            elif tor_signal['strength'] == "STRONG":
                composite_signal = "🔥 STRONG BEARISH"
                signal_class = "scalp-signal-warning"
                urgency = "HIGH"
            elif tor_signal['strength'] == "MODERATE":
                composite_signal = "🔴 BEARISH BIAS"
                signal_class = "signal-sell"
                urgency = "MEDIUM"
            else:
                composite_signal = "⚡ NEUTRAL BEARISH"
                signal_class = "signal-neutral"
                urgency = "LOW"
        else:
            composite_signal = "🐲 AWAITING SIGNAL"
            signal_class = "signal-neutral"
            urgency = "LOW"
        
        # Generate reasoning based only on Bitnodes
        reasoning = f"Bitnodes Tor Analysis: {tor_signal['signal']} (Change: {tor_signal['tor_change']:+.3f}%)"
        
        return {
            'composite_signal': composite_signal,
            'signal_class': signal_class,
            'urgency': urgency,
            'confirmation_score': 100 if tor_signal['strength'] in ["EXTREME", "STRONG"] else 50,
            'confirmations': [f"Bitnodes {tor_signal['strength']} Signal"],
            'tor_bias': tor_signal['bias'],
            'tor_strength': tor_signal['strength'],
            'tor_change': tor_signal['tor_change'],
            'reasoning': reasoning
        }

def get_coin_display_name(symbol):
    """Get display name for crypto symbols"""
    names = {
        'BTCUSDT': 'Bitcoin',
        'ETHUSDT': 'Ethereum'
    }
    return names.get(symbol, symbol)

def get_coin_emoji(symbol):
    """Get emoji for crypto symbols - GODZILLERS theme"""
    emojis = {
        'BTCUSDT': '🐲',
        'ETHUSDT': '🔥'
    }
    return emojis.get(symbol, '💀')

def main_app():
    """Main application after login"""
    # Initialize analyzer
    analyzer = CryptoAnalyzer()
    
    # [NEW] Initialize silent scanner
    initialize_scanner()
    
    # Logout button
    if st.button("🚪 LOGOUT", key="logout", use_container_width=False):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
    
    # Welcome message
    st.markdown(f'<p style="text-align: right; color: #ff4444; font-family: Orbitron; margin: 0.5rem 1rem;">Welcome, {st.session_state.username}!</p>', unsafe_allow_html=True)
    
    # GODZILLERS Header
    st.markdown('<h1 class="godzillers-header">🔥 GODZILLERS CRYPTO TRACKER</h1>', unsafe_allow_html=True)
    st.markdown('<p class="godzillers-subheader">AI-POWERED SIGNALS • REAL-TIME PRICES • DRAGON FIRE PRECISION</p>', unsafe_allow_html=True)
    
    # UPDATE SIGNALS BUTTON
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<h2 class="section-header">🎯 GODZILLERS AI SIGNALS</h2>', unsafe_allow_html=True)
    with col2:
        if st.button("🐉 GENERATE SIGNALS", key="refresh_main", use_container_width=True, type="primary"):
            with st.spinner("🔥 Activating dragon fire analysis..."):
                if analyzer.update_node_data():
                    st.success("✅ Signals updated successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to update signals")
    
    # LIVE CRYPTO PRICES SECTION
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">💰 DRAGON FIRE PRICES</h2>', unsafe_allow_html=True)
    
    # Get all crypto prices
    prices = get_crypto_prices()
    
    if prices:
        # Display BTC price prominently
        btc_price = prices.get('BTCUSDT')
        if btc_price and btc_price > 0:
            st.markdown('<div class="price-glow">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f'<div style="text-align: center;"><span style="font-family: Orbitron; font-size: 3rem; font-weight: 900; background: linear-gradient(90deg, #ff0000, #ff4444); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${btc_price:,.2f}</span></div>', unsafe_allow_html=True)
                st.markdown('<p style="text-align: center; color: #ff8888; font-family: Rajdhani;">BITCOIN PRICE (USD)</p>', unsafe_allow_html=True)
            
            with col2:
                st.metric(
                    label="24H STATUS",
                    value="🔥 LIVE",
                    delta="Godzillers"
                )
            
            with col3:
                st.metric(
                    label="DATA SOURCE", 
                    value="BINANCE API",
                    delta="RED HOT"
                )
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("❌ Could not fetch Bitcoin price")
        
        # Display all coins in a grid
        st.markdown('<h3 style="font-family: Orbitron; color: #ff4444; margin: 1rem 0;">📊 ALTCOIN BATTLEFIELD</h3>', unsafe_allow_html=True)
        
        # Create columns for coin grid
        coins_to_display = {k: v for k, v in prices.items() if k != 'BTCUSDT' and v and v > 0}
        if coins_to_display:
            # Use 2 columns for cleaner layout with fewer coins
            cols = st.columns(2)
            
            for idx, (symbol, price) in enumerate(coins_to_display.items()):
                if price:
                    with cols[idx % 2]:
                        emoji = get_coin_emoji(symbol)
                        name = get_coin_display_name(symbol)            
                        st.markdown(f'''
                        <div class="coin-card">
                            <div style="text-align: center;">
                                <h4 style="font-family: Orbitron; color: #ff4444; margin: 0.5rem 0; font-size: 1.1rem;">{emoji} {name}</h4>
                                <p style="font-family: Orbitron; font-size: 1.3rem; font-weight: 700; color: #ffffff; margin: 0.5rem 0;">${price:,.2f}</p>
                                <p style="color: #ff8888; font-family: Rajdhani; font-size: 0.9rem; margin: 0;">{symbol}</p>
                            </div>
                        </div>
                        ''', unsafe_allow_html=True)
        else:
            st.warning("⚠️ Could not fetch altcoin prices")
        
        st.markdown(f'<p style="text-align: center; color: #ff8888; font-family: Rajdhani;">🕒 Prices updated: {datetime.now().strftime("%H:%M:%S")}</p>', unsafe_allow_html=True)
    else:
        st.error("❌ Could not fetch crypto prices")
    
    # ========================================================================
    # [NEW] SILENT SCANNER SIGNAL DISPLAY - ADDED
    # ========================================================================
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">🔇 SILENT SCANNER SIGNAL</h2>', unsafe_allow_html=True)
    
    # Get signal from scanner
    scanner_signal = get_market_signal()
    
    if scanner_signal:
        # Display scanner signal
        signal_class = "signal-buy" if scanner_signal['direction'] == "BUY" else "signal-sell"
        leverage_class = "confirmation-badge" if scanner_signal['leverage'] == "MAX" else "warning-badge"
        
        st.markdown(f'''
        <div class="{signal_class}">
            <div style="text-align: center;">
                <h3 style="font-family: Orbitron; margin: 0.5rem 0; font-size: 1.3rem;">🎯 REAL-TIME SCANNER</h3>
                <p style="font-family: Orbitron; font-size: 1.5rem; font-weight: 700; margin: 0.5rem 0;">{scanner_signal['direction']} {scanner_signal['symbol']}</p>
                <p style="color: #ffd700; font-family: Orbitron; font-size: 1.1rem; margin: 0.2rem 0;">Exchange: {scanner_signal['exchange']}</p>
                <div style="margin: 0.5rem 0;">
                    <span class="{leverage_class}">LEVERAGE: {scanner_signal['leverage']}</span>
                </div>
                <p style="color: #ff8888; font-family: Rajdhani; font-size: 0.9rem; margin: 0.2rem 0;">Multi-Exchange Live Data • Silent Mode</p>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('''
        <div class="signal-neutral">
            <div style="text-align: center;">
                <h3 style="font-family: Orbitron; margin: 0.5rem 0; font-size: 1.3rem;">🔇 SCANNER SILENT</h3>
                <p style="font-family: Orbitron; font-size: 1.2rem; font-weight: 700; margin: 0.5rem 0;">NO QUALIFIED SIGNAL</p>
                <p style="color: #ff8888; font-family: Rajdhani; font-size: 0.9rem; margin: 0.2rem 0;">Scanning 300+ symbols across 3 exchanges</p>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    
    # BITNODES SCALPING SIGNALS SECTION
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">⚡ DRAGON SCALPING SIGNALS</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color: #ff8888; font-family: Rajdhani; text-align: center;">BITNODES TOR ANALYSIS SYSTEM • REAL-TIME NETWORK DATA</p>', unsafe_allow_html=True)
    
    if analyzer.current_data and analyzer.previous_data and prices:
        # Display scalp signals for each coin
        scalp_cols = st.columns(2)
        
        for idx, symbol in enumerate(['BTCUSDT', 'ETHUSDT']):
            if prices.get(symbol):
                with scalp_cols[idx % 2]:
                    current_price = prices[symbol]
                    scalp_signal = analyzer.generate_bitnodes_scalp_signal(symbol, current_price)
                    
                    emoji = get_coin_emoji(symbol)
                    name = get_coin_display_name(symbol)
                    
                    # Display main signal card
                    st.markdown(f'''
                    <div class="{scalp_signal['signal_class']}">
                        <div style="text-align: center;">
                            <h3 style="font-family: Orbitron; margin: 0.5rem 0; font-size: 1.3rem;">{emoji} {name}</h3>
                            <p style="font-family: Orbitron; font-size: 1.5rem; font-weight: 700; margin: 0.5rem 0;">{scalp_signal['composite_signal']}</p>
                            <p style="color: #ffd700; font-family: Orbitron; font-size: 1.1rem; margin: 0.2rem 0;">BITNODES SCORE: {scalp_signal['confirmation_score']}%</p>
                            <p style="color: #ff8888; font-family: Rajdhani; font-size: 0.9rem; margin: 0.2rem 0;">Urgency: {scalp_signal['urgency']}</p>
                            <p style="color: #ffffff; font-family: Rajdhani; font-size: 0.8rem; margin: 0.2rem 0;">{scalp_signal['reasoning']}</p>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                    
                    # Display confirmation badges
                    st.markdown('<div style="text-align: center; margin: 0.5rem 0;">', unsafe_allow_html=True)
                    for confirmation in scalp_signal['confirmations']:
                        if "EXTREME" in confirmation or "STRONG" in confirmation:
                            st.markdown(f'<span class="confirmation-badge">🐲 {confirmation}</span>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<span style="display: inline-block; background: #444; color: #fff; padding: 0.2rem 0.5rem; border-radius: 10px; font-size: 0.7rem; margin: 0.1rem;">{confirmation}</span>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Display Bitnodes metrics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(
                            label="TOR CHANGE",
                            value=f"{scalp_signal['tor_change']:+.3f}%",
                            delta="Bitnodes Analysis"
                        )
                    with col2:
                        st.metric(
                            label="SIGNAL BIAS", 
                            value=scalp_signal['tor_bias'].replace('_', ' '),
                            delta=scalp_signal['tor_strength']
                        )
                    with col3:
                        st.metric(
                            label="CURRENT PRICE",
                            value=f"${current_price:,.2f}",
                            delta="Live Market"
                        )
    else:
        st.info("🔥 Generate signals to see Bitnodes confirmed scalping opportunities")
    
    # MAIN SIGNAL DISPLAY WITH GODZILLERS THEME
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">🎯 GODZILLERS AI SIGNALS</h2>', unsafe_allow_html=True)
    
    if analyzer.current_data and analyzer.previous_data:
        tor_signal_data = analyzer.calculate_tor_signal()
        
        # Display main signal with GODZILLERS styling
        if "GODZILLA DUMP" in tor_signal_data['signal']:
            signal_class = "signal-sell"
            emoji = "🐲💀🔥"
            explanation = "EXTREME BEARISH SIGNAL - Market conditions indicate strong selling pressure"
        elif "STRONG SELL" in tor_signal_data['signal']:
            signal_class = "signal-sell"
            emoji = "🐲🔥"
            explanation = "STRONG SELL SIGNAL - Significant bearish momentum detected"
        elif "SELL" in tor_signal_data['signal']:
            signal_class = "signal-sell"
            emoji = "🔴"
            explanation = "SELL SIGNAL - Bearish conditions forming"
        elif "GODZILLA PUMP" in tor_signal_data['signal']:
            signal_class = "signal-buy"
            emoji = "🐲🚀🌟"
            explanation = "EXTREME BULLISH SIGNAL - Strong buying pressure detected"
        elif "STRONG BUY" in tor_signal_data['signal']:
            signal_class = "signal-buy"
            emoji = "🐲🚀"
            explanation = "STRONG BUY SIGNAL - Significant bullish momentum building"
        elif "BUY" in tor_signal_data['signal']:
            signal_class = "signal-buy"
            emoji = "🟢"
            explanation = "BUY SIGNAL - Bullish conditions forming"
        else:
            signal_class = "signal-neutral"
            emoji = "🐲⚡"
            explanation = "MARKET NEUTRAL - Awaiting stronger directional signals"
        
        st.markdown(f'<div class="{signal_class}">', unsafe_allow_html=True)
        st.markdown(f'<h2 style="font-family: Orbitron; text-align: center; margin: 0.5rem 0;">{emoji} {tor_signal_data["signal"]} {emoji}</h2>', unsafe_allow_html=True)
        st.markdown(f'<p style="text-align: center; color: #ff8888; font-family: Rajdhani; margin: 0.5rem 0;">{explanation}</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="text-align: center; font-family: Orbitron; color: #ffffff; margin: 0.5rem 0;">Signal Strength: {tor_signal_data["strength"]} • Tor Change: {tor_signal_data["tor_change"]:+.3f}%</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("🔥 Click 'GENERATE SIGNALS' to get AI-powered trading signals")
    
    # GODZILLERS Trademark Footer
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="trademark">
    <p>🔥 GODZILLERS CRYPTO WARFARE SYSTEM 🔥</p>
    <p>© 2025 GODZILLERS CRYPTO TRACKER • PROPRIETARY AI TECHNOLOGY</p>
    <p style="font-size: 0.7rem; color: #ff6666;">FORGE YOUR FORTUNE WITH DRAGON FIRE PRECISION</p>
    </div>
    """, unsafe_allow_html=True)

def main():
    """Main function with login check"""
    # Initialize session state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = None
    
    # Check if user is logged in
    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()

if __name__ == "__main__":
    main()