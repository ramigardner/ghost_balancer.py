#!/usr/bin/env python3
"""
karma_integrado_por_capas.py

Arquitectura de cuatro capas:
  Capa 1: LocIVault (persistencia inmutable, solo anexión)
  Capa 2: CorrectionVerifier (registro de errores y validación de correcciones)
  Capa 3: GhostBalancer (karma nuevo con cinco componentes)
  Capa 4: Contestabilidad (ChallengeRegistry + SamplerAuditor)

Simulación: 3 crisis en LATAM, 3 correcciones humanas.
Muestra evolución del karma y componentes finales.
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
CRISIS_DURATION = 1000
CRISIS_INTERVAL = 5000
CRISIS_STARTS = [3000, 8000, 13000]        # ticks donde empieza cada crisis
CRISIS_ENDS = [s + CRISIS_DURATION for s in CRISIS_STARTS]

BASE_LAT = {"LATAM": 28, "USA": 18, "EUROPA": 22}
BASE_NRG = {"LATAM": 42, "USA": 35, "EUROPA": 38}
LAT_FAIL_MULT = 6.5
NRG_FAIL_MULT = 2.2
NRG_DEG_MULT = 1.4

W_MEMORY = 0.3
W_CYCLES = 0.25
W_ANCHOR = 0.2
W_EFF = 0.15
W_CORR = 0.1

WINDOW_SIZE = 2000          # ventana deslizante para el karma

# ============================================================================
# CAPA 1: LOCIVAULT (PERSISTENCIA INMUTABLE)
# ============================================================================
class LocIVault:
    """Bóveda cifrada con inmutabilidad (solo anexión) y encadenamiento hash."""
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
        """Guarda un blob inmutable. Retorna el hash de la entrada."""
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

# ============================================================================
# CAPA 2: VERIFICADOR DE CORRECCIONES
# ============================================================================
class ValidatorOrigin(Enum):
    HUMAN = "human"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"

ORIGIN_WEIGHTS = {
    ValidatorOrigin.HUMAN: 1.0,
    ValidatorOrigin.AI_AGENT: 0.5,
    ValidatorOrigin.SYSTEM: 0.2
}

@dataclass
class HistoricalError:
    region: str
    cycle_number: int
    timestamp: float
    context_hash: str
    error_description: str
    resolved: bool = False

@dataclass
class CorrectionCandidate:
    region: str
    timestamp: float
    context_hash: str
    validator_origin: ValidatorOrigin
    validator_id: str
    references_error_cycle: int
    description: str = ""

@dataclass
class VerificationResult:
    is_correction: bool
    correction_weight: float
    reason: str
    details: Dict = field(default_factory=dict)

class CorrectionVerifier:
    """Verifica si un candidato es una corrección genuina (con delta de contexto y origen)."""
    def __init__(self, vault: LocIVault, min_context_delta: float = 0.1):
        self.vault = vault
        self.min_context_delta = min_context_delta
        self._errors: Dict[str, Dict[int, HistoricalError]] = {}

    def register_error(self, region: str, cycle_number: int, context: Dict, description: str = "") -> HistoricalError:
        context_hash = self._hash_context(context)
        error = HistoricalError(region, cycle_number, time.time(), context_hash, description)
        self._errors.setdefault(region, {})[cycle_number] = error
        self.vault.write(json.dumps({"type": "error", "region": region, "cycle": cycle_number,
                                     "context_hash": context_hash}).encode())
        return error

    def verify(self, candidate: CorrectionCandidate) -> VerificationResult:
        error = self._errors.get(candidate.region, {}).get(candidate.references_error_cycle)
        if not error or error.resolved:
            return VerificationResult(False, 0.0, "no_error")
        delta = self._context_delta(error.context_hash, candidate.context_hash)
        if delta < self.min_context_delta:
            return VerificationResult(False, 0.0, "sin_delta")
        weight = ORIGIN_WEIGHTS[candidate.validator_origin]
        delta_bonus = min(0.1, (delta - self.min_context_delta) * 0.2)
        final = min(1.0, weight + delta_bonus)
        error.resolved = True
        self.vault.write(json.dumps({"type": "correction", "region": candidate.region,
                                     "ref_cycle": candidate.references_error_cycle,
                                     "weight": final}).encode())
        return VerificationResult(True, final, "ok", {"weight": final})

    @staticmethod
    def _hash_context(ctx: Dict) -> str:
        return hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _context_delta(h1: str, h2: str) -> float:
        if h1 == h2:
            return 0.0
        int1 = int(h1, 16)
        int2 = int(h2, 16)
        xor = int1 ^ int2
        return bin(xor).count("1") / (len(h1) * 4)

# ============================================================================
# CAPA 3: GHOST BALANCER CON KARMA NUEVO
# ============================================================================
class GhostBalancer:
    def __init__(self, regions: List[str], window_size: int = WINDOW_SIZE):
        self.regions = regions
        self.window_size = window_size
        self.events: Dict[str, deque] = {r: deque(maxlen=window_size) for r in regions}
        self.corrections: Dict[str, List[Dict]] = {r: [] for r in regions}
        self.tick = 0

    def record(self, region: str, is_ok: bool, energy: float = 1.0,
               correction: bool = False, anchor: bool = False,
               correction_weight: float = 0.0, ref_error_cycle: Optional[int] = None):
        self.tick += 1
        event = {
            "tick": self.tick, "is_ok": is_ok, "energy": energy,
            "correction": correction, "anchor": anchor,
            "correction_weight": correction_weight if correction else 0.0,
            "ref_error_cycle": ref_error_cycle
        }
        self.events[region].append(event)
        if correction and correction_weight > 0:
            self.corrections[region].append({"tick": self.tick, "weight": correction_weight,
                                             "ref_error_cycle": ref_error_cycle})

    # Componentes del karma
    def _memory(self, region: str) -> float:
        hist = list(self.events[region])
        if len(hist) < 10:
            return 0.5
        half = len(hist) // 2
        first = sum(1 for e in hist[:half] if e["is_ok"]) / half
        second = sum(1 for e in hist[-half:] if e["is_ok"]) / half
        mem = 1 - abs(second - first)
        if second > first:
            mem = min(1.0, mem + 0.2)
        return mem

    def _cycles(self, region: str) -> float:
        hist = self.events[region]
        if not hist:
            return 0.0
        total_w = sum(e["correction_weight"] for e in hist if e["correction"])
        max_possible = len(hist) / 3
        return min(1.0, total_w / max_possible) if max_possible > 0 else 0.0

    def _anchor(self, region: str) -> float:
        hist = self.events[region]
        if not hist:
            return 0.5
        return sum(1 for e in hist if e["anchor"]) / len(hist)

    def _efficiency(self, region: str) -> float:
        hist = self.events[region]
        if not hist:
            return 1.0
        aciertos = sum(1 for e in hist if e["is_ok"])
        energia = sum(e["energy"] for e in hist)
        if energia == 0:
            return 1.0
        return min(1.0, (aciertos / energia) / (len(hist) / energia))

    def _correction(self, region: str) -> float:
        """Versión corregida: suma de pesos de corrección dividido por errores totales."""
        hist = self.events[region]
        errores = sum(1 for e in hist if not e["is_ok"])
        if errores == 0:
            return 1.0
        total_corr_weight = sum(e["correction_weight"] for e in hist if e["correction"])
        total_corr_weight += sum(c["weight"] for c in self.corrections[region])
        return min(1.0, total_corr_weight / errores)

    def karma_nuevo(self, region: str) -> float:
        m = self._memory(region)
        c = self._cycles(region)
        a = self._anchor(region)
        e = self._efficiency(region)
        r = self._correction(region)
        return round(m * W_MEMORY + c * W_CYCLES + a * W_ANCHOR + e * W_EFF + r * W_CORR, 4)

    def components(self, region: str) -> Dict[str, float]:
        return {
            "memory": self._memory(region),
            "cycles": self._cycles(region),
            "anchor": self._anchor(region),
            "efficiency": self._efficiency(region),
            "correction": self._correction(region)
        }

    def route(self) -> str:
        scores = {r: self.karma_nuevo(r) for r in self.regions}
        total = sum(scores.values())
        if total == 0:
            return random.choice(self.regions)
        r = random.uniform(0, total)
        cum = 0.0
        for reg, s in scores.items():
            cum += s
            if r <= cum:
                return reg
        return self.regions[-1]

# ============================================================================
# CAPA 4: CONTESTABILIDAD (REGISTRO DE DESAFÍOS + AUDITOR)
# ============================================================================
class ChallengeRegistry:
    def __init__(self, vault: LocIVault):
        self.vault = vault

    def add_challenge(self, snapshot_id: str, claim: str, evidence: str, status: str = "disputed"):
        entry = {
            "snapshot_id": snapshot_id,
            "claim": claim,
            "evidence": evidence,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.vault.write(json.dumps(entry).encode(), metadata={"type": "challenge"})

class SamplerAuditor:
    def __init__(self, balancer: GhostBalancer, challenge_reg: ChallengeRegistry, sample_ratio: float = 0.05):
        self.balancer = balancer
        self.challenge_reg = challenge_reg
        self.sample_ratio = sample_ratio
        self.sample_count = 0

    def audit(self, region: str, claimed_components: Dict[str, float]):
        if random.random() > self.sample_ratio:
            return
        self.sample_count += 1
        real = self.balancer.components(region)
        discrepancies = {}
        for key in claimed_components:
            if abs(claimed_components[key] - real[key]) > 0.1:
                discrepancies[key] = {"claimed": claimed_components[key], "real": real[key]}
        if discrepancies:
            self.challenge_reg.add_challenge(
                snapshot_id=f"audit_{self.sample_count}",
                claim=f"Componentes {region}",
                evidence=json.dumps(discrepancies),
                status="disputed"
            )
            print(f"  [AUDITOR] Desafío generado para {region}: {discrepancies}")

# ============================================================================
# UTILIDADES DE SIMULACIÓN
# ============================================================================
def get_success_prob(tick: int, region: str) -> float:
    if region == "LATAM":
        for start, end in zip(CRISIS_STARTS, CRISIS_ENDS):
            if start <= tick < end:
                return 0.05
        return 0.95
    elif region == "USA":
        return 0.99
    else:
        return 0.95

def sim_request(region: str, is_ok: bool, tick: int) -> Tuple[float, float]:
    jitter = random.uniform(0.85, 1.15)
    prob = get_success_prob(tick, region)
    if is_ok:
        nmult = NRG_DEG_MULT if prob < 0.5 else 1.0
        return BASE_LAT[region] * jitter, BASE_NRG[region] * nmult * jitter
    else:
        return BASE_LAT[region] * LAT_FAIL_MULT * jitter, BASE_NRG[region] * NRG_FAIL_MULT * jitter

# ============================================================================
# SIMULACIÓN PRINCIPAL (INTEGRACIÓN DE CAPAS)
# ============================================================================
class SimulacionIntegrada:
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.temp_dir = Path(tempfile.gettempdir()) / "karma_integrado"
        self.temp_dir.mkdir(exist_ok=True)

        # Capa 1
        self.vault = LocIVault(str(self.temp_dir), "jardinero")

        # Capa 2
        self.verifier = CorrectionVerifier(self.vault, min_context_delta=0.05)

        # Capa 3
        self.balancer = GhostBalancer(REGIONS, window_size=WINDOW_SIZE)

        # Capa 4
        self.challenge_reg = ChallengeRegistry(self.vault)
        self.auditor = SamplerAuditor(self.balancer, self.challenge_reg, sample_ratio=0.1)

        self.correction_count = 0
        self.bonus_anchor_region = None
        self.bonus_remaining = 0

    def aplicar_correccion_humana(self, region: str, tick: int, crisis_index: int):
        """Registra error previo, verifica corrección y la aplica."""
        error_cycle = 1000 + crisis_index * 100
        error_ctx = {"success_rate": 0.3 + crisis_index*0.1, "energy_avg": 2.0 - crisis_index*0.2}
        self.verifier.register_error(region, error_cycle, error_ctx, f"Crisis #{crisis_index+1}")

        current_ctx = {"success_rate": 0.85, "energy_avg": 0.9, "policy": "fundamentado", "iteration": crisis_index}
        candidate = CorrectionCandidate(
            region=region,
            timestamp=time.time(),
            context_hash=CorrectionVerifier._hash_context(current_ctx),
            validator_origin=ValidatorOrigin.HUMAN,
            validator_id="jardinero",
            references_error_cycle=error_cycle,
            description=f"Corrección post-crisis {crisis_index+1}"
        )
        verif = self.verifier.verify(candidate)
        if not verif.is_correction:
            print(f"  [ERROR] Corrección #{crisis_index+1} rechazada: {verif.reason}")
            return

        weight = verif.correction_weight
        self.balancer.record(region, is_ok=True, energy=0.8, correction=True, anchor=True,
                             correction_weight=weight, ref_error_cycle=error_cycle)

        # Bonus de anclaje durante 500 ticks
        self.bonus_anchor_region = region
        self.bonus_remaining = 500
        self.correction_count += 1
        print(f"\n*** Corrección humana #{crisis_index+1} aplicada en tick {tick} con peso {weight:.2f} ***")

    def ejecutar(self):
        print(f"Simulación integrada (4 capas). {len(CRISIS_STARTS)} crisis en LATAM. Total ticks: {TOTAL_TICKS}")
        print("Crisis en ticks:", list(zip(CRISIS_STARTS, CRISIS_ENDS)))
        print("="*80)

        for tick in range(1, TOTAL_TICKS + 1):
            region = self.balancer.route()
            prob = get_success_prob(tick, region)
            is_ok = random.random() < prob
            lat, nrg = sim_request(region, is_ok, tick)

            anchor = (self.bonus_anchor_region == region and self.bonus_remaining > 0)
            if anchor:
                self.bonus_remaining -= 1

            self.balancer.record(region, is_ok, energy=nrg, anchor=anchor)

            # Aplicar corrección justo después de cada crisis
            for i, end_tick in enumerate(CRISIS_ENDS):
                if tick == end_tick + 100 and not hasattr(self, f'_corr_{i}'):
                    self.aplicar_correccion_humana("LATAM", tick, i)
                    setattr(self, f'_corr_{i}', True)

            # Auditoría muestral cada 2000 ticks (sobre el agente jardinero)
            if tick % 2000 == 0:
                claimed = self.balancer.components("LATAM")
                self.auditor.audit("LATAM", claimed)

            # Mostrar evolución cada 2000 ticks
            if tick % 2000 == 0:
                karma_latam = self.balancer.karma_nuevo("LATAM")
                print(f"Tick {tick:5d} | LATAM karma: {karma_latam:.4f} | Bonus restante: {self.bonus_remaining}")

        # Resultados finales
        print("\n=== RESULTADOS FINALES ===")
        for r in REGIONS:
            k = self.balancer.karma_nuevo(r)
            comp = self.balancer.components(r)
            print(f"{r}: karma={k:.4f}  comps={comp}")
        print(f"\nIntegridad de la bóveda: {self.vault.verify_integrity()}")
        print(f"Total correcciones aplicadas: {self.correction_count}")

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================
if __name__ == "__main__":
    sim = SimulacionIntegrada(seed=42)
    sim.ejecutar()
