"""
tools/health_reporter.py
────────────────────────
Generates periodic system health summaries.
Called by the TaskScheduler and/or on-demand from AgentLoop.
"""

from __future__ import annotations
import platform
from datetime import datetime

import psutil
from loguru import logger


def get_health_report() -> dict:
    """Collect system metrics and return as a dict."""
    cpu = psutil.cpu_percent(interval=1)
    vm  = psutil.virtual_memory()
    disk= psutil.disk_usage("/")

    top_procs = sorted(
        psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
        key=lambda p: p.info.get("cpu_percent") or 0,
        reverse=True,
    )[:5]

    report = {
        "timestamp":     datetime.now().isoformat(),
        "platform":      platform.platform(),
        "cpu_percent":   cpu,
        "ram_percent":   vm.percent,
        "ram_used_gb":   round(vm.used / 1e9, 2),
        "ram_total_gb":  round(vm.total / 1e9, 2),
        "disk_percent":  disk.percent,
        "disk_free_gb":  round(disk.free / 1e9, 2),
        "top_processes": [
            {"name": p.info["name"],
             "cpu":  round(p.info.get("cpu_percent") or 0, 1),
             "ram":  round(p.info.get("memory_percent") or 0, 1)}
            for p in top_procs
            if p.info.get("name")
        ],
    }
    return report


def format_health_speech(report: dict) -> str:
    """Format report as a short TTS-friendly string."""
    return (
        f"System report: CPU at {report['cpu_percent']:.0f} percent, "
        f"RAM at {report['ram_percent']:.0f} percent, "
        f"Disk {report['disk_percent']:.0f} percent used. "
        f"{report['disk_free_gb']:.1f} gigabytes free."
    )


def log_health() -> None:
    """Convenience function for use in TaskScheduler."""
    report = get_health_report()
    logger.info("Health report: CPU={}% RAM={}% Disk={}%",
                report["cpu_percent"],
                report["ram_percent"],
                report["disk_percent"])
