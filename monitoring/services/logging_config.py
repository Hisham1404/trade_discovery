"""
Structured Logging Configuration Service
Configures JSON logging with trace correlation and Elasticsearch integration
"""

import logging
import structlog
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import asyncio
from elasticsearch import AsyncElasticsearch
from contextlib import contextmanager

class TraceManager:
    """Manages trace IDs for request correlation"""
    
    _trace_id = None
    
    @classmethod
    def get_trace_id(cls) -> str:
        """Get current trace ID or generate new one"""
        if cls._trace_id is None:
            cls._trace_id = str(uuid.uuid4())[:8]
        return cls._trace_id
    
    @classmethod
    def set_trace_id(cls, trace_id: str):
        """Set trace ID for current context"""
        cls._trace_id = trace_id
    
    @classmethod
    @contextmanager
    def trace_context(cls, trace_id: Optional[str] = None):
        """Context manager for trace ID"""
        old_trace_id = cls._trace_id
        cls._trace_id = trace_id or str(uuid.uuid4())[:8]
        try:
            yield cls._trace_id
        finally:
            cls._trace_id = old_trace_id

def add_trace_id(logger, method_name, event_dict):
    """Add trace ID to log events"""
    event_dict["trace_id"] = TraceManager.get_trace_id()
    return event_dict

def add_timestamp(logger, method_name, event_dict):
    """Add ISO timestamp to log events"""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict

def add_service_info(logger, method_name, event_dict):
    """Add service and component information"""
    event_dict["service"] = "trading-discovery"
    event_dict["version"] = "1.0.0"
    return event_dict

def add_agent_context(logger, method_name, event_dict):
    """Add agent-specific context if available"""
    # This would be populated by agent instances
    agent_id = getattr(logger, '_agent_id', None)
    agent_type = getattr(logger, '_agent_type', None)
    
    if agent_id:
        event_dict["agent_id"] = agent_id
    if agent_type:
        event_dict["agent_type"] = agent_type
    
    return event_dict

class ElasticsearchHandler(logging.Handler):
    """Custom logging handler for Elasticsearch"""
    
    def __init__(self, es_url: str = "http://localhost:9200", 
                 index_prefix: str = "trading-logs"):
        super().__init__()
        self.es_url = es_url
        self.index_prefix = index_prefix
        self.es_client = None
        self._buffer = []
        self._buffer_size = 100
        self._last_flush = datetime.utcnow()
    
    async def initialize(self):
        """Initialize Elasticsearch client"""
        try:
            self.es_client = AsyncElasticsearch([self.es_url])
            await self.es_client.ping()
            logging.info(f"Connected to Elasticsearch at {self.es_url}")
        except Exception as e:
            logging.error(f"Failed to connect to Elasticsearch: {e}")
            self.es_client = None
    
    def emit(self, record):
        """Emit log record to Elasticsearch"""
        if not self.es_client:
            return
        
        try:
            # Convert log record to dictionary
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "logger_name": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "thread": record.thread,
                "process": record.process
            }
            
            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.format(record)
            
            # Add extra fields
            if hasattr(record, '__dict__'):
                for key, value in record.__dict__.items():
                    if key not in log_entry and not key.startswith('_'):
                        log_entry[key] = value
            
            self._buffer.append(log_entry)
            
            # Flush buffer if full or time-based
            if (len(self._buffer) >= self._buffer_size or 
                (datetime.utcnow() - self._last_flush).seconds > 30):
                asyncio.create_task(self._flush_buffer())
                
        except Exception as e:
            print(f"Error in Elasticsearch handler: {e}")
    
    async def _flush_buffer(self):
        """Flush log buffer to Elasticsearch"""
        if not self._buffer or not self.es_client:
            return
        
        try:
            # Create index name with date
            index_name = f"{self.index_prefix}-{datetime.utcnow().strftime('%Y.%m.%d')}"
            
            # Bulk index documents
            actions = []
            for log_entry in self._buffer:
                actions.append({
                    "_index": index_name,
                    "_source": log_entry
                })
            
            if actions:
                from elasticsearch.helpers import async_bulk
                await async_bulk(self.es_client, actions)
                
            self._buffer.clear()
            self._last_flush = datetime.utcnow()
            
        except Exception as e:
            print(f"Error flushing to Elasticsearch: {e}")

class AgentLogger:
    """Logger wrapper for agent-specific logging"""
    
    def __init__(self, agent_type: str, agent_id: str):
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.logger = structlog.get_logger(f"agent.{agent_type}")
        
        # Add agent context to logger
        self.logger._agent_type = agent_type
        self.logger._agent_id = agent_id
    
    def info(self, message: str, **kwargs):
        """Log info message with agent context"""
        self.logger.info(message, agent_type=self.agent_type, 
                        agent_id=self.agent_id, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with agent context"""
        self.logger.warning(message, agent_type=self.agent_type, 
                           agent_id=self.agent_id, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with agent context"""
        self.logger.error(message, agent_type=self.agent_type, 
                         agent_id=self.agent_id, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with agent context"""
        self.logger.debug(message, agent_type=self.agent_type, 
                         agent_id=self.agent_id, **kwargs)
    
    def log_signal_generated(self, signal_data: Dict[str, Any]):
        """Log signal generation event"""
        self.logger.info(
            "Signal generated",
            event_type="signal_generated",
            signal_id=signal_data.get("signal_id"),
            symbol=signal_data.get("symbol"),
            confidence=signal_data.get("confidence"),
            signal_type=signal_data.get("signal_type"),
            agent_type=self.agent_type,
            agent_id=self.agent_id
        )
    
    def log_execution_time(self, duration_seconds: float, operation: str = "signal_generation"):
        """Log execution time metrics"""
        self.logger.info(
            f"Operation completed: {operation}",
            event_type="performance_metric",
            operation=operation,
            duration_seconds=duration_seconds,
            agent_type=self.agent_type,
            agent_id=self.agent_id
        )
    
    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """Log error with full context"""
        error_data = {
            "event_type": "error",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "agent_type": self.agent_type,
            "agent_id": self.agent_id
        }
        
        if context:
            error_data.update(context)
        
        self.logger.error(
            f"Error in {self.agent_type} agent",
            **error_data
        )

def configure_structured_logging(
    log_level: str = "INFO",
    enable_elasticsearch: bool = True,
    enable_file_logging: bool = True,
    log_dir: str = "./logs"
) -> None:
    """Configure structured logging for the application"""
    
    # Create logs directory
    Path(log_dir).mkdir(exist_ok=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_timestamp,
            add_trace_id,
            add_service_info,
            add_agent_context,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(message)s",
        handlers=[]
    )
    
    # Add console handler with JSON output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(console_handler)
    
    # Add file handler for persistent logs
    if enable_file_logging:
        file_handler = logging.FileHandler(f"{log_dir}/trading-discovery.log")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(file_handler)
    
    # Add Elasticsearch handler
    if enable_elasticsearch:
        es_handler = ElasticsearchHandler()
        asyncio.create_task(es_handler.initialize())
        logging.getLogger().addHandler(es_handler)
    
    # Log configuration completion
    logger = structlog.get_logger("logging.config")
    logger.info(
        "Structured logging configured",
        log_level=log_level,
        elasticsearch_enabled=enable_elasticsearch,
        file_logging_enabled=enable_file_logging,
        log_directory=log_dir
    )

def get_agent_logger(agent_type: str, agent_id: str) -> AgentLogger:
    """Get configured logger for an agent"""
    return AgentLogger(agent_type, agent_id)

def get_logger(name: str):
    """Get configured structlog logger"""
    return structlog.get_logger(name)

# Log retention configuration
LOG_RETENTION_POLICIES = {
    "elasticsearch_retention_days": 30,
    "file_log_retention_days": 7,
    "error_log_retention_days": 30,
    "agent_log_retention_days": 14,
    "performance_log_retention_days": 30
}

async def cleanup_old_logs():
    """Clean up old log files and Elasticsearch indices"""
    logger = get_logger("logging.cleanup")
    
    try:
        # Clean up file logs
        log_dir = Path("./logs")
        if log_dir.exists():
            cutoff_date = datetime.utcnow() - timedelta(
                days=LOG_RETENTION_POLICIES["file_log_retention_days"]
            )
            
            for log_file in log_dir.glob("*.log*"):
                file_stat = log_file.stat()
                file_date = datetime.fromtimestamp(file_stat.st_mtime)
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    logger.info(f"Deleted old log file: {log_file}")
        
        # Clean up Elasticsearch indices (implementation would depend on setup)
        logger.info("Log cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during log cleanup: {e}")

# Metrics logging helpers
def log_system_metrics(cpu_percent: float, memory_percent: float, 
                      disk_percent: float):
    """Log system metrics"""
    logger = get_logger("system.metrics")
    logger.info(
        "System metrics",
        event_type="system_metrics",
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        disk_percent=disk_percent
    )

def log_pulsar_metrics(topic: str, msg_rate_in: float, msg_rate_out: float,
                      storage_size: int, consumer_lag: int):
    """Log Pulsar topic metrics"""
    logger = get_logger("pulsar.metrics")
    logger.info(
        "Pulsar topic metrics",
        event_type="pulsar_metrics",
        topic=topic,
        msg_rate_in=msg_rate_in,
        msg_rate_out=msg_rate_out,
        storage_size=storage_size,
        consumer_lag=consumer_lag
    )

# Example usage and testing
async def test_logging_configuration():
    """Test the logging configuration"""
    configure_structured_logging(log_level="INFO")
    
    # Test basic logging
    logger = get_logger("test")
    logger.info("Test log message", test_field="test_value")
    
    # Test agent logging
    agent_logger = get_agent_logger("technical-agent", "tech-001")
    agent_logger.info("Agent test message")
    
    # Test signal logging
    signal_data = {
        "signal_id": "sig-123",
        "symbol": "RELIANCE",
        "confidence": 0.85,
        "signal_type": "BUY"
    }
    agent_logger.log_signal_generated(signal_data)
    
    # Test error logging
    try:
        raise ValueError("Test error")
    except Exception as e:
        agent_logger.log_error(e, {"context": "test_context"})
    
    print("Logging test completed")

if __name__ == "__main__":
    asyncio.run(test_logging_configuration()) 