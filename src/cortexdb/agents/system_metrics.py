"""
System Metrics Agent — Monitors CPU, memory, disk, and network in real-time.
Feeds both the Monitoring and Hardware dashboard pages.
"""

import time
import random
import logging
import platform
from typing import Dict, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not available — using simulated system metrics")


@dataclass
class SystemSnapshot:
    timestamp: float
    cpu_usage: float
    cpu_cores: int
    cpu_freq_mhz: float
    memory_total_gb: float
    memory_used_gb: float
    memory_pct: float
    disk_total_gb: float
    disk_used_gb: float
    disk_pct: float
    disk_read_mb_s: float
    disk_write_mb_s: float
    net_sent_mb_s: float
    net_recv_mb_s: float
    net_connections: int
    load_avg_1m: float
    load_avg_5m: float
    load_avg_15m: float
    uptime_seconds: float
    process_count: int
    swap_total_gb: float
    swap_used_gb: float
    temperatures: Dict = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["temperatures"] = self.temperatures or {}
        return d


class SystemMetricsAgent:
    """Real-time system metrics collection agent."""

    def __init__(self):
        self._history: List[SystemSnapshot] = []
        self._max_history = 360  # 1 hour at 10s intervals
        self._last_net = None
        self._last_disk = None
        self._last_ts = 0
        self._boot_time = time.time()
        # Seed baseline for simulation
        self._sim_base = {
            "cpu": 28 + random.uniform(-5, 10),
            "mem_pct": 58 + random.uniform(-5, 5),
        }

    def collect(self) -> dict:
        """Collect current system metrics snapshot."""
        if HAS_PSUTIL:
            snap = self._collect_real()
        else:
            snap = self._collect_simulated()

        self._history.append(snap)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return snap.to_dict()

    def _collect_real(self) -> SystemSnapshot:
        now = time.time()
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        swap = psutil.swap_memory()
        net = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()

        # Calculate rates
        dt = now - self._last_ts if self._last_ts > 0 else 1
        net_sent_rate = 0
        net_recv_rate = 0
        disk_read_rate = 0
        disk_write_rate = 0

        if self._last_net:
            net_sent_rate = (net.bytes_sent - self._last_net.bytes_sent) / dt / 1024 / 1024
            net_recv_rate = (net.bytes_recv - self._last_net.bytes_recv) / dt / 1024 / 1024
        if self._last_disk:
            disk_read_rate = (disk_io.read_bytes - self._last_disk.read_bytes) / dt / 1024 / 1024
            disk_write_rate = (disk_io.write_bytes - self._last_disk.write_bytes) / dt / 1024 / 1024

        self._last_net = net
        self._last_disk = disk_io
        self._last_ts = now

        # Temperatures (may not be available on all platforms)
        temps = {}
        try:
            t = psutil.sensors_temperatures()
            for name, entries in (t or {}).items():
                temps[name] = entries[0].current if entries else 0
        except (AttributeError, Exception):
            pass

        try:
            load = psutil.getloadavg()
        except (AttributeError, OSError):
            load = (cpu / 100 * psutil.cpu_count(), 0, 0)

        return SystemSnapshot(
            timestamp=now,
            cpu_usage=round(cpu, 1),
            cpu_cores=psutil.cpu_count(logical=True),
            cpu_freq_mhz=round(psutil.cpu_freq().current if psutil.cpu_freq() else 0, 0),
            memory_total_gb=round(mem.total / 1073741824, 2),
            memory_used_gb=round(mem.used / 1073741824, 2),
            memory_pct=round(mem.percent, 1),
            disk_total_gb=round(disk.total / 1073741824, 2),
            disk_used_gb=round(disk.used / 1073741824, 2),
            disk_pct=round(disk.percent, 1),
            disk_read_mb_s=round(max(0, disk_read_rate), 2),
            disk_write_mb_s=round(max(0, disk_write_rate), 2),
            net_sent_mb_s=round(max(0, net_sent_rate), 2),
            net_recv_mb_s=round(max(0, net_recv_rate), 2),
            net_connections=len(psutil.net_connections()),
            load_avg_1m=round(load[0], 2),
            load_avg_5m=round(load[1], 2),
            load_avg_15m=round(load[2], 2),
            uptime_seconds=round(now - psutil.boot_time(), 0),
            process_count=len(psutil.pids()),
            swap_total_gb=round(swap.total / 1073741824, 2),
            swap_used_gb=round(swap.used / 1073741824, 2),
            temperatures=temps,
        )

    def _collect_simulated(self) -> SystemSnapshot:
        now = time.time()
        # Realistic drifting simulation
        self._sim_base["cpu"] += random.uniform(-3, 3)
        self._sim_base["cpu"] = max(5, min(95, self._sim_base["cpu"]))
        self._sim_base["mem_pct"] += random.uniform(-1, 1)
        self._sim_base["mem_pct"] = max(30, min(90, self._sim_base["mem_pct"]))

        cpu = round(self._sim_base["cpu"] + random.uniform(-5, 5), 1)
        mem_pct = round(self._sim_base["mem_pct"], 1)
        total_mem = 32.0
        total_disk = 500.0
        disk_pct = 45 + random.uniform(-2, 2)

        return SystemSnapshot(
            timestamp=now,
            cpu_usage=max(1, min(100, cpu)),
            cpu_cores=8,
            cpu_freq_mhz=3600,
            memory_total_gb=total_mem,
            memory_used_gb=round(total_mem * mem_pct / 100, 2),
            memory_pct=mem_pct,
            disk_total_gb=total_disk,
            disk_used_gb=round(total_disk * disk_pct / 100, 2),
            disk_pct=round(disk_pct, 1),
            disk_read_mb_s=round(random.uniform(5, 80), 2),
            disk_write_mb_s=round(random.uniform(2, 40), 2),
            net_sent_mb_s=round(random.uniform(1, 25), 2),
            net_recv_mb_s=round(random.uniform(2, 50), 2),
            net_connections=random.randint(80, 300),
            load_avg_1m=round(cpu / 100 * 8 + random.uniform(-0.5, 0.5), 2),
            load_avg_5m=round(cpu / 100 * 8 * 0.8 + random.uniform(-0.3, 0.3), 2),
            load_avg_15m=round(cpu / 100 * 8 * 0.6 + random.uniform(-0.2, 0.2), 2),
            uptime_seconds=round(now - self._boot_time + 86400 * 14, 0),
            process_count=random.randint(180, 260),
            swap_total_gb=8.0,
            swap_used_gb=round(random.uniform(0.1, 1.5), 2),
            temperatures={"cpu": round(45 + random.uniform(-5, 15), 1)},
        )

    def get_current(self) -> dict:
        if self._history:
            return self._history[-1].to_dict()
        return self.collect()

    def get_history(self, minutes: int = 30) -> List[dict]:
        cutoff = time.time() - minutes * 60
        return [s.to_dict() for s in self._history if s.timestamp >= cutoff]

    def get_hardware_summary(self) -> dict:
        current = self.get_current()
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "python_version": platform.python_version(),
            "cpu": {
                "cores": current["cpu_cores"],
                "frequency_mhz": current["cpu_freq_mhz"],
                "usage_pct": current["cpu_usage"],
                "load_1m": current["load_avg_1m"],
                "load_5m": current["load_avg_5m"],
                "load_15m": current["load_avg_15m"],
            },
            "memory": {
                "total_gb": current["memory_total_gb"],
                "used_gb": current["memory_used_gb"],
                "usage_pct": current["memory_pct"],
            },
            "disk": {
                "total_gb": current["disk_total_gb"],
                "used_gb": current["disk_used_gb"],
                "usage_pct": current["disk_pct"],
                "read_mb_s": current["disk_read_mb_s"],
                "write_mb_s": current["disk_write_mb_s"],
            },
            "network": {
                "sent_mb_s": current["net_sent_mb_s"],
                "recv_mb_s": current["net_recv_mb_s"],
                "connections": current["net_connections"],
            },
            "swap": {
                "total_gb": current["swap_total_gb"],
                "used_gb": current["swap_used_gb"],
            },
            "temperatures": current.get("temperatures", {}),
            "uptime_seconds": current["uptime_seconds"],
            "process_count": current["process_count"],
        }
