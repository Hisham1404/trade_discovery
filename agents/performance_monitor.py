"""
Performance Monitor Module
Production implementation for monitoring ADK agent performance
"""

import asyncio
import logging
import psutil
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PerformanceAlert:
    """Performance alert structure"""
    alert_type: str
    severity: str
    message: str
    threshold: float
    current_value: float
    agent_name: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class PerformanceMonitor:
    """Production-grade ADK agent performance monitor"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_monitoring = False
        self.is_initialized = False
        
        # Performance data storage
        self.executions: List[Dict[str, Any]] = []
        self.agent_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'total_execution_time': 0.0,
            'execution_times': deque(maxlen=100),  # Keep last 100 execution times
            'memory_usage': deque(maxlen=100),     # Keep last 100 memory snapshots
            'last_execution': None,
            'error_count': 0,
            'error_messages': deque(maxlen=50)     # Keep last 50 errors
        })
        
        # System metrics
        self.system_metrics = {
            'cpu_usage': deque(maxlen=100),
            'memory_usage': deque(maxlen=100),
            'disk_usage': deque(maxlen=100),
            'process_memory': deque(maxlen=100)
        }
        
        # Configuration
        self.monitoring_interval = config.get('monitoring_interval', 30)  # seconds
        self.retention_hours = config.get('retention_hours', 24)
        self.alert_thresholds = config.get('alert_thresholds', {
            'execution_time_ms': 5000,      # 5 seconds
            'success_rate_min': 0.90,       # 90%
            'memory_usage_mb': 1024,        # 1GB
            'cpu_usage_percent': 80.0,      # 80%
            'error_rate_max': 0.10          # 10%
        })
        
        # Monitoring tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Process handle for system metrics
        self._process = psutil.Process()
        
        logger.info("PerformanceMonitor initialized")
    
    async def initialize(self) -> None:
        """Initialize performance monitor"""
        try:
            # Validate thresholds
            self._validate_thresholds()
            
            # Initialize baseline metrics
            await self._collect_baseline_metrics()
            
            self.is_initialized = True
            logger.info("Performance monitor initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize performance monitor: {e}")
            raise
    
    def _validate_thresholds(self) -> None:
        """Validate alert thresholds"""
        required_thresholds = [
            'execution_time_ms', 'success_rate_min', 'memory_usage_mb',
            'cpu_usage_percent', 'error_rate_max'
        ]
        
        for threshold in required_thresholds:
            if threshold not in self.alert_thresholds:
                raise ValueError(f"Missing required threshold: {threshold}")
    
    async def _collect_baseline_metrics(self) -> None:
        """Collect initial baseline system metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            process_memory = self._process.memory_info()
            
            self.system_metrics['cpu_usage'].append({
                'value': cpu_percent,
                'timestamp': datetime.now(timezone.utc)
            })
            
            self.system_metrics['memory_usage'].append({
                'value': memory.percent,
                'timestamp': datetime.now(timezone.utc)
            })
            
            self.system_metrics['disk_usage'].append({
                'value': disk.percent,
                'timestamp': datetime.now(timezone.utc)
            })
            
            self.system_metrics['process_memory'].append({
                'value': process_memory.rss / 1024 / 1024,  # MB
                'timestamp': datetime.now(timezone.utc)
            })
            
        except Exception as e:
            logger.warning(f"Failed to collect baseline metrics: {e}")
    
    async def start_monitoring(self) -> None:
        """Start comprehensive performance monitoring"""
        if not self.is_initialized:
            await self.initialize()
        
        if self.is_monitoring:
            logger.warning("Performance monitoring is already running")
            return
        
        try:
            self.is_monitoring = True
            
            # Start monitoring loop
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            logger.info("Performance monitoring started")
            
        except Exception as e:
            logger.error(f"Failed to start performance monitoring: {e}")
            self.is_monitoring = False
            raise
    
    async def stop_monitoring(self) -> None:
        """Stop performance monitoring"""
        logger.info("Stopping performance monitoring...")
        self.is_monitoring = False
        
        # Cancel monitoring tasks
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Performance monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _cleanup_loop(self) -> None:
        """Cleanup old metrics data"""
        while self.is_monitoring:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600)  # Run cleanup every hour
                
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(3600)
    
    async def _collect_system_metrics(self) -> None:
        """Collect current system metrics"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.system_metrics['cpu_usage'].append({
                'value': cpu_percent,
                'timestamp': current_time
            })
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_metrics['memory_usage'].append({
                'value': memory.percent,
                'timestamp': current_time
            })
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_metrics['disk_usage'].append({
                'value': disk.percent,
                'timestamp': current_time
            })
            
            # Process memory
            process_memory = self._process.memory_info()
            process_memory_mb = process_memory.rss / 1024 / 1024
            self.system_metrics['process_memory'].append({
                'value': process_memory_mb,
                'timestamp': current_time
            })
            
            logger.debug(f"Collected system metrics - CPU: {cpu_percent}%, Memory: {memory.percent}%, Process: {process_memory_mb:.1f}MB")
            
        except Exception as e:
            logger.warning(f"Failed to collect system metrics: {e}")
    
    async def _cleanup_old_data(self) -> None:
        """Clean up old performance data"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        
        try:
            # Clean up executions
            self.executions = [
                exec_data for exec_data in self.executions
                if datetime.fromisoformat(exec_data['timestamp']) > cutoff_time
            ]
            
            # Clean up agent metrics execution times
            for agent_name, metrics in self.agent_metrics.items():
                # Keep only recent execution times
                recent_times = []
                for exec_time in metrics['execution_times']:
                    if isinstance(exec_time, dict) and 'timestamp' in exec_time:
                        if datetime.fromisoformat(exec_time['timestamp']) > cutoff_time:
                            recent_times.append(exec_time)
                    else:
                        # Keep non-timestamped entries (legacy format)
                        recent_times.append(exec_time)
                
                metrics['execution_times'] = deque(recent_times, maxlen=100)
            
            logger.debug(f"Cleaned up performance data older than {self.retention_hours} hours")
            
        except Exception as e:
            logger.warning(f"Failed to cleanup old data: {e}")
    
    async def record_execution(self, metrics: Dict[str, Any]) -> None:
        """Record agent execution metrics"""
        try:
            # Add timestamp if not present
            if 'timestamp' not in metrics:
                metrics['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Store execution
            self.executions.append(metrics)
            
            # Update agent-specific metrics
            agent_name = metrics.get('agent_name', 'unknown')
            execution_time = metrics.get('execution_time', 0.0)
            success = metrics.get('status') == 'success'
            memory_usage = metrics.get('memory_usage_mb', 0.0)
            
            agent_metrics = self.agent_metrics[agent_name]
            agent_metrics['total_executions'] += 1
            agent_metrics['total_execution_time'] += execution_time
            agent_metrics['last_execution'] = metrics['timestamp']
            
            # Record execution time with timestamp
            agent_metrics['execution_times'].append({
                'value': execution_time * 1000,  # Convert to milliseconds
                'timestamp': metrics['timestamp']
            })
            
            # Record memory usage if available
            if memory_usage > 0:
                agent_metrics['memory_usage'].append({
                    'value': memory_usage,
                    'timestamp': metrics['timestamp']
                })
            
            if success:
                agent_metrics['successful_executions'] += 1
            else:
                agent_metrics['failed_executions'] += 1
                agent_metrics['error_count'] += 1
                
                # Record error message
                error_msg = metrics.get('error', 'Unknown error')
                agent_metrics['error_messages'].append({
                    'message': error_msg,
                    'timestamp': metrics['timestamp']
                })
            
            logger.debug(f"Recorded execution metrics for agent {agent_name}")
            
        except Exception as e:
            logger.error(f"Failed to record execution metrics: {e}")
    
    async def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Calculate overall metrics
            total_executions = len(self.executions)
            successful_executions = sum(1 for ex in self.executions if ex.get('status') == 'success')
            
            overall_success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
            
            # Calculate average execution time
            total_exec_time = sum(ex.get('execution_time', 0.0) for ex in self.executions)
            avg_execution_time = (total_exec_time / total_executions) if total_executions > 0 else 0.0
            
            # System metrics averages
            system_stats = {}
            for metric_name, metric_data in self.system_metrics.items():
                if metric_data:
                    recent_values = [item['value'] for item in metric_data if isinstance(item, dict)]
                    system_stats[metric_name] = {
                        'current': recent_values[-1] if recent_values else 0.0,
                        'average': sum(recent_values) / len(recent_values) if recent_values else 0.0,
                        'min': min(recent_values) if recent_values else 0.0,
                        'max': max(recent_values) if recent_values else 0.0
                    }
                else:
                    system_stats[metric_name] = {'current': 0.0, 'average': 0.0, 'min': 0.0, 'max': 0.0}
            
            # Agent-specific performance
            agent_performance = {}
            for agent_name, metrics in self.agent_metrics.items():
                total_agent_executions = metrics['total_executions']
                if total_agent_executions > 0:
                    agent_success_rate = metrics['successful_executions'] / total_agent_executions
                    agent_avg_time = metrics['total_execution_time'] / total_agent_executions
                    
                    # Recent execution times
                    recent_exec_times = [
                        item['value'] for item in metrics['execution_times'] 
                        if isinstance(item, dict) and 'value' in item
                    ]
                    
                    agent_performance[agent_name] = {
                        'total_executions': total_agent_executions,
                        'success_rate': agent_success_rate,
                        'average_execution_time_ms': agent_avg_time * 1000,
                        'recent_avg_execution_time_ms': (
                            sum(recent_exec_times[-10:]) / len(recent_exec_times[-10:])
                            if recent_exec_times else 0.0
                        ),
                        'error_count': metrics['error_count'],
                        'last_execution': metrics['last_execution']
                    }
                else:
                    agent_performance[agent_name] = {
                        'total_executions': 0,
                        'success_rate': 0.0,
                        'average_execution_time_ms': 0.0,
                        'recent_avg_execution_time_ms': 0.0,
                        'error_count': 0,
                        'last_execution': None
                    }
            
            return {
                'report_timestamp': current_time.isoformat(),
                'monitoring_duration_hours': (
                    (current_time - datetime.fromisoformat(self.executions[0]['timestamp'])).total_seconds() / 3600
                    if self.executions else 0.0
                ),
                'overall_metrics': {
                    'total_executions': total_executions,
                    'success_rate': overall_success_rate,
                    'average_execution_time_ms': avg_execution_time * 1000,
                    'total_agents_monitored': len(self.agent_metrics)
                },
                'system_metrics': system_stats,
                'agent_performance': agent_performance,
                'alert_thresholds': self.alert_thresholds,
                'monitoring_config': {
                    'monitoring_interval': self.monitoring_interval,
                    'retention_hours': self.retention_hours,
                    'is_monitoring': self.is_monitoring
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to generate performance report: {e}")
            return {
                'error': str(e),
                'report_timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    async def check_performance_alerts(self, thresholds: Dict[str, Any] = None) -> List[PerformanceAlert]:
        """Check for performance alerts based on thresholds"""
        alerts = []
        check_thresholds = thresholds or self.alert_thresholds
        
        try:
            current_time = datetime.now(timezone.utc)
            
            # Check system-level alerts
            if self.system_metrics['cpu_usage']:
                current_cpu = self.system_metrics['cpu_usage'][-1]['value']
                if current_cpu > check_thresholds.get('cpu_usage_percent', 80.0):
                    alerts.append(PerformanceAlert(
                        alert_type='system',
                        severity='warning',
                        message=f'High CPU usage detected',
                        threshold=check_thresholds['cpu_usage_percent'],
                        current_value=current_cpu,
                        timestamp=current_time
                    ))
            
            if self.system_metrics['process_memory']:
                current_memory = self.system_metrics['process_memory'][-1]['value']
                if current_memory > check_thresholds.get('memory_usage_mb', 1024):
                    alerts.append(PerformanceAlert(
                        alert_type='system',
                        severity='warning',
                        message=f'High memory usage detected',
                        threshold=check_thresholds['memory_usage_mb'],
                        current_value=current_memory,
                        timestamp=current_time
                    ))
            
            # Check agent-level alerts
            for agent_name, metrics in self.agent_metrics.items():
                total_executions = metrics['total_executions']
                
                if total_executions > 0:
                    # Success rate alert
                    success_rate = metrics['successful_executions'] / total_executions
                    if success_rate < check_thresholds.get('success_rate_min', 0.90):
                        alerts.append(PerformanceAlert(
                            alert_type='agent_performance',
                            severity='critical',
                            message=f'Low success rate for agent {agent_name}',
                            threshold=check_thresholds['success_rate_min'],
                            current_value=success_rate,
                            agent_name=agent_name,
                            timestamp=current_time
                        ))
                    
                    # Execution time alert
                    recent_exec_times = [
                        item['value'] for item in metrics['execution_times'][-10:]
                        if isinstance(item, dict) and 'value' in item
                    ]
                    
                    if recent_exec_times:
                        avg_recent_time = sum(recent_exec_times) / len(recent_exec_times)
                        if avg_recent_time > check_thresholds.get('execution_time_ms', 5000):
                            alerts.append(PerformanceAlert(
                                alert_type='agent_performance',
                                severity='warning',
                                message=f'Slow execution time for agent {agent_name}',
                                threshold=check_thresholds['execution_time_ms'],
                                current_value=avg_recent_time,
                                agent_name=agent_name,
                                timestamp=current_time
                            ))
                    
                    # Error rate alert
                    error_rate = metrics['failed_executions'] / total_executions
                    if error_rate > check_thresholds.get('error_rate_max', 0.10):
                        alerts.append(PerformanceAlert(
                            alert_type='agent_error',
                            severity='critical',
                            message=f'High error rate for agent {agent_name}',
                            threshold=check_thresholds['error_rate_max'],
                            current_value=error_rate,
                            agent_name=agent_name,
                            timestamp=current_time
                        ))
            
            if alerts:
                logger.warning(f"Generated {len(alerts)} performance alerts")
            
            return alerts
            
        except Exception as e:
            logger.error(f"Failed to check performance alerts: {e}")
            return []
    
    def get_agent_metrics(self, agent_name: str) -> Dict[str, Any]:
        """Get detailed metrics for a specific agent"""
        if agent_name not in self.agent_metrics:
            return {'error': f'Agent {agent_name} not found'}
        
        return dict(self.agent_metrics[agent_name])
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get current system health status"""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Get latest system metrics
            latest_metrics = {}
            for metric_name, metric_data in self.system_metrics.items():
                if metric_data:
                    latest_metrics[metric_name] = metric_data[-1]['value']
                else:
                    latest_metrics[metric_name] = 0.0
            
            # Determine overall health
            health_status = 'healthy'
            if latest_metrics.get('cpu_usage', 0) > self.alert_thresholds.get('cpu_usage_percent', 80):
                health_status = 'warning'
            if latest_metrics.get('process_memory', 0) > self.alert_thresholds.get('memory_usage_mb', 1024):
                health_status = 'warning'
            
            return {
                'status': health_status,
                'timestamp': current_time.isoformat(),
                'metrics': latest_metrics,
                'is_monitoring': self.is_monitoring,
                'monitored_agents': len(self.agent_metrics),
                'total_executions': len(self.executions)
            }
            
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            } 