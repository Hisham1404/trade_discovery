"""
Risk Agent
Production implementation of risk-based trading strategy with Google ADK integration
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


class RiskAgent(BaseAgent):
    """
    Production Risk Trading Agent with Google ADK Integration
    
    Features:
    - Portfolio risk assessment
    - VaR and CVaR calculations
    - Stress testing scenarios
    - Position sizing recommendations
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Risk-specific configuration
        self.strategy_type = config.get('strategy_type', 'risk')
        self.frequency_seconds = config.get('frequency_seconds', 600)
        self.confidence_threshold = config.get('confidence_threshold', 0.85)
        
        # Risk parameters
        self.var_confidence = config.get('var_confidence', 0.95)
        self.portfolio_limit = config.get('portfolio_limit', 0.02)  # 2%
        self.correlation_threshold = config.get('correlation_threshold', 0.7)
        self.stress_test_scenarios = config.get('stress_test_scenarios', ['market_crash', 'inflation_spike', 'geopolitical'])
        
        # ADK components
        self.llm_agent: Optional[LlmAgent] = None
        
        # Performance tracking
        self.metrics = {
            'signals_generated': 0,
            'total_execution_time': 0.0,
            'success_rate': 0.0,
            'average_confidence': 0.0,
            'risk_accuracy': 0.0
        }
        
        logger.info("Risk Agent initialized")
    
    async def initialize(self) -> None:
        """Initialize the Risk agent with ADK components"""
        try:
            # Initialize base agent
            await super().initialize()
            
            # Initialize LiteLLM model
            model_name = self.config.get('model', 'claude-3-sonnet-20240229')
            lite_llm = LiteLlm(model=model_name)
            
            # Create ADK LlmAgent only if not already set (preserves test mocks)
            if self.llm_agent is None:
                self.llm_agent = LlmAgent(
                    model=lite_llm,
                    name="risk_agent",
                    instruction=self._get_risk_system_instruction()
                )
            
            self.is_initialized = True
            logger.info("Risk Agent initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Risk Agent: {e}")
            raise
    
    def _get_risk_system_instruction(self) -> str:
        """Get risk-specific system instruction for LLM agent"""
        return """
You are a portfolio risk assessment specialist focused on financial markets.

Your expertise includes:
1. Value at Risk (VaR) and Conditional VaR calculations
2. Portfolio correlation and diversification analysis
3. Stress testing under market scenarios
4. Position sizing and risk-adjusted recommendations

Response format: Return JSON with signal, confidence, risk_level, var_assessment, and detailed rationale.
"""
    
    async def analyze_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market data for risk signals"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Build risk analysis prompt
            prompt = self.build_risk_prompt(market_data)
            
            # Get LLM response
            if not self.llm_agent:
                return self._get_fallback_signal("LLM agent not initialized")
            
            response = await self.llm_agent.run_async(
                user_message=prompt,
                session_id=f"risk_{uuid.uuid4().hex[:8]}"
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
            signal = self.parse_risk_response(response_text)
            
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
            logger.error(f"Error in risk market analysis: {e}")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.record_signal_generation(
                execution_time=execution_time,
                confidence=0.0,
                success=False
            )
            return self._get_fallback_signal(f"Analysis error: {str(e)}")
    
    def build_risk_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build risk-specific analysis prompt"""
        try:
            symbol = market_data.get('symbol', 'UNKNOWN')
            current_price = market_data.get('current_price', 0)
            
            prompt = f"""
Risk Assessment Analysis

Symbol: {symbol}
Current Price: {current_price}
Portfolio Weight: {market_data.get('portfolio_weight', 0.05)}

Risk Parameters:
- VaR Confidence Level: {self.var_confidence}
- Portfolio Risk Limit: {self.portfolio_limit}
- Correlation Threshold: {self.correlation_threshold}

Risk Analysis Requirements:
1. Calculate position-level VaR and CVaR
2. Assess correlation with existing portfolio
3. Evaluate stress test scenarios
4. Recommend position sizing

Required Output (JSON format):
{{
   "signal": "BUY|SELL|HOLD",
   "confidence": <float between 0.0 and 1.0>,
   "risk_level": "LOW|MODERATE|HIGH",
   "var_assessment": "ACCEPTABLE|ELEVATED|EXCESSIVE",
   "target_price": <float>,
   "stop_loss": <float>,
   "rationale": "<detailed risk analysis>"
}}

Analyze for risk trading signal:
"""
            
            return prompt
            
        except Exception as e:
            logger.error(f"Failed to build risk prompt: {e}")
            return self._get_fallback_prompt(market_data)
    
    def _get_fallback_prompt(self, market_data: Dict[str, Any]) -> str:
        """Fallback prompt when main prompt building fails"""
        return f"""
Analyze {market_data.get('symbol', 'UNKNOWN')} for risk assessment.
Return JSON with signal, confidence, risk_level, var_assessment, and rationale.
"""
    
    def parse_risk_response(self, response: str) -> Dict[str, Any]:
        """Parse risk LLM response and extract signal information"""
        try:
            # Try to parse JSON response
            signal_data = json.loads(response.strip())
            
            # Validate and set defaults for risk-specific fields
            signal_data.setdefault('risk_level', 'MODERATE')
            signal_data.setdefault('var_assessment', 'ACCEPTABLE')
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
            logger.error("Failed to parse risk JSON response")
            return self._get_fallback_signal("JSON parsing error")
        except Exception as e:
            logger.error(f"Error parsing risk response: {e}")
            return self._get_fallback_signal(f"Parsing error: {str(e)}")
    
    def _get_fallback_signal(self, reason: str) -> Dict[str, Any]:
        """Generate fallback signal when parsing fails"""
        return {
            'signal': 'HOLD',
            'confidence': 0.5,
            'risk_level': 'MODERATE',
            'var_assessment': 'ACCEPTABLE',
            'target_price': 100.0,
            'stop_loss': 95.0,
            'rationale': f"Fallback risk signal due to {reason}"
        }
    
    def format_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format signal with standardized structure"""
        return {
            'signal_id': f"risk_{uuid.uuid4().hex[:12]}",
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'symbol': market_data.get('symbol', 'UNKNOWN'),
            'agent_type': 'RISK',
            'agent_version': '1.0.0',
            'signal': signal_data['signal'],
            'confidence': signal_data['confidence'],
            'risk_level': signal_data.get('risk_level', 'MODERATE'),
            'var_assessment': signal_data.get('var_assessment', 'ACCEPTABLE'),
            'target_price': signal_data.get('target_price', 0.0),
            'stop_loss': signal_data.get('stop_loss', 0.0),
            'rationale': signal_data['rationale'],
            'market_data_snapshot': {
                'price': market_data.get('current_price'),
                'portfolio_weight': market_data.get('portfolio_weight', 0.05)
            },
            'strategy_type': self.strategy_type,
            'frequency_seconds': self.frequency_seconds
        }
    
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
    
    def calculate_confidence_score(self, market_data: Dict[str, Any]) -> float:
        """Calculate risk-specific confidence score based on portfolio factors"""
        try:
            # Base confidence from market data quality
            current_price = market_data.get('current_price', 0)
            portfolio_weight = market_data.get('portfolio_weight', 0.05)
            
            # Price validity check
            price_factor = 1.0 if current_price > 0 else 0.0
            
            # Portfolio weight factor (smaller weights = higher confidence)
            weight_factor = 1.0 - min(portfolio_weight / 0.1, 1.0)  # Inverse relationship
            
            # Risk parameters validation
            risk_params_factor = 0.8 if self.var_confidence > 0.9 else 0.6
            
            # Combine factors
            confidence = (price_factor * 0.4 + weight_factor * 0.4 + risk_params_factor * 0.2)
            
            return max(0.1, min(1.0, confidence))
            
        except Exception as e:
            logger.error(f"Error calculating risk confidence: {e}")
            return 0.5
    
    def should_publish_signal(self, signal: Dict[str, Any]) -> bool:
        """Determine if risk signal should be published"""
        return signal.get('confidence', 0.0) >= self.confidence_threshold
    
    def calculate_next_execution_time(self) -> datetime:
        """Calculate next execution time based on frequency"""
        return datetime.now(timezone.utc) + timedelta(seconds=self.frequency_seconds)
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate performance report for the risk agent"""
        total_signals = self.metrics['signals_generated']
        
        return {
            'agent_type': 'RISK',
            'strategy_type': self.strategy_type,
            'signals_generated': total_signals,
            'average_execution_time': (
                self.metrics['total_execution_time'] / total_signals 
                if total_signals > 0 else 0.0
            ),
            'success_rate': self.metrics['success_rate'],
            'average_confidence': self.metrics['average_confidence'],
            'risk_accuracy': self.metrics['risk_accuracy'],
            'frequency_seconds': self.frequency_seconds,
            'confidence_threshold': self.confidence_threshold
        }
    
    def build_analysis_prompt(self, market_data: Dict[str, Any]) -> str:
        """Build analysis prompt (alias for build_risk_prompt for consistency)"""
        return self.build_risk_prompt(market_data)
