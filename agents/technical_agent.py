"""
Technical Agent
Production implementation of technical analysis-based trading strategy with Google ADK integration
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


class TechnicalAgent(BaseAgent):
    """
    Production Technical Trading Agent with Google ADK Integration
    
    Features:
    - RSI analysis
    - MACD indicator analysis  
    - Bollinger bands analysis
    - ATR volatility analysis
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Technical-specific configuration
        self.strategy_type = config.get('strategy_type', 'technical')
        self.frequency_seconds = config.get('frequency_seconds', 240)  # 4 minutes
        self.confidence_threshold = config.get('confidence_threshold', 0.7)
        
        # Technical parameters from test config
        self.indicators = config.get('indicators', ['RSI', 'MACD', 'Bollinger', 'ATR'])
        self.lookback_period = config.get('lookback_period', 14)
        self.signal_threshold = config.get('signal_threshold', 0.75)
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'technical_accuracy': 0.0
        }
        
        logger.info("Technical Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Technical agent with ADK components"""
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
                    name="technical_agent",
                    instruction=self._get_technical_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Technical Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Technical Agent: {e}")
            raise
    
    def _get_technical_system_instruction(self) -> str:
        """Get technical-specific system instruction for LLM agent"""
        return """
You are a technical analysis specialist focused on financial markets and trading signals.

Your expertise includes:
1. RSI analysis
2. MACD indicator analysis
3. Bollinger bands analysis
4. ATR volatility analysis

Response format: Return JSON with signal, confidence, technical_indicator, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for technical analysis signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build technical analysis prompt
            prompt = self.build_technical_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"technical_{uuid.uuid4().hex[:8]}"
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
            signal = self.parse_technical_response(response_text)
            
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
            logger.error(f"Error in technical market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_technical_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build technical-specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Extract technical indicators
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            prompt = f"""
Technical Strategy Analysis

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

Technical Strategy Requirements:
1. RSI analysis
2. MACD indicator analysis
3. Bollinger bands analysis
4. ATR volatility analysis

Focus Areas:
- RSI analysis
- MACD indicator analysis
- Bollinger bands analysis
- ATR volatility analysis

  Required Output (JSON format):
  {{
     "signal": "BUY|SELL|HOLD",
     "confidence": <float between 0.0 and 1.0>,
     "technical_indicator": "<technical_indicator>",
     "sentiment_strength": "WEAK|MODERATE|STRONG",
     "target_price": <float>,
     "stop_loss": <float>,
     "rationale": "<detailed technical analysis>"
  }}

Analyze for technical trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build technical prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for technical trading opportunities.
Return JSON with signal, confidence, technical_indicator, and rationale.
"""
    
    def parse_technical_response(self, response: str) -> Dict[str, Any]:
        """Parse technical LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for technical-specific fields
            signal_data.setdefault('rsi_signal', 'NEUTRAL')
            signal_data.setdefault('macd_signal', 'NEUTRAL')
            signal_data.setdefault('bollinger_signal', 'NEUTRAL')
            signal_data.setdefault('atr_signal', 'NEUTRAL')
            signal_data.setdefault('technical_strength', 'MODERATE')
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
            logger.error("Failed to parse technical JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing technical response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'rsi_signal': 'NEUTRAL',
            'macd_signal': 'NEUTRAL',
            'bollinger_signal': 'NEUTRAL', 
            'atr_signal': 'NEUTRAL',
            'technical_strength': 'MODERATE',
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback technical signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"technical_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'TECHNICAL',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'rsi_signal': signal_data.get('rsi_signal', 'NEUTRAL'),
            'macd_signal': signal_data.get('macd_signal', 'NEUTRAL'),
            'bollinger_signal': signal_data.get('bollinger_signal', 'NEUTRAL'),
            'atr_signal': signal_data.get('atr_signal', 'NEUTRAL'),
            'technical_strength': signal_data.get('technical_strength', 'MODERATE'),
            'target_price': signal_data.get('target_price', 0.0),
            'stop_loss': signal_data.get('stop_loss', 0.0),
            'rationale': signal_data['rationale'],
            'market_data_snapshot': {
                'price': market_data.get('current_price'),
                'volume': market_data.get('volume'),
                'technical_indicators': market_data.get('technical_indicators', {})
            },
            'strategy_type': self.strategy_type,
            'frequency_seconds': self.frequency_seconds
        }
    
    def calculate_confidence_score(self, market_data: Dict[str, Any]) -> float:
        """Calculate technical-specific confidence score"""
        try:
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            # Technical factors
            sma_20 = moving_averages.get('sma_20', 0)
            sma_50 = moving_averages.get('sma_50', 0)
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Calculate technical strength
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
            logger.error(f"Error calculating technical confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if technical signal should be published"""
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
        """Generate performance report for the technical agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'TECHNICAL',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'technical_accuracy': self.metrics['technical_accuracy'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_technical_prompt for consistency)"""
        return self.build_technical_prompt(market_data) 