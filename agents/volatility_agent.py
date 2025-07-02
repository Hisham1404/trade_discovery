"""
Volatility Agent
Production implementation of volatility-based trading strategy with Google ADK integration
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


class VolatilityAgent(BaseAgent):
    """
    Production Volatility Trading Agent with Google ADK Integration
    
    Features:
    - Volatility strategy implementation
    - VIX and volatility index analysis
    - Volatility clustering detection
    - Options implied volatility analysis
    - Market regime change identification
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Volatility-specific configuration
        self.strategy_type = config.get('strategy_type', 'volatility')
        self.frequency_seconds = config.get('frequency_seconds', 120)
        self.confidence_threshold = config.get('confidence_threshold', 0.75)
        
        # Volatility parameters
        self.volatility_lookback = config.get('volatility_lookback', 30)
        self.high_volatility_threshold = config.get('high_volatility_threshold', 25.0)
        self.low_volatility_threshold = config.get('low_volatility_threshold', 12.0)
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'volatility_accuracy': 0.0,
            'regime_changes_detected': 0
        }
        
        logger.info("Volatility Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Volatility agent with ADK components"""
        try:
            # Initialize base agent
            await super().initialize()
            
            # Initialize LiteLLM model
            model_name = self.config.get('model', 'gemini-2.0-flash')
            lite_llm = LiteLlm(model=model_name)
            
            # Create ADK LlmAgent only if not already set (preserves test mocks)
            if self.llm_agent is None:
                self.llm_agent = LlmAgent(
                    model=lite_llm,
                    name="volatility_agent",
                    instruction=self._get_volatility_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Volatility Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Volatility Agent: {e}")
            raise
    
    def _get_volatility_system_instruction(self) -> str:
        """Get volatility-specific system instruction for LLM agent"""
        return """
You are a volatility trading specialist focused on market volatility analysis and regime changes.

Your expertise includes:
1. Analyzing market volatility patterns and clustering
2. Interpreting VIX and volatility indices
3. Detecting market regime changes (low vol to high vol)
4. Options implied volatility analysis
5. Volatility breakouts and contractions

Key volatility indicators to analyze:
- Historical volatility vs implied volatility
- VIX levels and term structure
- Bollinger Band width (volatility proxy)
- Average True Range (ATR)
- Volatility clustering patterns
- Options skew and smile

Trading approach:
- Long volatility during regime changes
- Short volatility during contractions
- Volatility breakout strategies
- Options-based volatility plays
- Market timing based on vol cycles
- Risk parity and vol targeting

Response format: Return JSON with signal, confidence, volatility_level, volatility_trend, vix_interpretation, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for volatility signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build volatility analysis prompt
            prompt = self.build_volatility_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"volatility_{uuid.uuid4().hex[:8]}"
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
            signal = self.parse_volatility_response(response_text)
            
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
            logger.error(f"Error in volatility market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_volatility_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build volatility-specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Extract technical indicators
            technical = market_data.get('technical_indicators', {})
            bollinger = technical.get('bollinger_bands', {})
            
            # Calculate volatility proxy from Bollinger Bands
            volatility_proxy = 0.0
            if bollinger:
                upper = bollinger.get('upper', 0)
                lower = bollinger.get('lower', 0)
                middle = bollinger.get('middle', current_price)
                if middle > 0:
                    volatility_proxy = ((upper - lower) / middle) * 100
            
            prompt = f"""
Volatility Strategy Analysis

Symbol: {symbol}
Current Price: {current_price}
Volume: {volume:,}
Timestamp: {market_data.get('timestamp', datetime.now(timezone.utc).isoformat())}

Volatility Analysis:
- Bollinger Band Width: {volatility_proxy:.2f}% (Volatility Proxy)
- Upper Band: {bollinger.get('upper', 'N/A')}
- Lower Band: {bollinger.get('lower', 'N/A')}
- Price Position: {((current_price - bollinger.get('lower', current_price)) / max(bollinger.get('upper', current_price) - bollinger.get('lower', current_price), 1)) * 100:.1f}%

Technical Context:
- RSI: {technical.get('rsi', 'N/A')}
- MACD: {technical.get('macd', 'N/A')}

Market Context:
- Recent Price Range: {market_data.get('ohlc', {})}
- Sentiment Score: {market_data.get('sentiment_score', 0.5)}
- News Events: {market_data.get('news_events', [])}

Volatility Strategy Requirements:
1. Assess current volatility level (LOW/MEDIUM/HIGH)
2. Identify volatility trend (INCREASING/DECREASING/STABLE)
3. Evaluate volatility clustering patterns
4. Consider market regime implications
5. Assess VIX-like sentiment interpretation
6. Determine volatility trading opportunities

Focus Areas:
- Volatility breakouts and contractions
- Market regime change signals
- Risk-on vs risk-off sentiment
- Options-related volatility plays
- Volatility mean reversion

Required Output (JSON format):
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": <float between 0.0 and 1.0>,
    "volatility_level": "LOW|MEDIUM|HIGH",
    "volatility_trend": "INCREASING|DECREASING|STABLE",
    "vix_interpretation": "FEAR|GREED|OPPORTUNITY|CAUTION",
    "regime_change": true/false,
    "target_price": <float>,
    "stop_loss": <float>,
    "rationale": "<detailed volatility analysis>"
}}

Analyze for volatility trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build volatility prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for volatility trading opportunities.
Return JSON with signal, confidence, volatility_level, volatility_trend, vix_interpretation, and rationale.
"""
    
    def parse_volatility_response(self, response: str) -> Dict[str, Any]:
        """Parse volatility LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for volatility-specific fields
            signal_data.setdefault('volatility_level', 'MEDIUM')
            signal_data.setdefault('volatility_trend', 'STABLE')
            signal_data.setdefault('vix_interpretation', 'CAUTION')
            signal_data.setdefault('regime_change', False)
            
            # Validate signal values
            if signal_data['signal'] not in ['BUY', 'SELL', 'HOLD']:
                signal_data['signal'] = 'HOLD'
            
            # Ensure confidence is within valid range
            confidence = float(signal_data['confidence'])
            signal_data['confidence'] = max(0.0, min(1.0, confidence))
            
            return signal_data
            
        except json.JSONDecodeError:
            logger.error("Failed to parse volatility JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing volatility response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'volatility_level': 'MEDIUM',
            'volatility_trend': 'STABLE',
            'vix_interpretation': 'CAUTION',
            'regime_change': False,
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback volatility signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"volatility_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'VOLATILITY',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'volatility_level': signal_data.get('volatility_level', 'MEDIUM'),
            'volatility_trend': signal_data.get('volatility_trend', 'STABLE'),
            'vix_interpretation': signal_data.get('vix_interpretation', 'CAUTION'),
            'regime_change': signal_data.get('regime_change', False),
            'target_price': signal_data.get('target_price', 0.0),
            'stop_loss': signal_data.get('stop_loss', 0.0),
            'rationale': signal_data['rationale'],
            'market_data_snapshot': {
                'price': market_data.get('current_price'),
                'volume': market_data.get('volume'),
                'bollinger_bands': market_data.get('technical_indicators', {}).get('bollinger_bands', {})
            },
            'strategy_type': self.strategy_type,
            'frequency_seconds': self.frequency_seconds
        }
    
    def calculate_confidence_score(self, market_data: Dict[str, Any]) -> float:
        """Calculate volatility-specific confidence score"""
        try:
            technical = market_data.get('technical_indicators', {})
            bollinger = technical.get('bollinger_bands', {})
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Volatility measurement from Bollinger Bands
            volatility_confidence = 0.0
            if bollinger:
                upper = bollinger.get('upper', 0)
                lower = bollinger.get('lower', 0)
                middle = bollinger.get('middle', current_price)
                
                if middle > 0 and upper > lower:
                    band_width = (upper - lower) / middle
                    
                    # High confidence during volatility extremes
                    if band_width > 0.08:  # High volatility
                        volatility_confidence = 0.8
                    elif band_width < 0.04:  # Low volatility
                        volatility_confidence = 0.7
                    else:
                        volatility_confidence = 0.5
            
            # Volume confirmation
            volume_factor = min(volume / 1000000, 1.0) if volume > 0 else 0.5
            
            # Combine factors
            confidence = (volatility_confidence * 0.7 + volume_factor * 0.3)
            
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            logger.error(f"Error calculating volatility confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if volatility signal should be published"""
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
        """Generate performance report for the volatility agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'VOLATILITY',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'volatility_accuracy': self.metrics['volatility_accuracy'],
            'regime_changes_detected': self.metrics['regime_changes_detected'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold,
            'volatility_thresholds': {
                'high': self.high_volatility_threshold,
                'low': self.low_volatility_threshold
            }
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_volatility_prompt for consistency)"""
        return self.build_volatility_prompt(market_data) 