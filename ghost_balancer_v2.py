#!/usr/bin/env python3
"""
Ghost Balancer v2 - Mejora anti-sala-de-espejos
Agrega componente Originality y penaliza recursión IA→IA
"""

import hashlib
import json
import os
import random
import time
import tempfile
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# CONFIGURACIÓN GLOBAL
# ============================================================================
REGIONS = ["LATAM", "USA", "EUROPA"]
TOTAL_TICKS = 20000
CRISIS_STARTS = [3000, 8000, 13000]
CRISIS_ENDS = [s + 1000 for s in CRISIS_STARTS]

W_MEMORY = 0.25
W_ORIGINALITY = 0.25   # Nuevo: penaliza recursión vacía
W_ANCHOR = 0.20
W_EFF = 0.15
W_CORR = 0.15

WINDOW_SIZE = 2000

# ============================================================================
# LOCIVAULT (sin cambios - ya era sólida)
# ============================================================================
class LocIVault:
    def __init__(self, vault_dir: str, identity: str):
        self.vault_dir = Path(vault_dir) / identity
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.chain_file = self.vault_dir / "chain.json"
        self._chain = self._load_chain()

    def _load_chain(self) -> List[Dict]:
        if self.chain_file.exists():
            with open(self.chain_file, "r") as f:
                return json.load(f)
        return []

    def _save_chain(self):
        with open(self.chain_file, "w") as f:
            json.dump(self._chain, f, indent=2)

    def write(self, data: bytes, metadata: Dict = None) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        nonce = os.urandom(16).hex()
        content_hash = hashlib.sha256(data).hexdigest()
        encrypted_hash = hashlib.sha256((content_hash + nonce).encode()).hexdigest()
        prev_hash = self._chain[-1]["entry_hash"] if self._chain else "0"*64
        entry = {
            "index": len(self._chain),
            "timestamp": timestamp,
            "encrypted_hash": encrypted_hash,
            "content_hash": content_hash,
            "prev_hash": prev_hash,
            "metadata": metadata or {},
            "nonce": nonce,
        }
        entry_str = json.dumps(entry, sort_keys=True)
        entry["entry_hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
        self._chain.append(entry)
        self._save_chain()
        return entry["entry_hash"]

    def verify_integrity(self) -> bool:
        for i, entry in enumerate(self._chain):
            entry_copy = entry.copy()
            entry_hash = entry_copy.pop("entry_hash")
            entry_str = json.dumps(entry_copy, sort_keys=True)
            if hashlib.sha256(entry_str.encode()).hexdigest() != entry_hash:
                return False
            if i > 0 and entry["prev_hash"] != self._chain[i-1]["entry_hash"]:
                return False
        return True

# (Mantengo CorrectionVerifier igual por brevedad - puedes copiarlo del código original)

# ============================================================================
# GHOST BALANCER v2
# ============================================================================
class GhostBalancer:
    def __init__(self, regions: List[str], window_size: int = WINDOW_SIZE):
        self.regions = regions
        self.window_size = window_size
        self.events: Dict[str, deque] = {r: deque(maxlen=window_size) for r in regions}
        self.corrections: Dict[str, List[Dict]] = {r: [] for r in regions}
        self.tick = 0
        self.last_anchor_tick: Dict[str, int] = {r: 0 for r in regions}

    def record(self, region: str, is_ok: bool, energy: float = 1.0,
               correction: bool = False, anchor: bool = False,
               correction_weight: float = 0.0, is_copied_from_agent: bool = False,
               ref_error_cycle: Optional[int] = None):
        self.tick += 1
        event = {
            "tick": self.tick,
            "is_ok": is_ok,
            "energy": energy,
            "correction": correction,
            "anchor": anchor,
            "correction_weight": correction_weight if correction else 0.0,
            "is_copied": is_copied_from_agent,
            "ref_error_cycle": ref_error_cycle
        }
        self.events[region].append(event)
        if correction and correction_weight > 0:
            self.corrections[region].append({"tick": self.tick, "weight": correction_weight})
        if anchor:
            self.last_anchor_tick[region] = self.tick

    def _originality(self, region: str) -> float:
        hist = list(self.events[region])
        if not hist:
            return 0.5
        copied = sum(1 for e in hist if e.get("is_copied", False))
        orig = 1.0 - (copied / len(hist))
        # Bonus si hay anclaje reciente
        if self.tick - self.last_anchor_tick[region] < 1000:
            orig = min(1.0, orig + 0.15)
        return max(0.0, orig)

    # (Mantengo _memory, _anchor, _efficiency, _correction similares, pero puedes ajustar)

    def karma_nuevo(self, region: str) -> float:
        m = self._memory(region)          # reutilizo tu _memory
        o = self._originality(region)     # nuevo
        a = self._anchor(region)
        e = self._efficiency(region)
        r = self._correction(region)
        return round(m * W_MEMORY + o * W_ORIGINALITY + a * W_ANCHOR + e * W_EFF + r * W_CORR, 4)

    def components(self, region: str) -> Dict[str, float]:
        return {
            "memory": self._memory(region),
            "originality": self._originality(region),
            "anchor": self._anchor(region),
            "efficiency": self._efficiency(region),
            "correction": self._correction(region)
        }

# ============================================================================
# Simulación (versión simplificada con opción multi-agente)
# ============================================================================
# ... (puedes extender la clase SimulacionIntegrada para incluir varios balancers y simular copias entre ellos)

if __name__ == "__main__":
    print("Ghost Balancer v2 cargado correctamente.")
    print("Componentes ahora incluyen 'originality' para penalizar recursión IA→IA.")
    # Aquí iría la simulación completa adaptada
