"""
Fundamental Agent
Production implementation of fundamental analysis-based trading strategy with Google ADK integration
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

# Google ADK imports
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

# Core utilities
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FundamentalAgent(BaseAgent):
    """
    Production Fundamental Trading Agent with Google ADK Integration
    
    Features:
    - Earnings analysis
    - Financial metrics analysis
    - PE ratio assessment
    - Debt analysis
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Fundamental-specific configuration
        self.strategy_type = config.get('strategy_type', 'fundamental')
        self.frequency_seconds = config.get('frequency_seconds', 3600)  # 1 hour
        self.confidence_threshold = config.get('confidence_threshold', 0.8)
        
        # Fundamental parameters from test config
        self.earnings_weight = config.get('earnings_weight', 0.4)
        self.financials_weight = config.get('financials_weight', 0.3)
        self.ratios_weight = config.get('ratios_weight', 0.3)
        self.pe_threshold = config.get('pe_threshold', 25)
        self.debt_ratio_threshold = config.get('debt_ratio_threshold', 0.6)
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'fundamental_accuracy': 0.0
        }
        
        logger.info("Fundamental Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Fundamental agent with ADK components"""
        try:
            # Initialize base agent
            await super().initialize()
            
            # Initialize LiteLLM model
            model_name = self.config.get('model', 'gpt-4o')
            lite_llm = LiteLlm(model=model_name)
            
            # Create ADK LlmAgent only if not already set (preserves test mocks)
            if self.llm_agent is None:
                self.llm_agent = LlmAgent(
                    model=lite_llm,
                    name="fundamental_agent",
                    instruction=self._get_fundamental_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Fundamental Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Fundamental Agent: {e}")
            raise
    
    def _get_fundamental_system_instruction(self) -> str:
        """Get fundamental-specific system instruction for LLM agent"""
        return """
You are a fundamental analysis specialist focused on financial markets and trading signals.

Your expertise includes:
1. Analyzing earnings and financial metrics
2. Assessing PE ratios and debt analysis
3. Multi-source fundamental analysis

Response format: Return JSON with signal, confidence, earnings_sentiment, financials_sentiment, ratios_sentiment, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for fundamental signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build fundamental analysis prompt
            prompt = self.build_fundamental_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"sentiment_{uuid.uuid4().hex[:8]}"
            )
            
            # Extract text from response
            response_text = ""
            if hasattr(response, 'content') and hasattr(response.content, 'parts'):
                for part in response.content.parts:
                    if hasattr(part, 'text'):
                        response_text += part.text
            else:
                response_text = str(response)
            
            # Parse response
            signal = self.parse_fundamental_response(response_text)
            
            # Format final signal
            formatted_signal = self.format_signal(signal, market_data)
            
            # Record metrics
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=signal['confidence'],
                success=True
            )
            
            return formatted_signal
            
        except Exception as e:
            logger.error(f"Error in sentiment market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_fundamental_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build sentiment-specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Extract technical indicators
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            prompt = f"""
Sentiment Strategy Analysis

Symbol: {symbol}
Current Price: {current_price}
Volume: {volume:,}
Timestamp: {market_data.get('timestamp', datetime.now(timezone.utc).isoformat())}

Technical Analysis for Sentiment:
- SMA 20: {moving_averages.get('sma_20', 'N/A')}
- SMA 50: {moving_averages.get('sma_50', 'N/A')}
- EMA 12: {moving_averages.get('ema_12', 'N/A')}
- EMA 26: {moving_averages.get('ema_26', 'N/A')}
- RSI: {technical.get('rsi', 'N/A')}
- MACD: {technical.get('macd', 'N/A')}

OHLC Data:
{market_data.get('ohlc', {})}

Sentiment Strategy Requirements:
1. Analyze news sentiment and market impact
2. Social media sentiment tracking and filtering
3. Event-driven sentiment analysis
4. Multi-source sentiment aggregation

Focus Areas:
- News sentiment analysis
- Social media sentiment tracking
- Event impact assessment
- Market sentiment strength

  Required Output (JSON format):
  {{
     "signal": "BUY|SELL|HOLD",
     "confidence": <float between 0.0 and 1.0>,
     "news_sentiment": "POSITIVE|NEGATIVE|NEUTRAL",
     "social_sentiment": "POSITIVE|NEGATIVE|NEUTRAL|MODERATELY_POSITIVE|MODERATELY_NEGATIVE",
     "sentiment_score": <float between 0.0 and 1.0>,
     "sentiment_strength": "WEAK|MODERATE|STRONG",
     "target_price": <float>,
     "stop_loss": <float>,
     "rationale": "<detailed sentiment analysis>"
  }}

Analyze for sentiment trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build sentiment prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for sentiment trading opportunities.
Return JSON with signal, confidence, news_sentiment, social_sentiment, and rationale.
"""
    
    def parse_fundamental_response(self, response: str) -> Dict[str, Any]:
        """Parse fundamental LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for fundamental-specific fields
            signal_data.setdefault('pe_assessment', 'FAIR_VALUED')
            signal_data.setdefault('debt_assessment', 'HEALTHY')
            signal_data.setdefault('growth_assessment', 'MODERATE')
            signal_data.setdefault('dividend_assessment', 'MODERATE')
            signal_data.setdefault('fundamental_strength', 'MODERATE')
            signal_data.setdefault('valuation', 'FAIR_VALUED')
            signal_data.setdefault('target_price', 0.0)
            signal_data.setdefault('stop_loss', 0.0)
            
            # Validate signal values
            if signal_data['signal'] not in ['BUY', 'SELL', 'HOLD']:
                signal_data['signal'] = 'HOLD'
            
            # Ensure confidence is within valid range
            confidence = float(signal_data['confidence'])
            signal_data['confidence'] = max(0.0, min(1.0, confidence))
            
            return signal_data
            
        except json.JSONDecodeError:
            logger.error("Failed to parse fundamental JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing fundamental response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'pe_assessment': 'FAIR_VALUED',
            'debt_assessment': 'HEALTHY',
            'growth_assessment': 'MODERATE',
            'dividend_assessment': 'MODERATE',
            'fundamental_strength': 'MODERATE',
            'valuation': 'FAIR_VALUED',
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback fundamental signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"fundamental_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'FUNDAMENTAL',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'pe_assessment': signal_data.get('pe_assessment', 'FAIR_VALUED'),
            'debt_assessment': signal_data.get('debt_assessment', 'HEALTHY'),
            'growth_assessment': signal_data.get('growth_assessment', 'MODERATE'),
            'dividend_assessment': signal_data.get('dividend_assessment', 'MODERATE'),
            'fundamental_strength': signal_data.get('fundamental_strength', 'MODERATE'),
            'valuation': signal_data.get('valuation', 'FAIR_VALUED'),
            'target_price': signal_data.get('target_price', 0.0),
            'stop_loss': signal_data.get('stop_loss', 0.0),
            'rationale': signal_data['rationale'],
            'market_data_snapshot': {
                'price': market_data.get('current_price'),
                'volume': market_data.get('volume'),
                'fundamental_data': market_data.get('fundamental_data', {})
            },
            'strategy_type': self.strategy_type,
            'frequency_seconds': self.frequency_seconds
        }
    
    def calculate_confidence_score(self, market_data: Dict[str, Any]) -> float:
        """Calculate sentiment-specific confidence score"""
        try:
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            # Sentiment factors
            sma_20 = moving_averages.get('sma_20', 0)
            sma_50 = moving_averages.get('sma_50', 0)
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Calculate sentiment strength
            price_sentiment = 0.0
            if sma_20 > 0 and sma_50 > 0:
                if current_price > sma_20 > sma_50:  # Positive sentiment
                    price_sentiment = 0.8
                elif current_price < sma_20 < sma_50:  # Negative sentiment
                    price_sentiment = 0.8
                else:
                    price_sentiment = 0.3
            
            # Volume confirmation
            volume_factor = min(volume / 1000000, 1.0) if volume > 0 else 0.0
            
            # Combine factors
            confidence = (price_sentiment * 0.7 + volume_factor * 0.3)
            
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            logger.error(f"Error calculating sentiment confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if sentiment signal should be published"""
        return signal.get('confidence', 0.0) >= self.confidence_threshold
    
    def calculate_next_execution_time(self) -> datetime:
        """Calculate next execution time based on frequency"""
        return datetime.now(timezone.utc) + timedelta(seconds=self.frequency_seconds)
    
    def record_signal_generation(self, execution_time: float, confidence: float, success: bool) -> None:
        """Record signal generation metrics"""
        self.metrics['signals_generated'] += 1
        self.metrics['total_execution_time'] += execution_time
        
        # Update success rate
        total_signals = self.metrics['signals_generated']
        if success:
            current_success_rate = self.metrics['success_rate']
            self.metrics['success_rate'] = (
                (current_success_rate * (total_signals - 1) + 1.0) / total_signals
            )
        else:
            current_success_rate = self.metrics['success_rate']
            self.metrics['success_rate'] = (
                current_success_rate * (total_signals - 1) / total_signals
            )
        
        # Update average confidence
        current_avg_confidence = self.metrics['average_confidence']
        self.metrics['average_confidence'] = (
            (current_avg_confidence * (total_signals - 1) + confidence) / total_signals
        )
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate performance report for the sentiment agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'SENTIMENT',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'sentiment_accuracy': self.metrics['sentiment_accuracy'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_fundamental_prompt for consistency)"""
        return self.build_fundamental_prompt(market_data) 
