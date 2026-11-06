import time
import threading
from typing import Dict, Any, Tuple
from collections import defaultdict

class MetricsService:
    """
    In-memory Prometheus-compatible metrics registry for TechDebt AI v3.0.0.
    Tracks request volume, latencies, assessment operations, and AI token consumption.
    """
    _lock = threading.Lock()
    _start_time = time.time()

    # Counters: (key, labels_tuple) -> count
    _counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = defaultdict(int)
    
    # Latencies: (method, endpoint) -> list of durations
    _latencies: Dict[Tuple[str, str], list] = defaultdict(list)

    @classmethod
    def record_request(cls, method: str, endpoint: str, status_code: int, duration_seconds: float):
        """Record an incoming HTTP request and its processing latency."""
        # Sanitize endpoint for metric grouping (replace UUIDs with {id})
        parts = endpoint.split("/")
        sanitized_parts = [
            "{id}" if len(p) > 20 or "-" in p else p
            for p in parts
        ]
        norm_endpoint = "/".join(sanitized_parts) or "/"

        labels = (
            ("method", method.upper()),
            ("endpoint", norm_endpoint),
            ("status", str(status_code))
        )

        with cls._lock:
            cls._counters[("http_requests_total", labels)] += 1
            lat_key = (method.upper(), norm_endpoint)
            # Keep recent 1000 latencies
            if len(cls._latencies[lat_key]) > 1000:
                cls._latencies[lat_key] = cls._latencies[lat_key][-500:]
            cls._latencies[lat_key].append(duration_seconds)

    @classmethod
    def increment_counter(cls, name: str, labels: Dict[str, str], value: int = 1):
        """Increment arbitrary metric counter with key-value labels."""
        sorted_labels = tuple(sorted(labels.items()))
        with cls._lock:
            cls._counters[(name, sorted_labels)] += value

    @classmethod
    def get_uptime_seconds(cls) -> float:
        """Returns uptime in seconds since process startup."""
        return time.time() - cls._start_time

    @classmethod
    def generate_prometheus_metrics(cls) -> str:
        """Serializes current metrics into standard Prometheus text exposition format."""
        lines = []

        # 1. System uptime
        lines.append("# HELP techdebt_uptime_seconds Total time the process has been running in seconds.")
        lines.append("# TYPE techdebt_uptime_seconds gauge")
        lines.append(f"techdebt_uptime_seconds {cls.get_uptime_seconds():.2f}")
        lines.append("")

        # 2. HTTP Requests Total
        lines.append("# HELP techdebt_http_requests_total Total number of HTTP requests received.")
        lines.append("# TYPE techdebt_http_requests_total counter")
        
        with cls._lock:
            for (name, labels), count in sorted(cls._counters.items()):
                if name == "http_requests_total":
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"techdebt_http_requests_total{{{label_str}}} {count}")
        lines.append("")

        # 3. HTTP Request Latency Averages
        lines.append("# HELP techdebt_http_request_duration_seconds_avg Average request processing latency in seconds.")
        lines.append("# TYPE techdebt_http_request_duration_seconds_avg gauge")
        with cls._lock:
            for (method, endpoint), durs in sorted(cls._latencies.items()):
                if durs:
                    avg_dur = sum(durs) / len(durs)
                    lines.append(f'techdebt_http_request_duration_seconds_avg{{method="{method}",endpoint="{endpoint}"}} {avg_dur:.4f}')
        lines.append("")

        # 4. Other custom counters (assessments, AI tokens)
        with cls._lock:
            custom_names = set(name for name, _ in cls._counters.keys() if name != "http_requests_total")
            for c_name in sorted(custom_names):
                lines.append(f"# HELP techdebt_{c_name} Metric counter {c_name}")
                lines.append(f"# TYPE techdebt_{c_name} counter")
                for (name, labels), count in sorted(cls._counters.items()):
                    if name == c_name:
                        label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                        lines.append(f"techdebt_{c_name}{{{label_str}}} {count}")
                lines.append("")

        return "\n".join(lines) + "\n"
