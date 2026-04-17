# SMC Algorithmic Trading Specifications
## Complete Technical Reference for 15 Institutional Strategies

---

# GLOBAL FILTERS (Apply to ALL Strategies)

Before any strategy logic executes, these filters must pass:

```
GLOBAL_FILTERS:
├── Premium/Discount Zone
│   ├── Calculate dealing_range = swing_high - swing_low (on H4/Daily)
│   ├── equilibrium = swing_low + (dealing_range * 0.5)
│   ├── BUY only if: current_price < equilibrium (Discount zone)
│   └── SELL only if: current_price > equilibrium (Premium zone)
│
├── Kill Zone Timing (EST)
│   ├── London KZ: 02:00 - 05:00
│   ├── NY KZ: 07:00 - 10:00
│   ├── Silver Bullet Windows: 03:00-04:00, 10:00-11:00, 14:00-15:00
│   └── SKIP trades outside these windows
│
├── HTF Bias Confirmation
│   ├── Check Daily/H4 for Break of Structure (BOS)
│   ├── Bullish bias: Recent higher high AND higher low
│   ├── Bearish bias: Recent lower low AND lower high
│   └── Trade direction MUST align with HTF bias
│
└── Day Filter
    ├── AVOID: Monday (44% historical win rate)
    ├── PREFER: Tuesday, Wednesday, Thursday
    └── CAUTION: Friday (reduced liquidity after 12:00 EST)
```

---

# CORE STRUCTURE DEFINITIONS

## Fair Value Gap (FVG) Detection

```python
def detect_fvg(candles):
    """
    FVG forms when Candle 1's wick doesn't overlap with Candle 3's wick
    
    BULLISH FVG:
    - candle[1].high < candle[3].low
    - Gap zone: candle[1].high to candle[3].low
    
    BEARISH FVG:
    - candle[1].low > candle[3].high  
    - Gap zone: candle[3].high to candle[1].low
    """
    
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    
    # Bullish FVG
    if c1.high < c3.low:
        return {
            'type': 'bullish',
            'top': c3.low,
            'bottom': c1.high,
            'ce': (c3.low + c1.high) / 2,  # Consequent Encroachment (50% level)
            'displacement_candle': c2
        }
    
    # Bearish FVG
    if c1.low > c3.high:
        return {
            'type': 'bearish',
            'top': c1.low,
            'bottom': c3.high,
            'ce': (c1.low + c3.high) / 2,
            'displacement_candle': c2
        }
    
    return None
```

## Order Block Detection

```python
def detect_order_block(candles, direction):
    """
    BULLISH OB: Last bearish candle before bullish displacement
    BEARISH OB: Last bullish candle before bearish displacement
    
    Displacement = Move of 2+ ATR with FVG formation
    """
    
    for i in range(len(candles) - 1, 0, -1):
        current = candles[i]
        previous = candles[i-1]
        
        # Check for displacement (strong move with FVG)
        move_size = abs(current.close - previous.close)
        if move_size < 2 * atr:
            continue
            
        if direction == 'bullish':
            # Find last bearish candle before bullish move
            if current.close > current.open and previous.close < previous.open:
                return {
                    'type': 'bullish',
                    'top': previous.open,
                    'bottom': previous.low,
                    'midpoint': (previous.open + previous.low) / 2
                }
                
        if direction == 'bearish':
            # Find last bullish candle before bearish move
            if current.close < current.open and previous.close > previous.open:
                return {
                    'type': 'bearish',
                    'top': previous.high,
                    'bottom': previous.open,
                    'midpoint': (previous.high + previous.open) / 2
                }
    
    return None
```

## Market Structure Shift (MSS) / Change of Character (CHoCH)

```python
def detect_mss(candles, lookback=20):
    """
    MSS = Break of most recent swing high/low with displacement
    
    Bullish MSS: Price breaks above recent swing high after making lower low
    Bearish MSS: Price breaks below recent swing low after making higher high
    """
    
    swings = identify_swing_points(candles, lookback)
    
    # Bullish MSS
    if (candles[-1].close > swings['last_swing_high'] and 
        candles[-2].low < swings['previous_swing_low']):
        return {'type': 'bullish', 'level': swings['last_swing_high']}
    
    # Bearish MSS
    if (candles[-1].close < swings['last_swing_low'] and
        candles[-2].high > swings['previous_swing_high']):
        return {'type': 'bearish', 'level': swings['last_swing_low']}
    
    return None
```

## Liquidity Sweep Detection

```python
def detect_liquidity_sweep(candles, key_level, tolerance_pips=5):
    """
    Liquidity sweep = wick pierces level but body closes back inside
    
    Types of liquidity:
    - Equal highs/lows (EQH/EQL)
    - Previous Day High/Low (PDH/PDL)
    - Previous Week High/Low (PWH/PWL)
    - Asian Session High/Low
    """
    
    current = candles[-1]
    tolerance = tolerance_pips * pip_value
    
    # Sweep above (taking buy-side liquidity - BSL)
    if (current.high > key_level + tolerance and 
        current.close < key_level):
        return {'type': 'bsl_sweep', 'level': key_level, 'wick': current.high}
    
    # Sweep below (taking sell-side liquidity - SSL)
    if (current.low < key_level - tolerance and
        current.close > key_level):
        return {'type': 'ssl_sweep', 'level': key_level, 'wick': current.low}
    
    return None
```

---

# STRATEGY 1: THE UNICORN MODEL

## Concept
Highest-probability ICT setup. Forms when FVG overlaps precisely with a Breaker Block (failed Order Block that flipped polarity after liquidity sweep).

## Detection Algorithm

```python
class UnicornModel:
    
    def detect(self, candles_5m, candles_h1):
        """
        BULLISH UNICORN SEQUENCE:
        1. Low forms (swing low)
        2. High forms (swing high) 
        3. Lower Low forms (sweeps original low = creates Breaker Block)
        4. Higher High forms with displacement (creates FVG)
        5. FVG must OVERLAP with Breaker Block zone
        """
        
        # Step 1: Identify swing sequence
        swings = self.identify_swing_sequence(candles_h1)
        if not swings['valid_sequence']:
            return None
            
        # Step 2: Detect Breaker Block (the swept swing point zone)
        breaker = self.detect_breaker_block(candles_5m, swings)
        if not breaker:
            return None
            
        # Step 3: Detect FVG from displacement move
        fvg = detect_fvg(candles_5m[-10:])
        if not fvg:
            return None
            
        # Step 4: Check OVERLAP (critical - proximity is NOT enough)
        overlap = self.calculate_overlap(breaker, fvg)
        if overlap['percentage'] < 10:  # Minimum 10% overlap required
            return None
            
        return {
            'setup': 'unicorn',
            'direction': breaker['type'],
            'entry_zone_top': overlap['zone_top'],
            'entry_zone_bottom': overlap['zone_bottom'],
            'ce_level': overlap['ce'],  # Optimal entry at 50% of overlap
            'breaker': breaker,
            'fvg': fvg
        }
    
    def detect_breaker_block(self, candles, swings):
        """
        Breaker Block = Order Block that was invalidated by price trading through it
        Then price reversed, flipping the OB's polarity
        """
        
        # Find the Order Block at the swept swing point
        sweep_candle = self.find_sweep_candle(candles, swings['swept_level'])
        if not sweep_candle:
            return None
            
        # The OB zone is now the Breaker Block
        ob = detect_order_block(candles[:sweep_candle['index']], swings['direction'])
        if not ob:
            return None
            
        # Verify displacement away from the sweep (confirming the break)
        displacement = self.verify_displacement(candles[sweep_candle['index']:])
        if not displacement:
            return None
            
        return {
            'type': 'bullish' if swings['direction'] == 'bearish' else 'bearish',
            'top': ob['top'],
            'bottom': ob['bottom'],
            'sweep_level': swings['swept_level']
        }
    
    def calculate_overlap(self, breaker, fvg):
        """Calculate the overlapping zone between Breaker and FVG"""
        
        overlap_top = min(breaker['top'], fvg['top'])
        overlap_bottom = max(breaker['bottom'], fvg['bottom'])
        
        if overlap_bottom >= overlap_top:
            return {'percentage': 0}
            
        overlap_size = overlap_top - overlap_bottom
        breaker_size = breaker['top'] - breaker['bottom']
        
        return {
            'percentage': (overlap_size / breaker_size) * 100,
            'zone_top': overlap_top,
            'zone_bottom': overlap_bottom,
            'ce': (overlap_top + overlap_bottom) / 2
        }
```

## Entry Rules

```
ENTRY CONDITIONS:
├── All detection criteria met
├── Price retraces INTO the overlap zone
├── Current session: 10:00-11:00 AM EST (Silver Bullet) preferred
├── HTF bias (H1-H4) aligns with trade direction
├── CHoCH confirmed on entry timeframe (5M-15M)
└── Volume increased on displacement candle

ENTRY TYPE: Limit order at Consequent Encroachment (50% of overlap zone)

ENTRY TRIGGER:
├── Set limit order at overlap_ce level
├── OR wait for price to reach zone + show rejection (confirmation entry)
└── NEVER enter at the moment of MSS (wait for retracement)
```

## Stop Loss Calculation

```python
def calculate_unicorn_sl(setup, atr, direction):
    """
    SL placed beyond the Breaker Block extreme
    Add 10-20 pips buffer (or 0.5x ATR for dynamic sizing)
    """
    
    buffer = max(0.0010, atr * 0.5)  # Minimum 10 pips, or 0.5 ATR
    
    if direction == 'bullish':
        sl = setup['breaker']['bottom'] - buffer
    else:
        sl = setup['breaker']['top'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_unicorn_tp(setup, direction, candles_h1):
    """
    TP1: Nearest internal liquidity (1:2 RR minimum)
    TP2: Next external liquidity pool (1:3+ RR)
    """
    
    internal_liq = find_internal_liquidity(candles_h1, direction)
    external_liq = find_external_liquidity(candles_h1, direction)
    
    return {
        'tp1': internal_liq,  # Partial close (50%)
        'tp2': external_liq,  # Runner (remaining 50%)
        'minimum_rr': 2.0
    }
```

## Invalidation Conditions

```
INVALIDATE SETUP IF:
├── FVG does not physically OVERLAP with Breaker Block (proximity alone = invalid)
├── No prior liquidity sweep detected
├── Price closes beyond the Breaker Block extreme before entry triggers
├── HTF bias changes (new BOS against trade direction)
└── Entry does not occur within Silver Bullet window (reduced probability)
```

---

# STRATEGY 2: THE JUDAS SWING

## Concept
Exploits daily manipulation phase where smart money creates false breakout of Asian session range at London Open, then reverses aggressively in the true daily direction.

## Detection Algorithm

```python
class JudasSwing:
    
    def __init__(self):
        self.asian_session_start = time(19, 0)  # 7PM EST (previous day)
        self.asian_session_end = time(2, 0)     # 2AM EST
        self.london_open = time(2, 0)           # 2AM EST
        self.london_close = time(5, 0)          # 5AM EST
        
    def detect(self, candles_m5, daily_bias):
        """
        BULLISH JUDAS SWING:
        1. Mark NY Midnight Opening Price (00:00 EST)
        2. Mark Asian session high and low
        3. At London Open (02:00-05:00), price sweeps BELOW Asian low
        4. Price reverses with MSS
        5. Daily bias must be BULLISH
        """
        
        # Step 1: Get reference levels
        midnight_price = self.get_midnight_opening_price(candles_m5)
        asian_range = self.get_asian_session_range(candles_m5)
        
        # Step 2: Check if we're in London Kill Zone
        current_time = candles_m5[-1].time
        if not self.is_london_kz(current_time):
            return None
            
        # Step 3: Detect false breakout (the "Judas" move)
        sweep = self.detect_asian_sweep(candles_m5, asian_range, daily_bias)
        if not sweep:
            return None
            
        # Step 4: Confirm reversal with MSS
        mss = detect_mss(candles_m5[-10:])
        if not mss or mss['type'] != daily_bias:
            return None
            
        # Step 5: Find entry zone (FVG or OB from displacement)
        entry_zone = self.find_entry_zone(candles_m5, mss)
        
        return {
            'setup': 'judas_swing',
            'direction': daily_bias,
            'asian_high': asian_range['high'],
            'asian_low': asian_range['low'],
            'sweep_extreme': sweep['wick'],
            'entry_zone': entry_zone,
            'midnight_price': midnight_price
        }
    
    def get_asian_session_range(self, candles):
        """Extract high and low of Asian session"""
        
        asian_candles = [c for c in candles 
                        if self.is_asian_session(c.time)]
        
        return {
            'high': max(c.high for c in asian_candles),
            'low': min(c.low for c in asian_candles)
        }
    
    def detect_asian_sweep(self, candles, asian_range, daily_bias):
        """
        Detect false breakout of Asian range against daily bias
        """
        
        recent = candles[-20:]  # Last 100 minutes
        
        if daily_bias == 'bullish':
            # Look for sweep below Asian low (taking SSL)
            for c in recent:
                if c.low < asian_range['low'] and c.close > asian_range['low']:
                    return {'type': 'ssl_sweep', 'wick': c.low}
                    
        if daily_bias == 'bearish':
            # Look for sweep above Asian high (taking BSL)
            for c in recent:
                if c.high > asian_range['high'] and c.close < asian_range['high']:
                    return {'type': 'bsl_sweep', 'wick': c.high}
                    
        return None
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Daily bias determined (HTF analysis)
├── Asian session range marked
├── FALSE BREAKOUT detected (sweep against daily bias direction)
│   ├── Bullish day: price dips below Asian low, then reverses
│   └── Bearish day: price spikes above Asian high, then reverses
├── MSS confirmed on M1-M5
├── Current time: 02:00-05:00 AM EST (London KZ)
└── Optimal window: 02:00-03:00 AM EST (highest probability)

ENTRY TYPE: 
├── OPTION 1: Limit order at FVG created by displacement
├── OPTION 2: Limit order at Order Block from displacement
└── OPTION 3: Market entry after MSS confirmation with tight stop

CRITICAL: Never chase the false move - WAIT for MSS confirmation
```

## Stop Loss Calculation

```python
def calculate_judas_sl(setup, direction):
    """
    SL placed 10-20 pips beyond the Judas Swing extreme wick
    """
    
    buffer = 0.0015  # 15 pips default
    
    if direction == 'bullish':
        sl = setup['sweep_extreme'] - buffer
    else:
        sl = setup['sweep_extreme'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_judas_tp(setup, direction):
    """
    TP1: Opposite side of Asian range (20-30 pips typical)
    TP2: Previous Day High/Low (extended target)
    """
    
    if direction == 'bullish':
        tp1 = setup['asian_high']
        tp2 = get_previous_day_high()
    else:
        tp1 = setup['asian_low']
        tp2 = get_previous_day_low()
        
    return {
        'tp1': tp1,      # Close 50-70%
        'tp2': tp2,      # Runner
        'typical_capture': 25  # pips
    }
```

## Invalidation Conditions

```
INVALIDATE SETUP IF:
├── No false breakout detected (price just ranges)
├── MSS does not confirm within 30-60 minutes of sweep
├── Trade direction conflicts with daily bias
├── Move starts at 01:00 EST (pre-runs are less reliable)
├── Price closes beyond the sweep extreme after MSS
└── Setup forms after 03:30 AM EST (reduced probability)
```

---

# STRATEGY 3: STOP HUNT INTO FVG REVERSAL (Confirmation Model)

## Concept
The highest-confluence reversal setup requiring ALL FIVE conditions simultaneously. Missing any single element = no trade.

## The Five Mandatory Conditions

```
FIVE-CONDITION CHECKLIST (ALL REQUIRED):
│
├── 1. LIQUIDITY TAKEN
│   ├── Clear high or low swept (PDH, PDL, Equal Highs/Lows)
│   ├── Wick pierces level, body closes back inside
│   └── Visible cluster of stops at the level
│
├── 2. MARKET STRUCTURE SHIFT (MSS)
│   ├── Displacement breaks recent structural pivot
│   ├── Not just a higher high/lower low - must BREAK structure
│   └── Occurs immediately after liquidity sweep
│
├── 3. FAIR VALUE GAP PRESENT
│   ├── FVG created by the displacement candle
│   ├── Gap must be "clean" (no overlapping wicks)
│   └── Minimum size: 5 pips for EURUSD
│
├── 4. HTF BIAS ALIGNED
│   ├── Daily or H4 trend supports trade direction
│   ├── Recent BOS on HTF confirms direction
│   └── Not trading against major structure
│
└── 5. PREMIUM/DISCOUNT ALIGNMENT
    ├── BUY only if price is in DISCOUNT (below 50% of range)
    ├── SELL only if price is in PREMIUM (above 50% of range)
    └── Calculate using most recent dealing range
```

## Detection Algorithm

```python
class ConfirmationModel:
    
    def detect(self, candles_m5, candles_h4, candles_daily):
        """
        ALL five conditions must be TRUE
        """
        
        conditions = {
            'liquidity_taken': False,
            'mss_present': False,
            'fvg_present': False,
            'htf_bias_aligned': False,
            'premium_discount_aligned': False
        }
        
        # Condition 1: Liquidity Taken
        key_levels = self.get_key_liquidity_levels(candles_daily)
        for level in key_levels:
            sweep = detect_liquidity_sweep(candles_m5, level['price'])
            if sweep:
                conditions['liquidity_taken'] = True
                sweep_data = sweep
                break
                
        if not conditions['liquidity_taken']:
            return None
            
        # Condition 2: MSS Present
        mss = detect_mss(candles_m5[-15:])
        if mss:
            conditions['mss_present'] = True
            mss_data = mss
        else:
            return None
            
        # Condition 3: FVG Present (from displacement)
        fvg = detect_fvg(candles_m5[-10:])
        if fvg and fvg['type'] == mss['type']:
            conditions['fvg_present'] = True
            fvg_data = fvg
        else:
            return None
            
        # Condition 4: HTF Bias Aligned
        htf_bias = self.determine_htf_bias(candles_h4, candles_daily)
        if htf_bias == mss['type']:
            conditions['htf_bias_aligned'] = True
        else:
            return None
            
        # Condition 5: Premium/Discount Aligned
        zone = self.get_premium_discount_zone(candles_h4)
        current_price = candles_m5[-1].close
        
        if mss['type'] == 'bullish' and current_price < zone['equilibrium']:
            conditions['premium_discount_aligned'] = True
        elif mss['type'] == 'bearish' and current_price > zone['equilibrium']:
            conditions['premium_discount_aligned'] = True
        else:
            return None
            
        # ALL conditions met
        return {
            'setup': 'confirmation_model',
            'direction': mss['type'],
            'sweep': sweep_data,
            'mss': mss_data,
            'fvg': fvg_data,
            'entry_zone': {
                'top': fvg_data['top'],
                'bottom': fvg_data['bottom'],
                'ce': fvg_data['ce']
            },
            'conditions': conditions
        }
    
    def get_key_liquidity_levels(self, candles_daily):
        """
        Identify key liquidity pools:
        - Previous Day High/Low
        - Equal Highs/Lows (within 5 pips)
        - Swing Highs/Lows
        """
        
        levels = []
        
        # PDH/PDL
        yesterday = candles_daily[-2]
        levels.append({'type': 'pdh', 'price': yesterday.high})
        levels.append({'type': 'pdl', 'price': yesterday.low})
        
        # Equal Highs/Lows
        eqh_eql = self.find_equal_highs_lows(candles_daily)
        levels.extend(eqh_eql)
        
        # Swing points
        swings = identify_swing_points(candles_daily, 10)
        levels.extend(swings)
        
        return levels
```

## Entry Rules

```
ENTRY CONDITIONS:
├── All five conditions verified TRUE
├── Current session: London or NY Kill Zone
├── Trade direction matches MSS direction
└── FVG has not been fully filled (CE still valid)

ENTRY TYPE: Limit order at FVG boundary OR Consequent Encroachment (50%)

ENTRY PLACEMENT:
├── Conservative: FVG boundary (higher fill rate, lower RR)
├── Optimal: FVG CE (50% level) - best balance
└── Aggressive: FVG far edge (lower fill rate, higher RR)

NEWS FILTER: Major news events often serve as sweep catalysts
├── High-impact news = potential setup
└── Enter AFTER the sweep, not during news
```

## Stop Loss Calculation

```python
def calculate_confirmation_sl(setup, atr):
    """
    SL beyond the swept wick + volatility buffer
    Buffer: 0.5x to 1.0x ATR
    """
    
    buffer = atr * 0.75  # Default 0.75 ATR
    
    if setup['direction'] == 'bullish':
        sl = setup['sweep']['wick'] - buffer
    else:
        sl = setup['sweep']['wick'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_confirmation_tp(setup, entry_price, sl_price, candles_h4):
    """
    TP1: 1:2 RR at next structural level
    TP2: Opposing liquidity pool (1:3 to 1:5 achievable)
    """
    
    risk = abs(entry_price - sl_price)
    
    # TP1: Fixed 1:2 RR
    if setup['direction'] == 'bullish':
        tp1 = entry_price + (risk * 2)
    else:
        tp1 = entry_price - (risk * 2)
        
    # TP2: Opposing liquidity
    opposing_liquidity = find_opposing_liquidity(candles_h4, setup['direction'])
    tp2 = opposing_liquidity['level']
    
    return {
        'tp1': tp1,
        'tp2': tp2,
        'tp1_allocation': 0.5,  # 50% at TP1
        'tp2_allocation': 0.5   # 50% runner
    }
```

## Critical Distinction: Reversal vs Continuation

```python
def classify_trade_type(sweep, mss_present, momentum_continuing):
    """
    REVERSAL: Sweep + MSS present → trade the reversal
    CONTINUATION: Sweep + NO MSS + momentum continues → do NOT fade
    """
    
    if sweep and mss_present:
        return 'reversal_trade'
    elif sweep and not mss_present and momentum_continuing:
        return 'do_not_trade'  # Continuation, don't fade
    else:
        return 'wait'  # Incomplete setup
```

---

# STRATEGY 4: ICT SILVER BULLET

## Concept
Time-based algorithmic model targeting three specific 1-hour windows where institutional algorithms are most active. One of the most consistently backtested ICT strategies.

## The Three Windows (EST)

```
SILVER BULLET WINDOWS:
│
├── WINDOW 1: London Silver Bullet
│   ├── Time: 03:00 - 04:00 AM EST
│   ├── Character: London session momentum
│   └── Priority: Medium
│
├── WINDOW 2: NY AM Silver Bullet (HIGHEST PROBABILITY)
│   ├── Time: 10:00 - 11:00 AM EST
│   ├── Character: London/NY overlap, maximum liquidity
│   └── Priority: HIGH - Best window for EURUSD
│
└── WINDOW 3: NY PM Silver Bullet
    ├── Time: 14:00 - 15:00 PM EST
    ├── Character: NY afternoon session
    └── Priority: Medium-Low
```

## Detection Algorithm

```python
class SilverBullet:
    
    def __init__(self):
        self.windows = [
            {'start': time(3, 0), 'end': time(4, 0), 'name': 'london'},
            {'start': time(10, 0), 'end': time(11, 0), 'name': 'ny_am'},  # Best
            {'start': time(14, 0), 'end': time(15, 0), 'name': 'ny_pm'}
        ]
        
    def detect(self, candles_m5, candles_m15, daily_bias):
        """
        SILVER BULLET SEQUENCE:
        1. Must be within one of three windows
        2. Mark BSL (highs) and SSL (lows) on 15M
        3. Wait for price to sweep one side within the window
        4. Confirm MSS on 1M-5M
        5. Identify FVG behind MSS
        6. Enter when price retraces to FVG
        """
        
        current_time = candles_m5[-1].time
        
        # Step 1: Verify we're in a Silver Bullet window
        active_window = self.get_active_window(current_time)
        if not active_window:
            return None
            
        # Step 2: Mark liquidity levels on 15M
        liquidity = self.mark_session_liquidity(candles_m15)
        
        # Step 3: Detect sweep within the window
        sweep = self.detect_window_sweep(candles_m5, liquidity, active_window)
        if not sweep:
            return None
            
        # Step 4: Confirm MSS
        mss = detect_mss(candles_m5[-10:])
        if not mss:
            return None
            
        # Step 5: Identify FVG
        fvg = detect_fvg(candles_m5[-8:])
        if not fvg or fvg['type'] != mss['type']:
            return None
            
        # Step 6: Verify alignment with daily bias
        if mss['type'] != daily_bias:
            return None  # Must trade with daily bias
            
        # Step 7: Check minimum target distance (15 pips)
        target_liquidity = self.get_target_liquidity(candles_m15, mss['type'])
        distance_to_target = abs(candles_m5[-1].close - target_liquidity)
        if distance_to_target < 0.0015:  # Less than 15 pips
            return None
            
        return {
            'setup': 'silver_bullet',
            'window': active_window['name'],
            'direction': mss['type'],
            'sweep': sweep,
            'mss': mss,
            'fvg': fvg,
            'entry_zone': fvg,
            'target_liquidity': target_liquidity
        }
    
    def get_active_window(self, current_time):
        """Check if current time is within any Silver Bullet window"""
        
        for window in self.windows:
            if window['start'] <= current_time <= window['end']:
                return window
        return None
    
    def mark_session_liquidity(self, candles_m15):
        """
        Mark BSL (buy-side liquidity = highs) and SSL (sell-side = lows)
        """
        
        session_candles = self.get_current_session_candles(candles_m15)
        
        return {
            'bsl': max(c.high for c in session_candles),  # Highs to sweep
            'ssl': min(c.low for c in session_candles)    # Lows to sweep
        }
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Currently within one of three Silver Bullet windows
├── Price sweeps BSL or SSL within the window
├── MSS confirms on M1-M5 after sweep
├── FVG forms behind the MSS
├── Daily bias supports trade direction
└── Minimum 15-pip distance from entry to target liquidity

ENTRY TYPE: Limit order at FVG

ENTRY TIMING:
├── Both SETUP and ENTRY must occur within the 1-hour window
├── Trade CAN be held beyond the window
└── 10:00-11:00 AM window = highest probability (London/NY overlap)
```

## Stop Loss Options

```python
def calculate_silver_bullet_sl(setup, method='conservative'):
    """
    Two SL methods with different characteristics:
    
    METHOD 1 (Conservative): Beyond sweep extreme
    - Wider stop
    - Higher win rate
    - Lower RR
    
    METHOD 2 (Aggressive): Beyond FVG boundary
    - Tighter stop  
    - Lower win rate
    - Higher RR
    """
    
    if method == 'conservative':
        if setup['direction'] == 'bullish':
            sl = setup['sweep']['wick'] - 0.0010  # 10 pip buffer
        else:
            sl = setup['sweep']['wick'] + 0.0010
            
    elif method == 'aggressive':
        if setup['direction'] == 'bullish':
            sl = setup['fvg']['bottom'] - 0.0005  # 5 pip buffer
        else:
            sl = setup['fvg']['top'] + 0.0005
            
    return sl
```

## Take Profit Targets

```python
def calculate_silver_bullet_tp(setup):
    """
    Target: Next liquidity pool
    Typical capture: 15-40 pips on EURUSD
    Minimum: 1:2 RR
    """
    
    target = setup['target_liquidity']
    
    return {
        'tp': target,
        'typical_pips': (15, 40),
        'minimum_rr': 2.0
    }
```

---

# STRATEGY 5: NESTED FVGs / FVG STACKING

## Concept
When 3+ consecutive FVGs form in a single displacement leg, it signals extreme institutional urgency with no deep retracement expected. Captures runaway momentum.

## Detection Algorithm

```python
class NestedFVGs:
    
    def detect(self, candles_m5, candles_h1, htf_bias):
        """
        NESTED FVG SEQUENCE:
        1. Strong displacement creates 3+ consecutive FVGs
        2. Classify: First = Breakaway Gap, subsequent = Measuring Gaps
        3. Entry at CE (50%) of most recent FVG
        4. Do NOT use OTE (0.618-0.786) - retracements are shallow
        """
        
        # Step 1: Identify displacement move
        displacement = self.detect_strong_displacement(candles_m5)
        if not displacement:
            return None
            
        # Step 2: Count consecutive FVGs
        fvgs = self.find_all_fvgs_in_leg(candles_m5, displacement)
        
        if len(fvgs) < 3:
            return None  # Need minimum 3 FVGs
            
        # Step 3: Classify FVGs
        classified_fvgs = self.classify_fvgs(fvgs)
        
        # Step 4: Verify HTF alignment
        if classified_fvgs[0]['type'] != htf_bias:
            return None
            
        return {
            'setup': 'nested_fvgs',
            'direction': classified_fvgs[0]['type'],
            'fvg_count': len(fvgs),
            'breakaway_gap': classified_fvgs[0],  # Most important
            'measuring_gaps': classified_fvgs[1:],
            'entry_fvg': classified_fvgs[-1],  # Enter at most recent
            'entry_zone': {
                'top': classified_fvgs[-1]['top'],
                'bottom': classified_fvgs[-1]['bottom'],
                'ce': classified_fvgs[-1]['ce']  # Optimal entry
            }
        }
    
    def detect_strong_displacement(self, candles, min_consecutive=5):
        """
        Strong displacement = 5+ consecutive candles in same direction
        with increasing or sustained momentum
        """
        
        consecutive = 0
        direction = None
        start_index = None
        
        for i, candle in enumerate(candles):
            is_bullish = candle.close > candle.open
            
            if direction is None:
                direction = 'bullish' if is_bullish else 'bearish'
                start_index = i
                consecutive = 1
            elif (direction == 'bullish' and is_bullish) or \
                 (direction == 'bearish' and not is_bullish):
                consecutive += 1
            else:
                if consecutive >= min_consecutive:
                    return {
                        'direction': direction,
                        'start_index': start_index,
                        'end_index': i - 1,
                        'candle_count': consecutive
                    }
                direction = 'bullish' if is_bullish else 'bearish'
                start_index = i
                consecutive = 1
                
        return None
    
    def find_all_fvgs_in_leg(self, candles, displacement):
        """Find all FVGs within the displacement leg"""
        
        fvgs = []
        leg_candles = candles[displacement['start_index']:displacement['end_index']+1]
        
        for i in range(2, len(leg_candles)):
            subset = leg_candles[i-2:i+1]
            fvg = detect_fvg(subset)
            if fvg:
                fvgs.append(fvg)
                
        return fvgs
    
    def classify_fvgs(self, fvgs):
        """
        Breakaway Gap: First FVG (most important, invalidation point)
        Measuring Gaps: Subsequent FVGs
        """
        
        classified = []
        for i, fvg in enumerate(fvgs):
            fvg_copy = fvg.copy()
            fvg_copy['classification'] = 'breakaway' if i == 0 else 'measuring'
            classified.append(fvg_copy)
            
        return classified
```

## Entry Rules

```
ENTRY CONDITIONS:
├── 3+ consecutive FVGs detected in single displacement leg
├── Current session: London or NY Kill Zone (Asian stacks lack volume)
├── HTF bias (H1-H4) aligns with stack direction
├── Multi-timeframe alignment: 15M FVG inside H4 FVG (stronger)
└── Entry at CE (50%) of MOST RECENT FVG

CRITICAL: Do NOT use standard OTE (0.618-0.786) for entry
├── Market rarely retraces that deep during stacking
└── Shallow retracements only - CE of each gap

PYRAMIDING STRATEGY:
├── Initial entry: 1% risk at first FVG CE retest
├── Add 0.5-1% at each new Measuring Gap CE
└── Trail stops behind invalidation FVGs
```

## Stop Loss Calculation

```python
def calculate_nested_fvg_sl(setup, direction):
    """
    Initial SL: Beyond far edge of most recent FVG
    Trailing: Move SL behind each 'invalidation FVG' as price advances
    """
    
    entry_fvg = setup['entry_fvg']
    buffer = 0.0005  # 5 pips
    
    if direction == 'bullish':
        initial_sl = entry_fvg['bottom'] - buffer
    else:
        initial_sl = entry_fvg['top'] + buffer
        
    return {
        'initial_sl': initial_sl,
        'trail_method': 'behind_each_fvg'
    }

def trail_nested_fvg_sl(current_sl, new_fvg, direction):
    """Update trailing stop as new FVGs form"""
    
    if direction == 'bullish':
        new_sl = new_fvg['bottom'] - 0.0005
        return max(current_sl, new_sl)  # Only move up
    else:
        new_sl = new_fvg['top'] + 0.0005
        return min(current_sl, new_sl)  # Only move down
```

## Take Profit Targets

```python
def calculate_nested_fvg_tp(setup, candles_h4, direction):
    """
    Target: Next external liquidity or opposite-side HTF FVG
    RR achievable: 1:2 to 1:5
    """
    
    external_liq = find_external_liquidity(candles_h4, direction)
    htf_fvg = find_opposing_htf_fvg(candles_h4, direction)
    
    return {
        'tp1': external_liq,
        'tp2': htf_fvg['ce'] if htf_fvg else None,
        'expected_rr': (2.0, 5.0)
    }
```

## Invalidation Conditions

```
INVALIDATE SETUP IF:
├── Breakaway Gap (first FVG) gets FULLY FILLED
│   └── This invalidates the entire momentum thesis
├── Price closes beyond the Breakaway Gap's far edge
├── Session changes to Asian (volume drops)
└── HTF structure changes against trade direction
```

---

# STRATEGY 6: INVERSE FVG (iFVG) POLARITY FLIP

## Concept
When an FVG is completely breached (candle body closes through entire gap), it "inverts" - former support becomes resistance and vice versa. Signals fundamental shift in institutional commitment.

## Detection Algorithm

```python
class InverseFVG:
    
    def detect(self, candles_m5, candles_m15):
        """
        iFVG SEQUENCE:
        1. Liquidity sweep at key level
        2. FVG forms on 1M-5M
        3. FVG gets BROKEN (candle body closes through entire gap)
        4. This creates the Inverse FVG (polarity flipped)
        5. Wait for retest of iFVG zone
        6. Enter on retest with SMT Divergence confirmation
        """
        
        # Step 1: Detect liquidity sweep
        key_levels = self.get_key_levels(candles_m15)
        sweep = None
        for level in key_levels:
            sweep = detect_liquidity_sweep(candles_m5, level)
            if sweep:
                break
                
        if not sweep:
            return None
            
        # Step 2: Find FVG that formed after sweep
        fvg = detect_fvg(candles_m5[-15:])
        if not fvg:
            return None
            
        # Step 3: Detect FVG breach (creates iFVG)
        ifvg = self.detect_fvg_breach(candles_m5, fvg)
        if not ifvg:
            return None
            
        # Step 4: Verify with SMT Divergence (strongest filter)
        smt = self.check_smt_divergence(candles_m5)
        
        return {
            'setup': 'inverse_fvg',
            'direction': ifvg['new_direction'],
            'original_fvg': fvg,
            'ifvg': ifvg,
            'entry_zone': {
                'top': ifvg['top'],
                'bottom': ifvg['bottom'],
                'ce': (ifvg['top'] + ifvg['bottom']) / 2
            },
            'sweep': sweep,
            'smt_confirmed': smt is not None
        }
    
    def detect_fvg_breach(self, candles, original_fvg):
        """
        iFVG creation requires:
        - Candle BODY (not just wick) closes through ENTIRE gap
        - Simple wick through does NOT count
        """
        
        for i, candle in enumerate(candles[-10:]):
            body_high = max(candle.open, candle.close)
            body_low = min(candle.open, candle.close)
            
            if original_fvg['type'] == 'bullish':
                # Bearish breach: body closes below entire bullish FVG
                if body_high < original_fvg['bottom']:
                    return {
                        'created': True,
                        'new_direction': 'bearish',
                        'top': original_fvg['top'],
                        'bottom': original_fvg['bottom'],
                        'breach_candle': candle
                    }
                    
            elif original_fvg['type'] == 'bearish':
                # Bullish breach: body closes above entire bearish FVG
                if body_low > original_fvg['top']:
                    return {
                        'created': True,
                        'new_direction': 'bullish',
                        'top': original_fvg['top'],
                        'bottom': original_fvg['bottom'],
                        'breach_candle': candle
                    }
                    
        return None
    
    def check_smt_divergence(self, eurusd_candles):
        """
        SMT Divergence: EURUSD vs GBPUSD diverging at key levels
        - EURUSD makes lower low, GBPUSD makes higher low = bullish divergence
        - EURUSD makes higher high, GBPUSD makes lower high = bearish divergence
        """
        
        gbpusd_candles = get_correlated_pair_candles('GBPUSD')
        
        eurusd_swing = identify_swing_points(eurusd_candles, 5)
        gbpusd_swing = identify_swing_points(gbpusd_candles, 5)
        
        # Bullish SMT: EU lower low, GU higher low
        if (eurusd_swing['last_low'] < eurusd_swing['prev_low'] and
            gbpusd_swing['last_low'] > gbpusd_swing['prev_low']):
            return {'type': 'bullish', 'strength': 'strong'}
            
        # Bearish SMT: EU higher high, GU lower high
        if (eurusd_swing['last_high'] > eurusd_swing['prev_high'] and
            gbpusd_swing['last_high'] < gbpusd_swing['prev_high']):
            return {'type': 'bearish', 'strength': 'strong'}
            
        return None
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Liquidity sweep at key level detected
├── Original FVG formed then BREACHED (body closes through)
├── Breach creates polarity flip (iFVG)
├── Price retraces back to iFVG zone
├── SMT Divergence confirms (EURUSD vs GBPUSD)
├── Premium/Discount alignment
└── Current session: NY (9:30 AM EST onward)

ENTRY TYPE: Limit order at iFVG zone (boundary or CE)

CRITICAL DISTINCTION:
├── Simple WICK through FVG = NOT an iFVG
├── Candle BODY must CLOSE through entire gap
└── Multiple stacked FVGs = uncertainty, avoid or zoom out
```

## Stop Loss Calculation

```python
def calculate_ifvg_sl(setup, direction):
    """
    SL beyond iFVG zone OR beyond the sweep swing
    """
    
    buffer = 0.0010  # 10 pips
    
    # Option 1: Beyond iFVG zone
    if direction == 'bullish':
        sl_option1 = setup['ifvg']['bottom'] - buffer
    else:
        sl_option1 = setup['ifvg']['top'] + buffer
        
    # Option 2: Beyond sweep swing
    sl_option2 = setup['sweep']['wick']
    if direction == 'bullish':
        sl_option2 -= buffer
    else:
        sl_option2 += buffer
        
    # Use wider of the two for safety
    if direction == 'bullish':
        return min(sl_option1, sl_option2)
    else:
        return max(sl_option1, sl_option2)
```

## Take Profit Targets

```python
def calculate_ifvg_tp(setup, candles_h1, direction):
    """
    TP1: Internal liquidity (1:2 RR)
    TP2: Major swing high/low (1:3+)
    """
    
    internal_liq = find_internal_liquidity(candles_h1, direction)
    major_swing = find_major_swing(candles_h1, direction)
    
    return {
        'tp1': internal_liq,      # Close 50%
        'tp2': major_swing,       # Runner
        'minimum_rr': 2.0
    }
```

---

# STRATEGY 7: OTE + FVG CONFLUENCE

## Concept
Optimal Trade Entry zone (0.618-0.786 Fibonacci) combined with FVG inside that band creates geometrically precise entry. The 0.705 level is the "sweet spot."

## Detection Algorithm

```python
class OTEwithFVG:
    
    def __init__(self):
        self.ote_start = 0.618
        self.ote_end = 0.786
        self.ote_sweet_spot = 0.705
        
    def detect(self, candles_m15, candles_h4):
        """
        OTE + FVG SEQUENCE:
        1. Identify clear impulse leg
        2. Draw Fibonacci retracement (body-to-body for accuracy)
        3. Mark OTE zone (0.618-0.786)
        4. Locate FVG that overlaps with OTE zone
        5. Prior liquidity sweep must have occurred
        6. Enter on rejection at FVG within OTE
        """
        
        # Step 1: Identify impulse leg
        impulse = self.identify_impulse_leg(candles_h4)
        if not impulse:
            return None
            
        # Step 2: Calculate Fibonacci (body-to-body)
        fib_levels = self.calculate_fib_levels(impulse)
        
        # Step 3: Define OTE zone
        ote_zone = {
            'top': fib_levels[0.618],
            'bottom': fib_levels[0.786],
            'sweet_spot': fib_levels[0.705]
        }
        
        # Step 4: Find FVG within OTE
        fvg = self.find_fvg_in_ote(candles_m15, ote_zone, impulse['direction'])
        if not fvg:
            return None
            
        # Step 5: Verify prior liquidity sweep
        sweep = self.detect_prior_sweep(candles_h4, impulse)
        if not sweep:
            return None
            
        return {
            'setup': 'ote_fvg',
            'direction': impulse['direction'],
            'impulse': impulse,
            'fib_levels': fib_levels,
            'ote_zone': ote_zone,
            'fvg': fvg,
            'entry_zone': {
                'top': fvg['top'],
                'bottom': fvg['bottom'],
                'optimal': fib_levels[0.705]  # Sweet spot
            },
            'sweep': sweep
        }
    
    def identify_impulse_leg(self, candles):
        """
        Impulse = Strong directional move with displacement
        Minimum: 3x ATR move
        """
        
        atr = calculate_atr(candles, 14)
        
        for i in range(len(candles) - 1, 10, -1):
            leg_high = max(c.high for c in candles[i-10:i])
            leg_low = min(c.low for c in candles[i-10:i])
            leg_size = leg_high - leg_low
            
            if leg_size >= 3 * atr:
                direction = 'bullish' if candles[i-1].close > candles[i-10].close else 'bearish'
                return {
                    'direction': direction,
                    'swing_high': leg_high,
                    'swing_low': leg_low,
                    'start_index': i - 10,
                    'end_index': i
                }
                
        return None
    
    def calculate_fib_levels(self, impulse):
        """
        Calculate Fib using BODY-TO-BODY (ignoring wicks)
        More accurate than wick-to-wick
        """
        
        if impulse['direction'] == 'bullish':
            # For bullish: measure from low body to high body
            range_size = impulse['swing_high'] - impulse['swing_low']
            return {
                0.0: impulse['swing_high'],
                0.236: impulse['swing_high'] - (range_size * 0.236),
                0.382: impulse['swing_high'] - (range_size * 0.382),
                0.5: impulse['swing_high'] - (range_size * 0.5),
                0.618: impulse['swing_high'] - (range_size * 0.618),
                0.705: impulse['swing_high'] - (range_size * 0.705),  # Sweet spot
                0.786: impulse['swing_high'] - (range_size * 0.786),
                1.0: impulse['swing_low'],
                -0.27: impulse['swing_high'] + (range_size * 0.27),   # Extension
                -0.62: impulse['swing_high'] + (range_size * 0.62)    # Extension
            }
        else:
            range_size = impulse['swing_high'] - impulse['swing_low']
            return {
                0.0: impulse['swing_low'],
                0.236: impulse['swing_low'] + (range_size * 0.236),
                0.382: impulse['swing_low'] + (range_size * 0.382),
                0.5: impulse['swing_low'] + (range_size * 0.5),
                0.618: impulse['swing_low'] + (range_size * 0.618),
                0.705: impulse['swing_low'] + (range_size * 0.705),
                0.786: impulse['swing_low'] + (range_size * 0.786),
                1.0: impulse['swing_high'],
                -0.27: impulse['swing_low'] - (range_size * 0.27),
                -0.62: impulse['swing_low'] - (range_size * 0.62)
            }
    
    def find_fvg_in_ote(self, candles, ote_zone, direction):
        """
        FVG must sit INSIDE the OTE band (0.618-0.786)
        Proximity is not enough
        """
        
        fvgs = []
        for i in range(2, len(candles)):
            fvg = detect_fvg(candles[i-2:i+1])
            if fvg and fvg['type'] == direction:
                fvgs.append(fvg)
                
        # Find FVG that overlaps with OTE zone
        for fvg in fvgs:
            if self.fvg_overlaps_ote(fvg, ote_zone):
                return fvg
                
        return None
    
    def fvg_overlaps_ote(self, fvg, ote_zone):
        """Check if FVG has any overlap with OTE zone"""
        
        overlap_top = min(fvg['top'], ote_zone['top'])
        overlap_bottom = max(fvg['bottom'], ote_zone['bottom'])
        
        return overlap_bottom < overlap_top
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Clear impulse leg identified
├── Fibonacci drawn body-to-body
├── FVG sits INSIDE OTE band (0.618-0.786)
├── Prior liquidity sweep confirmed
├── Current session: NY Kill Zone 8:30-11:00 AM EST
└── Order Block overlap adds probability (optional)

ENTRY TYPE: 
├── Wait for price to reach FVG within OTE
├── Enter on sharp REJECTION + follow-through
├── Do NOT enter on first touch alone
└── Optimal entry: 0.705 Fibonacci level

CRITICAL: OTE alone is NOT an entry model
├── OTE without FVG/OB = "just waiting"
└── Never trade OTE without entry model confluence
```

## Stop Loss Calculation

```python
def calculate_ote_fvg_sl(setup, direction):
    """
    SL 10-20 pips beyond swing extreme
    OR below 100% Fibonacci level
    """
    
    fib_100 = setup['fib_levels'][1.0]
    buffer = 0.0015  # 15 pips
    
    if direction == 'bullish':
        sl = min(setup['impulse']['swing_low'], fib_100) - buffer
    else:
        sl = max(setup['impulse']['swing_high'], fib_100) + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_ote_fvg_tp(setup, direction):
    """
    TP1: Previous swing high/low (0% Fib level)
    TP2: -0.27 or -0.62 Fibonacci extension
    """
    
    fib = setup['fib_levels']
    
    return {
        'tp1': fib[0.0],        # Previous extreme
        'tp2': fib[-0.27],      # First extension
        'tp3': fib[-0.62],      # Second extension (ambitious)
        'expected_rr': (2.0, 3.0)
    }
```

---

# STRATEGY 8: REJECTION BLOCK AT LAST-DEFENSE LEVELS

## Concept
Forms at 80-90% Fibonacci retracement - the deepest PD Array and market's "last line of defense." Offers the tightest stops of any PD Array.

## Detection Algorithm

```python
class RejectionBlock:
    
    def detect(self, candles_h1, candles_daily):
        """
        REJECTION BLOCK CRITERIA:
        1. Long wicks at swing highs/lows after liquidity sweep
        2. Wick must be 2-3x the candle body size
        3. Forms at 80-90% Fibonacci retracement
        4. Must occur at genuine HTF key levels
        5. Requires MSS/CHoCH confirmation
        """
        
        # Step 1: Identify potential rejection candles
        rejection_candles = self.find_rejection_candles(candles_h1)
        if not rejection_candles:
            return None
            
        # Step 2: Verify at key level
        key_levels = self.get_htf_key_levels(candles_daily)
        valid_rejections = []
        
        for rc in rejection_candles:
            for level in key_levels:
                if self.candle_at_level(rc, level):
                    valid_rejections.append({
                        'candle': rc,
                        'level': level
                    })
                    
        if not valid_rejections:
            return None
            
        # Step 3: Verify 80-90% Fib retracement zone
        rejection = valid_rejections[0]
        in_deep_zone = self.verify_deep_retracement(rejection, candles_h1)
        if not in_deep_zone:
            return None
            
        # Step 4: Confirm MSS/CHoCH
        mss = detect_mss(candles_h1[-10:])
        if not mss:
            return None
            
        # Step 5: Build rejection block zone
        rb_zone = self.define_rejection_block(rejection)
        
        return {
            'setup': 'rejection_block',
            'direction': mss['type'],
            'rejection_candle': rejection['candle'],
            'key_level': rejection['level'],
            'entry_zone': rb_zone,
            'mss': mss
        }
    
    def find_rejection_candles(self, candles):
        """
        Rejection candle criteria:
        - Wick at least 2-3x the body size
        - At swing high or swing low
        """
        
        rejections = []
        
        for i, candle in enumerate(candles[-50:]):
            body = abs(candle.close - candle.open)
            upper_wick = candle.high - max(candle.open, candle.close)
            lower_wick = min(candle.open, candle.close) - candle.low
            
            # Bullish rejection (long lower wick)
            if lower_wick >= 2 * body and lower_wick >= upper_wick * 2:
                rejections.append({
                    'type': 'bullish',
                    'candle': candle,
                    'index': i,
                    'wick': lower_wick,
                    'body': body
                })
                
            # Bearish rejection (long upper wick)
            if upper_wick >= 2 * body and upper_wick >= lower_wick * 2:
                rejections.append({
                    'type': 'bearish',
                    'candle': candle,
                    'index': i,
                    'wick': upper_wick,
                    'body': body
                })
                
        return rejections
    
    def define_rejection_block(self, rejection):
        """
        For bullish: RB zone is from low of candle to the body low
        For bearish: RB zone is from high of candle to the body high
        """
        
        candle = rejection['candle']
        
        if rejection['candle']['type'] == 'bullish':
            return {
                'top': min(candle.open, candle.close),  # Body low
                'bottom': candle.low,  # Wick low
                'entry_trigger': min(candle.open, candle.close)  # Enter when price reaches below body
            }
        else:
            return {
                'top': candle.high,  # Wick high
                'bottom': max(candle.open, candle.close),  # Body high
                'entry_trigger': max(candle.open, candle.close)
            }
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Rejection candle with wick 2-3x body size
├── Forms at genuine HTF key level
├── Located in 80-90% Fibonacci retracement zone
├── MSS/CHoCH confirmed on LTF
├── Displacement with FVG follows rejection
├── Current session: London or NY Kill Zone
└── HTF timeframe (H1-Daily) for identification

ENTRY TRIGGER (Bullish):
├── Wait for price to reach BELOW the body of rejection candle
├── Execute buy when price touches below body level
└── This provides optimal entry with tightest stop

THE 50% BODY PENETRATION RULE:
├── If RB body is >50% penetrated by closing candle → setup FAILS (~90% of time)
├── If body does NOT close above 50% → setup WORKS (~90% of time)
└── This is the key validation rule

HTF vs LTF WICK COUNT:
├── HTF (H1-Daily): Only 1 wick needed for validation
└── LTF (M15 and below): Need at least 2 wicks for validation
```

## Stop Loss Calculation

```python
def calculate_rejection_block_sl(setup, direction):
    """
    Tightest stops of all PD Arrays
    SL 10-20 pips beyond rejection block extreme
    """
    
    buffer = 0.0010  # 10 pips (tighter than other setups)
    
    if direction == 'bullish':
        sl = setup['entry_zone']['bottom'] - buffer
    else:
        sl = setup['entry_zone']['top'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_rejection_block_tp(setup, candles_h4, direction):
    """
    Target: Opposing liquidity pool
    Superior RR due to tight stops
    """
    
    opposing_liq = find_opposing_liquidity(candles_h4, direction)
    
    return {
        'tp': opposing_liq,
        'expected_rr': (3.0, 5.0)  # High RR due to tight stops
    }
```

## Invalidation Conditions

```
INVALIDATE SETUP IF:
├── Rejection block body >50% penetrated by closing candle
├── News-event candles with long wicks (NOT rejection blocks - just volatility)
├── Not at genuine HTF key level
├── MSS/CHoCH does not confirm
└── LTF only shows 1 wick (need 2+ for LTF validation)
```

---

# STRATEGY 9: ICT MARKET MAKER MODEL (MMM)

## Concept
Maps the entire institutional price delivery cycle across four phases. Most comprehensive ICT framework, operating fractally from intraday to weekly scales.

## The Four Phases

```
MARKET MAKER BUY MODEL (MMBM):
│
├── PHASE 1: ORIGINAL CONSOLIDATION
│   ├── Price ranges, building SSL below
│   ├── Retail traders placing stops below lows
│   └── Duration: Days to weeks
│
├── PHASE 2: SELL PROGRAM (Smart Money Reversal prep)
│   ├── Price creates lower highs
│   ├── Appears bearish to retail
│   ├── Actually engineered liquidity
│   └── Building sellside liquidity (SSL)
│
├── PHASE 3: SMART MONEY REVERSAL
│   ├── Price reaches HTF Discount PD Array
│   ├── MSS occurs (this is THE entry point)
│   ├── FVG forms on reversal
│   └── Enter on FVG retracement
│
└── PHASE 4: BUY PROGRAM (Distribution)
    ├── Price moves toward original consolidation
    ├── Creates higher lows
    ├── Targets engineered liquidity highs
    └── Model completion

MARKET MAKER SELL MODEL (MMSM):
└── Inverse of above (BSL engineered above, etc.)
```

## Detection Algorithm

```python
class MarketMakerModel:
    
    def detect(self, candles_h4, candles_daily):
        """
        Detect current phase and entry opportunities
        Focus on Phase 3 (Smart Money Reversal) for entries
        """
        
        # Step 1: Identify original consolidation zone
        consolidation = self.find_consolidation(candles_daily, lookback=50)
        if not consolidation:
            return None
            
        # Step 2: Detect engineered liquidity
        liquidity = self.detect_engineered_liquidity(candles_daily, consolidation)
        
        # Step 3: Determine current phase
        phase = self.identify_current_phase(candles_h4, consolidation, liquidity)
        
        # Step 4: If in Phase 3, look for entry
        if phase['number'] == 3:
            entry = self.find_reversal_entry(candles_h4, phase)
            if entry:
                return {
                    'setup': 'market_maker_model',
                    'model_type': 'buy' if phase['direction'] == 'bullish' else 'sell',
                    'phase': phase,
                    'consolidation': consolidation,
                    'liquidity': liquidity,
                    'entry': entry
                }
                
        return None
    
    def find_consolidation(self, candles, lookback):
        """
        Original consolidation = range where SSL/BSL is being engineered
        Tight range with multiple touches of boundaries
        """
        
        for i in range(len(candles) - lookback, len(candles) - 10):
            window = candles[i:i+20]
            high = max(c.high for c in window)
            low = min(c.low for c in window)
            range_size = high - low
            
            # Count touches of range boundaries
            high_touches = sum(1 for c in window if c.high > high - range_size * 0.1)
            low_touches = sum(1 for c in window if c.low < low + range_size * 0.1)
            
            if high_touches >= 3 and low_touches >= 3:
                return {
                    'high': high,
                    'low': low,
                    'range_size': range_size,
                    'start_index': i
                }
                
        return None
    
    def identify_current_phase(self, candles, consolidation, liquidity):
        """
        Determine which of the 4 phases we're in
        """
        
        current_price = candles[-1].close
        
        # Phase 2: Sell Program (moving away from consolidation toward discount)
        if current_price < consolidation['low']:
            # Check for lower highs (characteristic of sell program)
            swings = identify_swing_points(candles[-20:], 5)
            if swings['last_high'] < swings['prev_high']:
                return {
                    'number': 2,
                    'name': 'sell_program',
                    'direction': 'bullish'  # Eventual direction
                }
                
        # Phase 3: Smart Money Reversal
        # Look for MSS at discount PD Array
        discount_zone = consolidation['low'] - consolidation['range_size'] * 0.5
        if current_price < discount_zone:
            mss = detect_mss(candles[-10:])
            if mss and mss['type'] == 'bullish':
                return {
                    'number': 3,
                    'name': 'smart_money_reversal',
                    'direction': 'bullish',
                    'mss': mss
                }
                
        # Phase 4: Buy Program
        if current_price > consolidation['low']:
            swings = identify_swing_points(candles[-20:], 5)
            if swings['last_low'] > swings['prev_low']:
                return {
                    'number': 4,
                    'name': 'buy_program',
                    'direction': 'bullish'
                }
                
        # Phase 1: Still in consolidation
        return {
            'number': 1,
            'name': 'consolidation',
            'direction': None
        }
    
    def find_reversal_entry(self, candles, phase):
        """
        Entry during Phase 3 (Smart Money Reversal)
        Enter on FVG retracement after MSS
        """
        
        fvg = detect_fvg(candles[-10:])
        if fvg and fvg['type'] == phase['direction']:
            return {
                'entry_zone': fvg,
                'mss_level': phase['mss']['level']
            }
            
        return None
```

## Entry Rules

```
ENTRY CONDITIONS:
├── All four phases correctly identified
├── Currently in PHASE 3 (Smart Money Reversal)
├── MSS confirmed at HTF Discount/Premium PD Array
├── FVG forms after MSS
├── Enter on FVG retracement
├── Trading on the "right side" of the curve
└── Current session: London (2-5 AM EST) or NY Open (7-10 AM EST)

ENTRY TIMING:
├── Reversal most likely during Kill Zones
├── Do not anticipate Phase 3 - wait for MSS
└── Model is fractal - visible on weekly, daily, hourly candles

FRAMEWORK VS REVERSAL:
├── Focus on nailing the REVERSAL PHASE entry
├── Framework trades around the model are secondary
└── Not all MMMs complete - some create fractal retracements
```

## Stop Loss Calculation

```python
def calculate_mmm_sl(setup, direction):
    """
    SL beyond the Smart Money Reversal extreme
    (the swing low in MMBM, swing high in MMSM)
    """
    
    buffer = 0.0020  # 20 pips for HTF setup
    
    if direction == 'bullish':
        sl = setup['entry']['mss_level'] - buffer
    else:
        sl = setup['entry']['mss_level'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_mmm_tp(setup, direction):
    """
    Target: Original consolidation zone + engineered liquidity
    Full model completion = massive move
    """
    
    consolidation = setup['consolidation']
    
    if direction == 'bullish':
        tp1 = consolidation['low']  # Bottom of consolidation
        tp2 = consolidation['high']  # Top of consolidation
        tp3 = setup['liquidity']['bsl_level']  # Engineered highs
    else:
        tp1 = consolidation['high']
        tp2 = consolidation['low']
        tp3 = setup['liquidity']['ssl_level']
        
    return {
        'tp1': tp1,
        'tp2': tp2,
        'tp3': tp3,  # Full model completion
        'expected_rr': (3.0, 5.0)
    }
```

---

# STRATEGY 10: POWER OF 3 / AMD INTRADAY CYCLE

## Concept
Every EURUSD trading day follows three phases: Accumulation (Asian), Manipulation (London open false breakout), Distribution (the real move). Only the Distribution phase is traded.

## The Three Phases

```
DAILY AMD CYCLE:
│
├── ACCUMULATION (Asian Session: 7PM - 2AM EST)
│   ├── Price consolidates, building range
│   ├── Creates high and low reference points
│   ├── Low volatility, tight range
│   └── DO NOT TRADE this phase
│
├── MANIPULATION (London Open: 2AM - 5AM EST)
│   ├── FALSE BREAKOUT of accumulation range
│   ├── Against the true daily bias
│   ├── Bullish day: dips below Asian low
│   ├── Bearish day: spikes above Asian high
│   └── This is the TRAP - do not trade yet
│
└── DISTRIBUTION (NY Session: 7AM onward)
    ├── True directional move begins
    ├── After manipulation reverses
    ├── THIS is the phase to trade
    └── Enter on FVG/OB from displacement
```

## Detection Algorithm

```python
class PowerOf3:
    
    def __init__(self):
        self.asian_start = time(19, 0)  # 7PM EST (previous day)
        self.asian_end = time(2, 0)     # 2AM EST
        self.manipulation_start = time(2, 0)
        self.manipulation_end = time(5, 0)
        self.distribution_start = time(7, 0)
        
    def detect(self, candles_m5, daily_bias):
        """
        PO3 / AMD DETECTION:
        1. Determine daily bias (HTF analysis)
        2. Mark Asian session range
        3. Detect manipulation (false breakout)
        4. Wait for reversal
        5. Enter distribution phase
        """
        
        # Step 1: Get Asian range
        asian_range = self.get_asian_range(candles_m5)
        
        # Step 2: Check current phase
        current_time = candles_m5[-1].time
        current_phase = self.get_current_phase(current_time)
        
        # Step 3: Detect manipulation
        manipulation = self.detect_manipulation(candles_m5, asian_range, daily_bias)
        
        # Step 4: If manipulation detected, look for reversal
        if manipulation and current_phase in ['manipulation', 'distribution']:
            reversal = self.detect_reversal(candles_m5, manipulation, daily_bias)
            
            if reversal:
                # Step 5: Find entry zone
                entry_zone = self.find_entry_zone(candles_m5, reversal)
                
                return {
                    'setup': 'power_of_3',
                    'direction': daily_bias,
                    'asian_range': asian_range,
                    'manipulation': manipulation,
                    'reversal': reversal,
                    'entry_zone': entry_zone,
                    'phase': current_phase
                }
                
        return None
    
    def get_asian_range(self, candles):
        """Get Asian session high and low"""
        
        asian_candles = [c for c in candles 
                        if self.is_asian_session(c.time)]
        
        if not asian_candles:
            return None
            
        return {
            'high': max(c.high for c in asian_candles),
            'low': min(c.low for c in asian_candles),
            'mid': (max(c.high for c in asian_candles) + 
                   min(c.low for c in asian_candles)) / 2
        }
    
    def detect_manipulation(self, candles, asian_range, daily_bias):
        """
        Detect false breakout of Asian range against daily bias
        """
        
        manipulation_candles = [c for c in candles 
                               if self.is_manipulation_window(c.time)]
        
        if daily_bias == 'bullish':
            # Look for sweep below Asian low (false bearish move)
            for c in manipulation_candles:
                if c.low < asian_range['low'] - 0.0005:  # 5 pip buffer
                    return {
                        'type': 'ssl_sweep',
                        'extreme': c.low,
                        'candle': c
                    }
                    
        elif daily_bias == 'bearish':
            # Look for sweep above Asian high (false bullish move)
            for c in manipulation_candles:
                if c.high > asian_range['high'] + 0.0005:
                    return {
                        'type': 'bsl_sweep',
                        'extreme': c.high,
                        'candle': c
                    }
                    
        return None
    
    def detect_reversal(self, candles, manipulation, daily_bias):
        """
        Detect reversal after manipulation
        MSS confirms the turn
        """
        
        post_manipulation = candles[-20:]  # Recent candles
        
        mss = detect_mss(post_manipulation)
        if mss and mss['type'] == daily_bias:
            return {
                'mss': mss,
                'confirmed': True
            }
            
        return None
    
    def find_entry_zone(self, candles, reversal):
        """
        Entry on FVG or OB from the displacement
        """
        
        fvg = detect_fvg(candles[-10:])
        if fvg:
            return {
                'type': 'fvg',
                'zone': fvg
            }
            
        ob = detect_order_block(candles[-15:], reversal['mss']['type'])
        if ob:
            return {
                'type': 'order_block',
                'zone': ob
            }
            
        return None
```

## Entry Rules

```
ENTRY CONDITIONS:
├── Daily bias correctly determined (HTF analysis)
├── Asian session range marked
├── Manipulation detected (false breakout against bias)
├── Reversal confirmed with MSS/CHoCH
├── FVG or OB formed during displacement
├── Current phase: Distribution (NY session)
└── Clear three-phase structure visible

ENTRY TYPE: Limit order at FVG or Order Block

FRACTAL APPLICATION:
├── PO3 visible on weekly, daily, AND hourly candles
├── Each individual candle follows AMD: Open → High/Low → Close
├── Weekly PO3 = Monday-Wednesday accumulation, 
│   Thursday manipulation, Friday distribution
└── Works best in TRENDING markets (less clear in chop)
```

## Stop Loss Calculation

```python
def calculate_po3_sl(setup, direction):
    """
    SL beyond the manipulation extreme (false breakout wick)
    """
    
    buffer = 0.0010  # 10 pips
    
    if direction == 'bullish':
        sl = setup['manipulation']['extreme'] - buffer
    else:
        sl = setup['manipulation']['extreme'] + buffer
        
    return sl
```

## Take Profit Targets

```python
def calculate_po3_tp(setup, direction, candles_daily):
    """
    TP1: PDH/PDL (Previous Day High/Low)
    TP2: HTF liquidity targets
    TP3: Previous session High/Low
    """
    
    pdh = get_previous_day_high(candles_daily)
    pdl = get_previous_day_low(candles_daily)
    
    if direction == 'bullish':
        return {
            'tp1': setup['asian_range']['high'],  # Asian high
            'tp2': pdh,  # Previous day high
            'expected_rr': (2.0, 3.0)
        }
    else:
        return {
            'tp1': setup['asian_range']['low'],
            'tp2': pdl,
            'expected_rr': (2.0, 3.0)
        }
```

---

# STRATEGIES 11-15: LESSER-KNOWN SETUPS

## Strategy 11: Propulsion Block

```python
class PropulsionBlock:
    """
    A candle that trades WITHIN an activated Order Block
    and drives price forcefully away from it.
    Not an OB itself - a momentum candle inside an OB.
    """
    
    def detect(self, candles_m5, candles_h1):
        # FIVE VALIDATION CRITERIA (all required):
        validation = {
            '1_accumulated_liquidity': self.check_liquidity_pool(candles_h1),
            '2_activated_order_block': self.find_activated_ob(candles_m5),
            '3_fvg_after_propulsion': None,
            '4_zone_untouched': None,
            '5_candle_characteristics': None
        }
        
        if not validation['2_activated_order_block']:
            return None
            
        ob = validation['2_activated_order_block']
        
        # Find propulsion candle within OB
        for c in candles_m5[-20:]:
            if self.candle_within_zone(c, ob):
                # Check propulsion characteristics
                body = abs(c.close - c.open)
                total_range = c.high - c.low
                body_ratio = body / total_range if total_range > 0 else 0
                
                if body_ratio > 0.6:  # Body larger than wick
                    # Check FVG formation after propulsion
                    idx = candles_m5.index(c)
                    if idx + 3 < len(candles_m5):
                        fvg = detect_fvg(candles_m5[idx:idx+4])
                        if fvg:
                            validation['3_fvg_after_propulsion'] = fvg
                            validation['5_candle_characteristics'] = True
                            
                            # Check zone wasn't retouched
                            subsequent = candles_m5[idx+1:]
                            if not self.zone_touched(subsequent, ob):
                                validation['4_zone_untouched'] = True
                                
        if all(validation.values()):
            return {
                'setup': 'propulsion_block',
                'order_block': ob,
                'propulsion_candle': c,
                'fvg': fvg,
                'entry_zone': ob  # Enter on PB retest
            }
        return None

# ENTRY: M5-M15 after propulsion block retest
# SL: Beyond propulsion block zone extreme
# TP: Next liquidity target
# WIN RATE: Improves dramatically with Daily bias alignment
```

## Strategy 12: Vacuum Block

```python
class VacuumBlock:
    """
    Price gap created by session opens, weekend gaps, or high-impact news
    where no orders were executed.
    The 50% level is the most frequently visited price point.
    """
    
    def detect(self, candles_h1):
        # Find gaps in price (no overlapping candles)
        for i in range(1, len(candles_h1)):
            prev = candles_h1[i-1]
            curr = candles_h1[i]
            
            # Gap up
            if curr.low > prev.high:
                gap = {
                    'type': 'bullish',
                    'top': curr.low,
                    'bottom': prev.high,
                    'ce': (curr.low + prev.high) / 2,  # 50% = KEY LEVEL
                    'gap_type': self.classify_gap(prev.time, curr.time)
                }
                return gap
                
            # Gap down
            if curr.high < prev.low:
                gap = {
                    'type': 'bearish',
                    'top': prev.low,
                    'bottom': curr.high,
                    'ce': (prev.low + curr.high) / 2,
                    'gap_type': self.classify_gap(prev.time, curr.time)
                }
                return gap
                
        return None
    
    def classify_gap(self, prev_time, curr_time):
        # Weekend gap, session gap, or news gap
        if prev_time.weekday() == 4 and curr_time.weekday() == 6:
            return 'weekend_gap'
        elif (curr_time - prev_time).seconds > 3600:
            return 'session_gap'
        else:
            return 'news_gap'

# ENTRY: At or near 50% level (CE) with LTF MSS confirmation
# SL: Beyond full vacuum block extent
# BEST APPLICATION: EURUSD Sunday/Monday opens, ECB decision gaps
# WIN RATE: 65-70%
```

## Strategy 13: Reclaimed FVG

```python
class ReclaimedFVG:
    """
    Price enters FVG but FAILS to close beyond its CE (50%).
    Zone strengthens on each test that respects the CE.
    Enter on second retest.
    """
    
    def detect(self, candles_m15, known_fvgs):
        for fvg in known_fvgs:
            tests = self.count_ce_tests(candles_m15, fvg)
            
            if tests['count'] >= 2 and tests['all_respected']:
                # Zone has been tested 2+ times and CE held
                return {
                    'setup': 'reclaimed_fvg',
                    'fvg': fvg,
                    'test_count': tests['count'],
                    'entry_zone': {
                        'boundary': fvg['top'] if fvg['type'] == 'bullish' else fvg['bottom'],
                        'ce': fvg['ce']
                    }
                }
                
        return None
    
    def count_ce_tests(self, candles, fvg):
        tests = {'count': 0, 'all_respected': True}
        
        for c in candles:
            # Check if candle tested the FVG
            if fvg['type'] == 'bullish':
                if c.low <= fvg['top']:  # Touched FVG
                    tests['count'] += 1
                    # Did it close beyond CE?
                    if c.close < fvg['ce']:
                        tests['all_respected'] = False
            else:
                if c.high >= fvg['bottom']:
                    tests['count'] += 1
                    if c.close > fvg['ce']:
                        tests['all_respected'] = False
                        
        return tests

# CRITICAL RULE: If price CLOSES past CE → reclaim thesis FAILS
# "PERFECT FVGs" (Candle 3 body touches exactly at FVG edge) = highest success
# SL: Below full FVG range
# WIN RATE: 70%+
```

## Strategy 14: CISD (Change in State of Delivery)

```python
class CISD:
    """
    Signals directional shift BEFORE CHoCH or MSS appears.
    Earlier entries at cost of more false signals.
    Use as confluence, never standalone.
    """
    
    def detect(self, candles_m5, htf_key_levels):
        # Bullish CISD: Close above opening price of preceding bearish sequence
        bearish_sequence = self.find_bearish_sequence(candles_m5)
        
        if bearish_sequence:
            sequence_open = bearish_sequence['first_candle'].open
            
            # Check if recent candle closes above sequence open
            recent = candles_m5[-1]
            if recent.close > sequence_open:
                # Verify at HTF key level
                for level in htf_key_levels:
                    if abs(recent.close - level) < 0.0015:  # Within 15 pips
                        # Check for prior liquidity sweep
                        sweep = self.check_prior_sweep(candles_m5, level)
                        if sweep:
                            return {
                                'setup': 'cisd',
                                'type': 'bullish',
                                'cisd_level': sequence_open,
                                'htf_level': level,
                                'sweep': sweep
                            }
                            
        return None

# MUST OCCUR:
# - At or near HTF key level
# - Must follow liquidity sweep
# - Requires FVG/OB retest for entry

# ENTRY TF: 15M/5M identification, 1M-3M entries during Kill Zones
# USE AS: Confluence only, NEVER standalone
# WIN RATE: 65-75% with proper filters
```

## Strategy 15: Balanced Price Range (BPR) Inside Order Blocks

```python
class BalancedPriceRange:
    """
    When both a bearish FVG and bullish FVG overlap in the same price range
    within an Order Block, it creates a powerful magnet for price.
    """
    
    def detect(self, candles_m15, candles_h4):
        # Step 1: Find HTF Order Block
        ob = detect_order_block(candles_h4, 'bullish')  # or bearish
        if not ob:
            return None
            
        # Step 2: Find FVGs within the OB zone
        fvgs_in_ob = []
        for i in range(2, len(candles_m15)):
            fvg = detect_fvg(candles_m15[i-2:i+1])
            if fvg and self.fvg_within_ob(fvg, ob):
                fvgs_in_ob.append(fvg)
                
        # Step 3: Find overlapping bullish and bearish FVGs
        bullish_fvgs = [f for f in fvgs_in_ob if f['type'] == 'bullish']
        bearish_fvgs = [f for f in fvgs_in_ob if f['type'] == 'bearish']
        
        for b_fvg in bullish_fvgs:
            for s_fvg in bearish_fvgs:
                overlap = self.calculate_overlap(b_fvg, s_fvg)
                if overlap['exists']:
                    return {
                        'setup': 'bpr_in_ob',
                        'order_block': ob,
                        'bullish_fvg': b_fvg,
                        'bearish_fvg': s_fvg,
                        'bpr_zone': overlap['zone'],
                        'entry_zone': overlap['zone']  # This is equilibrium
                    }
                    
        return None
    
    def calculate_overlap(self, fvg1, fvg2):
        overlap_top = min(fvg1['top'], fvg2['top'])
        overlap_bottom = max(fvg1['bottom'], fvg2['bottom'])
        
        if overlap_bottom < overlap_top:
            return {
                'exists': True,
                'zone': {
                    'top': overlap_top,
                    'bottom': overlap_bottom,
                    'midpoint': (overlap_top + overlap_bottom) / 2
                }
            }
        return {'exists': False}

# ENTRY: On confirmation at BPR zone with LTF structure shift
# RATIONALE: Dual-sided institutional interest = extreme reliability
# WIN RATE: 75%+ (highest among lesser-known setups)
```

---

# RISK MANAGEMENT FRAMEWORK

## Position Sizing

```python
def calculate_position_size(account_balance, risk_percent, entry, stop_loss, pip_value):
    """
    Standard risk-based position sizing
    Maximum: 1% per trade
    """
    
    risk_amount = account_balance * (risk_percent / 100)
    pip_distance = abs(entry - stop_loss) / pip_value
    position_size = risk_amount / (pip_distance * pip_value * 10)
    
    return position_size
```

## Daily Loss Limits

```
DAILY RISK MANAGEMENT:
├── Maximum 1% risk per trade
├── Two-loss daily stop (after 2 consecutive losses, stop trading)
├── 20-minute cooling period after any stop-out
├── Maximum 15 trades per month (performance degrades beyond this)
└── Avoid Monday trading (44% historical win rate)
```

## Trade Management

```python
def manage_trade(trade, current_price, direction):
    """
    Standard partial profit and trailing stop logic
    """
    
    risk = abs(trade['entry'] - trade['stop_loss'])
    
    # TP1 hit (1:2 RR) - close 50%
    tp1_distance = risk * 2
    if direction == 'bullish':
        tp1 = trade['entry'] + tp1_distance
        if current_price >= tp1:
            close_partial(0.5)
            move_sl_to_breakeven()
    else:
        tp1 = trade['entry'] - tp1_distance
        if current_price <= tp1:
            close_partial(0.5)
            move_sl_to_breakeven()
            
    # Trailing stop for runner
    if trade['partial_closed']:
        trail_stop_behind_structure(current_price, direction)
```

---

# APPENDIX: KEY DEFINITIONS

| Term | Definition |
|------|------------|
| **FVG** | Fair Value Gap - 3-candle pattern where C1 wick doesn't touch C3 wick |
| **OB** | Order Block - Last opposite-colored candle before displacement |
| **MSS** | Market Structure Shift - Break of recent swing with displacement |
| **CHoCH** | Change of Character - First break of structure in opposite direction |
| **CE** | Consequent Encroachment - 50% level of any zone |
| **OTE** | Optimal Trade Entry - 0.618-0.786 Fibonacci zone |
| **BSL** | Buy Side Liquidity - Stops above highs |
| **SSL** | Sell Side Liquidity - Stops below lows |
| **PDH/PDL** | Previous Day High/Low |
| **PWH/PWL** | Previous Week High/Low |
| **EQH/EQL** | Equal Highs/Lows - Clustered liquidity |
| **PD Array** | Premium/Discount Array - Institutional reference points |
| **Kill Zone** | High-probability trading windows (London/NY) |
| **SMT** | Smart Money Technique - Divergence between correlated pairs |
| **AMD** | Accumulation, Manipulation, Distribution |
| **BPR** | Balanced Price Range - Overlapping opposing FVGs |
| **CISD** | Change in State of Delivery - Early reversal signal |
| **iFVG** | Inverse FVG - FVG that has been breached and flipped |

---

# IMPLEMENTATION PRIORITY

For algorithmic implementation, prioritize in this order:

1. **Core Detection Functions** (FVG, OB, MSS, Liquidity Sweep)
2. **Global Filters** (Premium/Discount, Kill Zone, HTF Bias)
3. **Strategy 4: Silver Bullet** (most backtested, time-based)
4. **Strategy 3: Confirmation Model** (clearest rules)
5. **Strategy 2: Judas Swing** (session-based, clear triggers)
6. **Strategy 1: Unicorn Model** (highest probability)
7. **Remaining strategies** based on backtest results

**Expected realistic performance**: 55-65% win rate, 1:2-1:3 average R:R, resulting in positive expectancy when risk management is followed.
