"""
Mean Reversion Agent
Production implementation of mean reversion trading strategy with Google ADK integration
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


class MeanReversionAgent(BaseAgent):
    """
    Production Mean Reversion Trading Agent with Google ADK Integration
    
    Features:
    - Mean reversion strategy implementation
    - Overbought/oversold analysis
    - Statistical arbitrage opportunities
    - Bollinger Band mean reversion
    - RSI divergence analysis
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Mean reversion specific configuration
        self.strategy_type = config.get('strategy_type', 'mean_reversion')
        self.frequency_seconds = config.get('frequency_seconds', 900)
        self.confidence_threshold = config.get('confidence_threshold', 0.65)
        
        # Mean reversion parameters
        self.lookback_period = config.get('lookback_period', 50)
        self.deviation_threshold = config.get('deviation_threshold', 2.0)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'reversion_accuracy': 0.0,
            'false_signals': 0
        }
        
        logger.info("Mean Reversion Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Mean Reversion agent with ADK components"""
        try:
            # Initialize base agent
            await super().initialize()
            
            # Initialize LiteLLM model
            model_name = self.config.get('model', 'claude-3-sonnet@20240229')
            lite_llm = LiteLlm(model=model_name)
            
            # Create ADK LlmAgent only if not already set (preserves test mocks)
            if self.llm_agent is None:
                self.llm_agent = LlmAgent(
                    model=lite_llm,
                    name="mean_reversion_agent",
                    instruction=self._get_mean_reversion_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Mean Reversion Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Mean Reversion Agent: {e}")
            raise
    
    def _get_mean_reversion_system_instruction(self) -> str:
        """Get mean reversion specific system instruction for LLM agent"""
        return """
You are a mean reversion trading specialist focused on identifying overextended price movements.

Your expertise includes:
1. Identifying overbought and oversold conditions
2. Analyzing statistical deviations from mean prices
3. Detecting Bollinger Band squeeze and expansion patterns
4. RSI divergence and extreme readings analysis
5. Support and resistance level interactions

Key mean reversion indicators to analyze:
- Bollinger Bands (upper/lower band touches)
- RSI extreme readings (>70 overbought, <30 oversold)
- Standard deviation from moving averages
- Price-to-moving-average ratios
- Volume during overextensions
- Market regime (trending vs range-bound)

Trading approach:
- Target overextended moves for reversal
- Use statistical probability for entry timing
- Focus on range-bound market conditions
- Implement tight risk management
- Consider market sentiment extremes
- Avoid mean reversion in strong trends

Response format: Return JSON with signal, confidence, deviation_from_mean, reversion_probability, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for mean reversion signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build mean reversion analysis prompt
            prompt = self.build_mean_reversion_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"mean_reversion_{uuid.uuid4().hex[:8]}"
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
            signal = self.parse_mean_reversion_response(response_text)
            
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
            logger.error(f"Error in mean reversion market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_mean_reversion_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build mean reversion specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            
            # Extract technical indicators
            technical = market_data.get('technical_indicators', {})
            bollinger = technical.get('bollinger_bands', {})
            moving_averages = technical.get('moving_averages', {})
            rsi = technical.get('rsi', 50)
            
            # Calculate deviations
            sma_20 = moving_averages.get('sma_20', current_price)
            upper_band = bollinger.get('upper', current_price * 1.05)
            lower_band = bollinger.get('lower', current_price * 0.95)
            middle_band = bollinger.get('middle', current_price)
            
            prompt = f"""
Mean Reversion Strategy Analysis

Symbol: {symbol}
Current Price: {current_price}
Timestamp: {market_data.get('timestamp', datetime.now(timezone.utc).isoformat())}

Technical Analysis for Mean Reversion:
- RSI: {rsi} (Overbought >70, Oversold <30)
- SMA 20: {sma_20}
- Price vs SMA 20: {((current_price / sma_20 - 1) * 100):.2f}% deviation

Bollinger Bands:
- Upper Band: {upper_band}
- Middle Band: {middle_band}
- Lower Band: {lower_band}
- Band Position: {((current_price - lower_band) / (upper_band - lower_band) * 100):.1f}%

Market Context:
- Volume: {market_data.get('volume', 0):,}
- Sentiment Score: {market_data.get('sentiment_score', 0.5)}

Mean Reversion Analysis Requirements:
1. Assess overbought/oversold conditions
2. Calculate statistical deviation from mean
3. Evaluate Bollinger Band position
4. Analyze RSI extreme readings
5. Consider volume confirmation
6. Assess reversion probability

Focus Areas:
- Overextended price movements
- Statistical probability of reversion
- Support/resistance at mean levels
- Market regime identification
- Risk-reward for contrarian trades

Required Output (JSON format):
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": <float between 0.0 and 1.0>,
    "deviation_from_mean": "LOW|MEDIUM|HIGH",
    "reversion_probability": <float between 0.0 and 1.0>,
    "rsi_condition": "OVERSOLD|NEUTRAL|OVERBOUGHT",
    "bollinger_position": "LOWER|MIDDLE|UPPER",
    "target_price": <float>,
    "stop_loss": <float>,
    "rationale": "<detailed mean reversion analysis>"
}}

Analyze for mean reversion trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build mean reversion prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for mean reversion trading opportunities.
Return JSON with signal, confidence, deviation_from_mean, reversion_probability, and rationale.
"""
    
    def parse_mean_reversion_response(self, response: str) -> Dict[str, Any]:
        """Parse mean reversion LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for mean reversion specific fields
            signal_data.setdefault('deviation_from_mean', 'MEDIUM')
            signal_data.setdefault('reversion_probability', 0.5)
            signal_data.setdefault('rsi_condition', 'NEUTRAL')
            signal_data.setdefault('bollinger_position', 'MIDDLE')
            
            # Validate signal values
            if signal_data['signal'] not in ['BUY', 'SELL', 'HOLD']:
                signal_data['signal'] = 'HOLD'
            
            # Ensure confidence is within valid range
            confidence = float(signal_data['confidence'])
            signal_data['confidence'] = max(0.0, min(1.0, confidence))
            
            # Ensure reversion probability is within valid range
            reversion_prob = float(signal_data['reversion_probability'])
            signal_data['reversion_probability'] = max(0.0, min(1.0, reversion_prob))
            
            return signal_data
            
        except json.JSONDecodeError:
            logger.error("Failed to parse mean reversion JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing mean reversion response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'deviation_from_mean': 'LOW',
            'reversion_probability': 0.5,
            'rsi_condition': 'NEUTRAL',
            'bollinger_position': 'MIDDLE',
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback mean reversion signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"mean_reversion_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'MEAN_REVERSION',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'deviation_from_mean': signal_data.get('deviation_from_mean', 'MEDIUM'),
            'reversion_probability': signal_data.get('reversion_probability', 0.5),
            'rsi_condition': signal_data.get('rsi_condition', 'NEUTRAL'),
            'bollinger_position': signal_data.get('bollinger_position', 'MIDDLE'),
            'target_price': signal_data.get('target_price', 0.0),
            'stop_loss': signal_data.get('stop_loss', 0.0),
            'rationale': signal_data['rationale'],
            'market_data_snapshot': {
                'price': market_data.get('current_price'),
                'rsi': market_data.get('technical_indicators', {}).get('rsi'),
                'bollinger_bands': market_data.get('technical_indicators', {}).get('bollinger_bands', {})
            },
            'strategy_type': self.strategy_type,
            'frequency_seconds': self.frequency_seconds
        }
    
    def calculate_confidence_score(self, market_data: Dict[str, Any]) -> float:
        """Calculate mean reversion specific confidence score"""
        try:
            technical = market_data.get('technical_indicators', {})
            rsi = technical.get('rsi', 50)
            current_price = market_data.get('current_price', 0)
            
            # RSI extreme confidence
            rsi_confidence = 0.0
            if rsi > self.rsi_overbought:
                rsi_confidence = (rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
            elif rsi < self.rsi_oversold:
                rsi_confidence = (self.rsi_oversold - rsi) / self.rsi_oversold
            
            # Bollinger Band position
            bollinger = technical.get('bollinger_bands', {})
            band_confidence = 0.0
            if bollinger:
                upper = bollinger.get('upper', current_price)
                lower = bollinger.get('lower', current_price)
                if upper > lower:
                    if current_price >= upper:
                        band_confidence = 0.8  # At upper band - sell signal
                    elif current_price <= lower:
                        band_confidence = 0.8  # At lower band - buy signal
                    else:
                        band_position = (current_price - lower) / (upper - lower)
                        band_confidence = abs(band_position - 0.5) * 2  # Distance from middle
            
            # Combine factors
            confidence = (rsi_confidence * 0.6 + band_confidence * 0.4)
            
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            logger.error(f"Error calculating mean reversion confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if mean reversion signal should be published"""
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
            self.metrics['false_signals'] += 1
        
        # Update average confidence
        current_avg_confidence = self.metrics['average_confidence']
        self.metrics['average_confidence'] = (
            (current_avg_confidence * (total_signals - 1) + confidence) / total_signals
        )
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate performance report for the mean reversion agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'MEAN_REVERSION',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'reversion_accuracy': self.metrics['reversion_accuracy'],
            'false_signals': self.metrics['false_signals'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold,
            'rsi_thresholds': {
                'overbought': self.rsi_overbought,
                'oversold': self.rsi_oversold
            }
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_mean_reversion_prompt for consistency)"""
        return self.build_mean_reversion_prompt(market_data) 