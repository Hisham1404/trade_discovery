"""
Momentum Agent
Production implementation of momentum-based trading strategy with Google ADK integration
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


class MomentumAgent(BaseAgent):
    """
    Production Momentum Trading Agent with Google ADK Integration
    
    Features:
    - Momentum strategy implementation
    - Trend following algorithms
    - Price acceleration analysis
    - Volume-confirmed momentum signals
    - Risk-adjusted position sizing
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Momentum-specific configuration
        self.strategy_type = config.get('strategy_type', 'momentum')
        self.frequency_seconds = config.get('frequency_seconds', 300)
        self.confidence_threshold = config.get('confidence_threshold', 0.7)
        
        # Momentum parameters
        self.momentum_lookback = config.get('momentum_lookback', 20)
        self.volume_threshold = config.get('volume_threshold', 1.5)  # 1.5x average volume
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'momentum_accuracy': 0.0
        }
        
        logger.info("Momentum Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Momentum agent with ADK components"""
        try:
            # Initialize base agent
            await super().initialize()
            
            # Initialize LiteLLM model
            model_name = self.config.get('model', 'gpt-4o')
            lite_llm = LiteLlm(model=model_name)
            
            # Create ADK LlmAgent
            # If llm_agent already set (e.g., injected by a test), keep existing mock
            if self.llm_agent is None:
                self.llm_agent = LlmAgent(
                    model=lite_llm,
                    name="momentum_agent",
                    instruction=self._get_momentum_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Momentum Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Momentum Agent: {e}")
            raise
    
    def _get_momentum_system_instruction(self) -> str:
        """Get momentum-specific system instruction for LLM agent"""
        return """
You are a momentum trading specialist focused on trend-following strategies.

Your expertise includes:
1. Identifying strong price momentum and trend acceleration
2. Analyzing volume confirmation for momentum moves
3. Detecting breakouts and trend continuations
4. Assessing momentum strength and sustainability
5. Risk management for momentum strategies

Key momentum indicators to analyze:
- Price rate of change (ROC)
- Moving average crossovers and slopes
- Volume surge analysis
- Relative strength comparison
- Momentum oscillators (RSI, MACD momentum)
- Breakout patterns and consolidations

Trading approach:
- Focus on trending markets with strong directional bias
- Require volume confirmation for momentum signals
- Use trend-following position sizing
- Implement momentum-based stop losses
- Consider market regime (trending vs sideways)

Response format: Return JSON with signal, confidence, momentum_strength, trend_direction, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for momentum signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build momentum analysis prompt
            prompt = self.build_momentum_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"momentum_{uuid.uuid4().hex[:8]}"
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
            signal = self.parse_momentum_response(response_text)
            
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
            logger.error(f"Error in momentum market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_momentum_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build momentum-specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Extract technical indicators
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            prompt = f"""
Momentum Strategy Analysis

Symbol: {symbol}
Current Price: {current_price}
Volume: {volume:,}
Timestamp: {market_data.get('timestamp', datetime.now(timezone.utc).isoformat())}

Technical Analysis for Momentum:
- SMA 20: {moving_averages.get('sma_20', 'N/A')}
- SMA 50: {moving_averages.get('sma_50', 'N/A')}
- EMA 12: {moving_averages.get('ema_12', 'N/A')}
- EMA 26: {moving_averages.get('ema_26', 'N/A')}
- RSI: {technical.get('rsi', 'N/A')}
- MACD: {technical.get('macd', 'N/A')}

OHLC Data:
{market_data.get('ohlc', {})}

Momentum Strategy Requirements:
1. Analyze trend direction and strength
2. Assess price momentum acceleration
3. Confirm with volume analysis
4. Evaluate moving average alignment
5. Consider momentum oscillator signals
6. Determine trend sustainability

Focus Areas:
- Trend following opportunities
- Breakout potential with volume
- Moving average crossover signals
- Price momentum strength
- Risk-reward for momentum trades

Required Output (JSON format):
{{
    "signal": "BUY|SELL|HOLD",
    "confidence": <float between 0.0 and 1.0>,
    "momentum_strength": "WEAK|MODERATE|STRONG",
    "trend_direction": "UPWARD|DOWNWARD|SIDEWAYS",
    "volume_confirmation": true/false,
    "target_price": <float>,
    "stop_loss": <float>,
    "rationale": "<detailed momentum analysis>"
}}

Analyze for momentum trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build momentum prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for momentum trading opportunities.
Return JSON with signal, confidence, momentum_strength, trend_direction, and rationale.
"""
    
    def parse_momentum_response(self, response: str) -> Dict[str, Any]:
        """Parse momentum LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for momentum-specific fields
            signal_data.setdefault('momentum_strength', 'MODERATE')
            signal_data.setdefault('trend_direction', 'SIDEWAYS')
            signal_data.setdefault('volume_confirmation', False)
            
            # Validate signal values
            if signal_data['signal'] not in ['BUY', 'SELL', 'HOLD']:
                signal_data['signal'] = 'HOLD'
            
            # Ensure confidence is within valid range
            confidence = float(signal_data['confidence'])
            signal_data['confidence'] = max(0.0, min(1.0, confidence))
            
            return signal_data
            
        except json.JSONDecodeError:
            logger.error("Failed to parse momentum JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing momentum response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'momentum_strength': 'WEAK',
            'trend_direction': 'SIDEWAYS',
            'volume_confirmation': False,
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback momentum signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"momentum_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'MOMENTUM',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'momentum_strength': signal_data.get('momentum_strength', 'MODERATE'),
            'trend_direction': signal_data.get('trend_direction', 'SIDEWAYS'),
            'volume_confirmation': signal_data.get('volume_confirmation', False),
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
        """Calculate momentum-specific confidence score"""
        try:
            technical = market_data.get('technical_indicators', {})
            moving_averages = technical.get('moving_averages', {})
            
            # Momentum factors
            sma_20 = moving_averages.get('sma_20', 0)
            sma_50 = moving_averages.get('sma_50', 0)
            current_price = market_data.get('current_price', 0)
            volume = market_data.get('volume', 0)
            
            # Calculate momentum strength
            price_momentum = 0.0
            if sma_20 > 0 and sma_50 > 0:
                if current_price > sma_20 > sma_50:  # Upward momentum
                    price_momentum = 0.8
                elif current_price < sma_20 < sma_50:  # Downward momentum
                    price_momentum = 0.8
                else:
                    price_momentum = 0.3
            
            # Volume confirmation
            volume_factor = min(volume / 1000000, 1.0) if volume > 0 else 0.0
            
            # Combine factors
            confidence = (price_momentum * 0.7 + volume_factor * 0.3)
            
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            logger.error(f"Error calculating momentum confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if momentum signal should be published"""
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
        """Generate performance report for the momentum agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'MOMENTUM',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'momentum_accuracy': self.metrics['momentum_accuracy'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_momentum_prompt for consistency)"""
        return self.build_momentum_prompt(market_data) 