from typing import Dict, Any, Tuple

class ScoringSystem:
    """
    Evaluates stock setups and ranks them on a 1-10 scale.
    Categorizes signals into A+, A, B, C, and Weak ratings.
    """
    
    @staticmethod
    def evaluate(
        price: float,
        rvol: float,
        gap_pct: float,
        change_pct: float,
        has_news: bool,
        vwap: float,
        resistance: float,
        support: float,
        rsi: float
    ) -> Tuple[float, float, str]:
        """
        Evaluate opportunity and return (momentum_score, quality_score, rating).
        """
        points = 0.0
        max_points = 10.0
        
        # 1. RVOL Score (Max 2.5 points)
        if rvol >= 10.0:
            points += 2.5
        elif rvol >= 5.0:
            points += 2.0
        elif rvol >= 3.0:
            points += 1.5
        elif rvol >= 1.5:
            points += 0.5
            
        # 2. Gap Size Score (Max 2.0 points)
        if gap_pct >= 15.0:
            points += 2.0
        elif gap_pct >= 8.0:
            points += 1.5
        elif gap_pct >= 3.0:
            points += 1.0
        elif gap_pct >= 1.0:
            points += 0.5
            
        # 3. Price vs VWAP (Max 1.5 points)
        if vwap > 0:
            if price > vwap:
                points += 1.5
            elif price == vwap:
                points += 0.5
                
        # 4. News Catalyst Score (Max 1.5 points)
        if has_news:
            points += 1.5
            
        # 5. Breakout Score (Max 1.5 points)
        if resistance > 0:
            if price >= resistance:
                points += 1.5  # Breakout
            elif (resistance - price) / price <= 0.02:
                points += 0.75  # Near breakout
                
        # 6. Trend / RSI indicator (Max 1.0 points)
        if 55.0 <= rsi <= 75.0:
            points += 1.0  # Strong healthy trend
        elif 40.0 <= rsi < 55.0:
            points += 0.5  # Modest trend
        elif rsi > 75.0:
            points += 0.25  # Extended, but high momentum
            
        # Limit to 10 max
        points = min(points, max_points)
        
        # Calculate derived scores
        momentum_score = min((rvol * 0.4) + (abs(change_pct) * 0.3) + (gap_pct * 0.3), 10.0)
        quality_score = points
        
        # Determine Rating based on quality score
        if quality_score >= 9.0:
            rating = "A+"
        elif quality_score >= 8.0:
            rating = "A"
        elif quality_score >= 7.0:
            rating = "B"
        elif quality_score >= 5.0:
            rating = "C"
        else:
            rating = "Weak"
            
        return round(momentum_score, 1), round(quality_score, 1), rating
