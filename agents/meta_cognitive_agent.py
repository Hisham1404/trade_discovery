"""
Meta-Cognitive Agent with K-Level Reasoning

This module implements a sophisticated Meta-Cognitive Agent that uses K-Level reasoning 
to analyze other agents' outputs and dynamically adjust reasoning depth based on 
market conditions and signal quality.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import json
from abc import ABC, abstractmethod

from .base_agent import BaseAgent

# Configure logging
logger = logging.getLogger(__name__)


class KLevelReasoningEngine:
    """
    K-Level Reasoning Engine implementing different levels of strategic thinking:
    - K=0: Naive belief (what agent thinks)
    - K=1: Theory of mind (what agent thinks others think)
    - K=2: Meta-theory of mind (what agent thinks others think others think)
    """
    
    def __init__(self, max_k_level: int = 5):
        self.max_k_level = max_k_level
        self.complexity_cache = {}
    
    async def process_level_0(self, agent_belief: Dict[str, Any]) -> Dict[str, Any]:
        """Level 0: Direct agent belief without strategic consideration"""
        return {
            'level': 0,
            'belief': agent_belief,
            'meta_reasoning': None,
            'computation_complexity': 1
        }
    
    async def process_level_1(self, multi_agent_beliefs: Dict[str, Any]) -> Dict[str, Any]:
        """Level 1: Consider what other agents believe"""
        signals = [belief.get('signal', '') for belief in multi_agent_beliefs.values()]
        confidences = [belief.get('confidence', 0) for belief in multi_agent_beliefs.values()]
        
        # Analyze belief conflicts
        unique_signals = set(signals)
        has_conflicts = len(unique_signals) > 1
        
        # Determine consensus direction
        signal_counts = {signal: signals.count(signal) for signal in unique_signals}
        consensus_signal = max(signal_counts, key=signal_counts.get) if signal_counts else 'HOLD'
        
        return {
            'level': 1,
            'other_agent_analysis': {
                'agent_count': len(multi_agent_beliefs),
                'unique_signals': list(unique_signals),
                'average_confidence': np.mean(confidences) if confidences else 0,
                'consensus_signal': consensus_signal
            },
            'belief_conflicts': has_conflicts,
            'consensus_direction': 'MIXED' if has_conflicts else consensus_signal,
            'computation_complexity': len(multi_agent_beliefs) * 2
        }
    
    async def process_level_2(self, level_1_results: Dict[str, Any]) -> Dict[str, Any]:
        """Level 2: Consider what agents think others think"""
        strategic_considerations = []
        
        # Analyze meta-strategic elements
        for agent_name, l1_result in level_1_results.items():
            belief = l1_result.get('belief', {})
            other_analysis = l1_result.get('other_agent_analysis', {})
            
            # Strategic consideration: contrast effect
            if other_analysis.get('consensus_signal') != belief.get('signal'):
                strategic_considerations.append('contrarian_opportunity')
            
            # Strategic consideration: herding detection
            if other_analysis.get('average_confidence', 0) > 0.8:
                strategic_considerations.append('potential_herding')
        
        return {
            'level': 2,
            'meta_meta_reasoning': 'Deep strategic analysis of agent belief interactions',
            'strategic_considerations': strategic_considerations,
            'recursion_depth': 2,
            'computation_complexity': len(level_1_results) * 4
        }
    
    async def process_k_level(self, k_level: int, max_k_level: int = None, 
                            graceful_degradation: bool = False) -> Dict[str, Any]:
        """Process arbitrary K-level with optional graceful degradation"""
        effective_max = max_k_level or self.max_k_level
        
        if k_level > effective_max:
            if graceful_degradation:
                actual_k = effective_max
                return {
                    'actual_k_level': actual_k,
                    'degradation_applied': True,
                    'reason': f'K-level {k_level} reduced to {actual_k} due to computational limits'
                }
            else:
                raise ValueError(f"K-level too high: {k_level} > {effective_max}")
        
        return {
            'actual_k_level': k_level,
            'degradation_applied': False
        }
    
    async def measure_complexity(self, k_level: int, num_agents: int) -> Dict[str, Any]:
        """Measure computational complexity for given K-level and agent count"""
        # Exponential complexity growth with K-level
        operations = (k_level ** 2) * num_agents * 10
        time_estimate = operations / 1000.0  # Simplified time estimation
        
        return {
            'operations': operations,
            'time_estimate': time_estimate,
            'memory_estimate': k_level * num_agents * 0.1,  # MB
            'complexity_class': f'O(k^2 * n)' if k_level <= 3 else f'O(k^{k_level} * n)'
        }


class DynamicDepthController:
    """
    Controls reasoning depth dynamically based on market conditions,
    computational constraints, and historical performance feedback.
    """
    
    def __init__(self):
        self.performance_history = []
        self.efficiency_threshold = 0.75
    
    async def calculate_optimal_depth(self, market_conditions: Dict[str, Any], 
                                    constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate optimal K-level based on market conditions and constraints"""
        volatility = market_conditions.get('volatility', 0.2)
        complexity = market_conditions.get('complexity_score', 0.5)
        uncertainty = market_conditions.get('uncertainty_level', 0.3)
        
        # Base K-level calculation
        base_k = 1
        
        # Increase K-level for volatile/complex markets
        volatility_adjustment = int(volatility * 4)  # 0-4 levels
        complexity_adjustment = int(complexity * 2)  # 0-2 levels
        uncertainty_adjustment = int(uncertainty * 2)  # 0-2 levels
        
        recommended_k = base_k + volatility_adjustment + complexity_adjustment + uncertainty_adjustment
        
        # Apply constraints
        if constraints:
            max_k = constraints.get('max_k_level', 5)
            max_time = constraints.get('max_computation_time', 1.0)
            
            recommended_k = min(recommended_k, max_k)
            
            # Time-based constraint
            estimated_time = recommended_k * 0.03  # Rough estimate
            if estimated_time > max_time:
                recommended_k = max(1, int(max_time / 0.03))
        
        confidence_threshold = 0.6 + volatility * 0.3
        computation_budget = recommended_k * 0.05
        
        return {
            'k_level': max(1, recommended_k),
            'confidence_threshold': min(0.95, confidence_threshold),
            'computation_budget': computation_budget,
            'estimated_time': recommended_k * 0.03,
            'rationale': f'Vol:{volatility:.2f} Comp:{complexity:.2f} Unc:{uncertainty:.2f}'
        }
    
    async def optimize_from_feedback(self, feedback_data: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
        """Optimize K-level based on historical performance feedback"""
        if not feedback_data:
            return {'recommended_k_level': 2, 'efficiency_score': 0.0, 'rationale': 'No feedback data'}
        
        best_k = None
        best_efficiency = 0.0
        
        for k_level_str, metrics in feedback_data.items():
            # Extract K-level from string like 'k_level_2'
            try:
                k_level = int(k_level_str.split('_')[2])
            except (IndexError, ValueError):
                continue
            
            accuracy = metrics.get('accuracy', 0)
            comp_time = metrics.get('computation_time', 1)
            
            # Calculate efficiency as accuracy/time ratio
            efficiency = accuracy / max(comp_time, 0.001)  # Avoid division by zero
            
            if efficiency > best_efficiency:
                best_efficiency = efficiency
                best_k = k_level
        
        return {
            'recommended_k_level': best_k or 2,
            'efficiency_score': best_efficiency,
            'rationale': f'K={best_k} provides best accuracy/time ratio: {best_efficiency:.2f}'
        }


class MetaCognitiveAgent(BaseAgent):
    """
    Meta-Cognitive Agent with K-Level reasoning that analyzes other agents' outputs
    and dynamically adjusts reasoning depth based on market conditions and signal quality.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.name = "MetaCognitiveAgent"
        
        # Initialize components
        self.k_level_engine = KLevelReasoningEngine()
        self.depth_controller = DynamicDepthController()
        
        # Configuration
        self.default_k_level = config.get('default_k_level', 2) if config else 2
        self.max_k_level = config.get('max_k_level', 5) if config else 5
        self.confidence_threshold = config.get('confidence_threshold', 0.7) if config else 0.7
        
        logger.info(f"MetaCognitiveAgent initialized with default K-level: {self.default_k_level}")
    
    async def analyze_k_level(self, agent_outputs: Dict[str, Any], k_level: int) -> Dict[str, Any]:
        """Perform K-level analysis on agent outputs"""
        start_time = time.time()
        
        try:
            if k_level == 0:
                # Pick first agent for K=0 analysis
                first_agent = next(iter(agent_outputs.values()))
                result = await self.k_level_engine.process_level_0(first_agent)
            elif k_level == 1:
                result = await self.k_level_engine.process_level_1(agent_outputs)
            elif k_level == 2:
                # For K=2, we need level 1 results first
                level_1_results = {}
                for agent_name, output in agent_outputs.items():
                    l1_result = await self.k_level_engine.process_level_1({agent_name: output})
                    level_1_results[agent_name] = {
                        'belief': output,
                        'other_agent_analysis': l1_result.get('other_agent_analysis', {})
                    }
                result = await self.k_level_engine.process_level_2(level_1_results)
            else:
                # For higher K-levels, use simplified processing
                complexity = await self.k_level_engine.measure_complexity(k_level, len(agent_outputs))
                result = {
                    'level': k_level,
                    'complexity_warning': f'High K-level ({k_level}) may be computationally expensive',
                    'estimated_operations': complexity['operations'],
                    'simplified_processing': True
                }
            
            # Add common fields
            result.update({
                'k_level': k_level,
                'agent_beliefs': agent_outputs,
                'consensus_strength': 0.7,  # Simplified consensus calculation
                'computation_complexity': result.get('computation_complexity', k_level * 10),
                'meta_reasoning': f'K-{k_level} analysis complete',
                'processing_time': time.time() - start_time
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in K-level {k_level} analysis: {e}")
            return {
                'k_level': k_level,
                'error': str(e),
                'agent_beliefs': agent_outputs,
                'consensus_strength': 0.5,
                'computation_complexity': k_level * 10,
                'meta_reasoning': f'K-{k_level} analysis failed'
            }
    
    async def analyze_confidence_levels(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze confidence levels across all agents"""
        confidences = [output.get('confidence', 0.5) for output in agent_outputs.values()]
        
        if not confidences:
            return {
                'average_confidence': 0.5,
                'confidence_variance': 0.0,
                'high_confidence_agents': [],
                'low_confidence_agents': [],
                'consensus_confidence': 0.5
            }
        
        avg_confidence = np.mean(confidences)
        confidence_variance = np.var(confidences)
        
        high_confidence_agents = [
            name for name, output in agent_outputs.items() 
            if output.get('confidence', 0) > 0.8
        ]
        
        low_confidence_agents = [
            name for name, output in agent_outputs.items() 
            if output.get('confidence', 0) < 0.7
        ]
        
        consensus_confidence = max(confidences)
        
        return {
            'average_confidence': avg_confidence,
            'confidence_variance': confidence_variance,
            'high_confidence_agents': high_confidence_agents,
            'low_confidence_agents': low_confidence_agents,
            'consensus_confidence': consensus_confidence
        }
    
    async def assess_reasoning_quality(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Assess the quality of reasoning across agents"""
        depth_scores = {}
        coherence_scores = {}
        evidence_strength = {}
        agent_scores = {}
        
        total_quality = 0
        agent_count = len(agent_outputs)
        
        for agent_name, output in agent_outputs.items():
            # Reasoning depth score
            depth = output.get('reasoning_depth', 1)
            depth_scores[agent_name] = depth
            
            # Coherence score (simplified based on reasoning length and structure)
            reasoning = output.get('reasoning', '')
            coherence = min(1.0, len(reasoning) / 100.0 + 0.3)  # Basic heuristic
            coherence_scores[agent_name] = coherence
            
            # Evidence strength (simplified)
            evidence_strength[agent_name] = 0.75  # Default moderate strength
            
            # Agent overall score
            agent_score = (depth / 5.0 * 0.4 + coherence * 0.3 + 0.75 * 0.3)
            agent_scores[agent_name] = min(1.0, agent_score)
            total_quality += agent_score
        
        overall_quality = total_quality / max(agent_count, 1) if agent_count > 0 else 0.5
        
        return {
            'depth_scores': depth_scores,
            'coherence_scores': coherence_scores,
            'evidence_strength': evidence_strength,
            'overall_quality': min(1.0, overall_quality),
            'agent_scores': agent_scores
        }
    
    async def calculate_weighted_consensus(self, agent_outputs: Dict[str, Any], 
                                         use_accuracy_weighting: bool = False) -> Dict[str, Any]:
        """Calculate weighted consensus of agent signals"""
        if not agent_outputs:
            return {
                'weighted_signal': 'HOLD',
                'accuracy_weights': {},
                'confidence_adjusted_signal': 'HOLD'
            }
        
        # Calculate weights
        if use_accuracy_weighting:
            weights = {
                name: output.get('historical_accuracy', 0.5) 
                for name, output in agent_outputs.items()
            }
        else:
            weights = {name: 1.0 for name in agent_outputs.keys()}
        
        # Calculate weighted signal
        signal_weights = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        
        for agent_name, output in agent_outputs.items():
            signal = output.get('signal', 'HOLD')
            confidence = output.get('confidence', 0.5)
            weight = weights.get(agent_name, 1.0)
            
            if signal in signal_weights:
                signal_weights[signal] += weight * confidence
        
        # Determine weighted signal
        weighted_signal = max(signal_weights, key=signal_weights.get)
        
        return {
            'weighted_signal': weighted_signal,
            'accuracy_weights': weights,
            'confidence_adjusted_signal': weighted_signal,
            'signal_weights': signal_weights
        }
    
    async def adjust_reasoning_depth(self, market_conditions: Dict[str, Any], 
                                   current_k_level: int) -> Dict[str, Any]:
        """Dynamically adjust reasoning depth based on market conditions"""
        optimal_depth = await self.depth_controller.calculate_optimal_depth(
            market_conditions
        )
        
        volatility = market_conditions.get('volatility', 0.2)
        complexity = market_conditions.get('complexity_score', 0.5)
        
        adjustment_reason = f'Volatility: {volatility:.2f}, Complexity: {complexity:.2f}'
        confidence_threshold = 0.7 + volatility * 0.2
        
        return {
            'recommended_k_level': optimal_depth['k_level'],
            'adjustment_reason': adjustment_reason,
            'confidence_threshold': min(0.95, confidence_threshold),
            'computation_budget': optimal_depth.get('computation_budget', 0.1),
            'estimated_time': optimal_depth.get('estimated_time', 0.05)
        }
    
    async def full_meta_cognitive_analysis(self, agent_outputs: Dict[str, Any], 
                                         market_conditions: Dict[str, Any],
                                         max_k_level: int = 5) -> Dict[str, Any]:
        """Perform complete meta-cognitive analysis"""
        start_time = time.time()
        
        try:
            # Determine optimal K-level
            depth_analysis = await self.adjust_reasoning_depth(market_conditions, 2)
            k_level_to_use = min(depth_analysis['recommended_k_level'], max_k_level)
            
            # Perform K-level analysis
            k_analysis = await self.analyze_k_level(agent_outputs, k_level_to_use)
            
            # Analyze confidence levels
            confidence_analysis = await self.analyze_confidence_levels(agent_outputs)
            
            # Assess reasoning quality
            quality_assessment = await self.assess_reasoning_quality(agent_outputs)
            
            # Calculate weighted consensus
            consensus = await self.calculate_weighted_consensus(agent_outputs, use_accuracy_weighting=True)
            
            # Generate meta-signal based on analysis
            meta_signal = consensus['weighted_signal']
            meta_confidence = min(0.95, confidence_analysis['average_confidence'] * quality_assessment['overall_quality'])
            
            total_time = time.time() - start_time
            
            return {
                'meta_signal': meta_signal,
                'confidence_score': meta_confidence,
                'k_level_used': k_level_to_use,
                'reasoning_explanation': f'Meta-cognitive analysis using K-level {k_level_to_use} reasoning',
                'computation_metrics': {
                    'complexity_score': quality_assessment['overall_quality'],
                    'time_taken': total_time,
                    'k_level_complexity': k_analysis.get('computation_complexity', 0)
                },
                'quality_assessment': quality_assessment,
                'confidence_analysis': confidence_analysis,
                'consensus_analysis': consensus,
                'depth_analysis': depth_analysis,
                'agent_count': len(agent_outputs),
                'scalability_metrics': {
                    'memory_usage': f'{len(agent_outputs) * k_level_to_use}MB',
                    'cpu_usage': f'{min(100, k_level_to_use * 5)}%'
                }
            }
            
        except Exception as e:
            logger.error(f"Error in full meta-cognitive analysis: {e}")
            return {
                'meta_signal': 'HOLD',
                'confidence_score': 0.5,
                'k_level_used': 1,
                'reasoning_explanation': f'Meta-cognitive analysis failed: {str(e)}',
                'computation_metrics': {'complexity_score': 0.5, 'time_taken': time.time() - start_time},
                'quality_assessment': {'overall_quality': 0.5},
                'agent_count': len(agent_outputs),
                'error': str(e)
            }
    
    async def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main signal generation method for BaseAgent compatibility"""
        # Extract agent outputs from market data
        agent_outputs = market_data.get('agent_outputs', {})
        market_conditions = market_data.get('market_conditions', {
            'volatility': 0.2,
            'complexity_score': 0.5,
            'uncertainty_level': 0.3
        })
        
        if not agent_outputs:
            logger.warning("No agent outputs provided for meta-cognitive analysis")
            return {
                'signal': 'HOLD',
                'confidence': 0.5,
                'reasoning': 'No agent outputs available for meta-cognitive analysis',
                'agent_name': self.name
            }
        
        # Perform full meta-cognitive analysis
        analysis = await self.full_meta_cognitive_analysis(agent_outputs, market_conditions)
        
        return {
            'signal': analysis['meta_signal'],
            'confidence': analysis['confidence_score'],
            'reasoning': analysis['reasoning_explanation'],
            'agent_name': self.name,
            'k_level_used': analysis['k_level_used'],
            'meta_analysis': analysis
        } 