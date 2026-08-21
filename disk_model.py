#!/usr/bin/env python3
"""List physical disk models currently attached to this machine."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from typing import Any


def _run_powershell(script: str) -> Any:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PowerShell 查詢失敗")
    raw = completed.stdout.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"無法解析硬碟資料：{exc}") from exc
    if isinstance(data, dict):
        return [data]
    return data


def list_disks_windows() -> list[dict[str, Any]]:
    script = r"""
$ErrorActionPreference = 'Stop'
$disks = @(Get-CimInstance -ClassName Win32_DiskDrive | ForEach-Object {
    [PSCustomObject]@{
        Index = $_.Index
        Model = $_.Model
        SerialNumber = (($_.SerialNumber -as [string]) -replace '\s+', '').Trim()
        Interface = $_.InterfaceType
        Firmware = $_.FirmwareRevision
        SizeBytes = [int64]$_.Size
        DeviceId = $_.DeviceID
        Status = $_.Status
    }
})
$physical = @{}
try {
    Get-PhysicalDisk | ForEach-Object {
        $key = (($_.SerialNumber -as [string]) -replace '\s+', '').Trim()
        if ($key) {
            $physical[$key] = $_
        }
    }
} catch {
    $physical = @{}
}
$result = foreach ($disk in $disks) {
    $match = $null
    if ($disk.SerialNumber -and $physical.ContainsKey($disk.SerialNumber)) {
        $match = $physical[$disk.SerialNumber]
    }
    [PSCustomObject]@{
        Index = $disk.Index
        Model = $disk.Model
        SerialNumber = $disk.SerialNumber
        Interface = if ($match) { $match.BusType.ToString() } else { $disk.Interface }
        MediaType = if ($match) { $match.MediaType.ToString() } else { $null }
        Health = if ($match) { $match.HealthStatus.ToString() } else { $disk.Status }
        Firmware = $disk.Firmware
        SizeBytes = $disk.SizeBytes
        DeviceId = $disk.DeviceId
    }
}
$result | ConvertTo-Json -Compress
"""
    return _run_powershell(script)


def format_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("找不到實體硬碟。")
        return

    headers = ["#", "型號", "媒體", "介面", "容量", "序號", "健康狀態"]
    table: list[list[str]] = []
    for row in sorted(rows, key=lambda item: item.get("Index") or 0):
        table.append(
            [
                str(row.get("Index", "")),
                str(row.get("Model") or "-").strip(),
                str(row.get("MediaType") or "-"),
                str(row.get("Interface") or "-"),
                format_size(row.get("SizeBytes")),
                str(row.get("SerialNumber") or "-"),
                str(row.get("Health") or "-"),
            ]
        )

    widths = [len(h) for h in headers]
    for line in table:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], len(cell))

    def fmt(cols: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cols))

    print(fmt(headers))
    print("  ".join("-" * w for w in widths))
    for line in table:
        print(fmt(line))


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_stdio()
    system = platform.system()
    if system != "Windows":
        print(f"目前只支援 Windows，偵測到的系統是 {system}。", file=sys.stderr)
        return 1
    try:
        disks = list_disks_windows()
    except Exception as exc:
        print(f"讀取硬碟資訊失敗：{exc}", file=sys.stderr)
        return 1
    print_table(disks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
