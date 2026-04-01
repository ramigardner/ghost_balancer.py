class GhostWithFatality:
    """Ghost que puede ejecutar fatality restaurando desde ciclos limpios"""
    
    def __init__(self, caja_negra_path: str):
        self.caja_negra_path = caja_negra_path
        self.clean_cycles_cache = {}  # cache de ciclos limpios por región
    
    def evaluate_and_act(self, ghost_balancer, current_cycle: CycleSnapshot) -> List[dict]:
        """Evalúa el ciclo actual y ejecuta acciones (incluyendo fatality)"""
        interventions = []
        
        for region, snapshot in current_cycle.region_snapshots.items():
            # Obtener historial de ciclos anteriores
            history = self._get_region_history(region, cycles_back=10)
            
            # Decidir acción con fatality
            action = self._decide_action_with_fatality(region, snapshot, history, ghost_balancer)
            
            if action:
                intervention = self._execute_action(
                    region, action, snapshot, history, ghost_balancer
                )
                interventions.append(intervention)
        
        return interventions
    
    def _decide_action_with_fatality(self, region: str, current: dict, 
                                      history: List[dict], ghost_balancer) -> Optional[str]:
        """Decide acción incluyendo fatality basado en ciclos históricos"""
        
        # Nivel 1: Degradación leve → cooling suave
        if current['temperature'] > 0.6 and current['ghost_score'] > 0.3:
            return "cooling_light"
        
        # Nivel 2: Temperatura alta persistente (2+ ciclos) → cooling intenso
        if len(history) >= 2:
            recent_temps = [h['temperature'] for h in history[-2:]]
            if all(t > 0.7 for t in recent_temps) and current['temperature'] > 0.7:
                return "cooling_intense"
        
        # NIVEL 3: FATALITY - condiciones severas
        # 3a: Ghost Score colapsado (< 0.2) por 3+ ciclos consecutivos
        if len(history) >= 3:
            recent_scores = [h['ghost_score'] for h in history[-3:]]
            if all(s < 0.2 for s in recent_scores) and current['ghost_score'] < 0.2:
                return "fatality_score_collapse"
        
        # 3b: Temperatura extremadamente alta (> 0.9) por 2+ ciclos
        if len(history) >= 2:
            recent_temps = [h['temperature'] for h in history[-2:]]
            if all(t > 0.9 for t in recent_temps) and current['temperature'] > 0.9:
                return "fatality_overheating"
        
        # 3c: Coherencia crítica (< 0.3) por 3+ ciclos
        if len(history) >= 3:
            recent_coherence = [h['coherence_score'] for h in history[-3:]]
            if all(c < 0.3 for c in recent_coherence) and current['coherence_score'] < 0.3:
                return "fatality_incoherence"
        
        # 3d: Múltiples intervenciones previas sin mejora
        recent_interventions = self._count_recent_interventions(region, cycles=5)
        if recent_interventions >= 3 and current['temperature'] > 0.5:
            return "fatality_stuck"
        
        # Nivel 4: Restauración preventiva (menos agresiva)
        if len(history) >= 5:
            # Si la región ha estado degradada la mayoría del tiempo
            degraded_cycles = sum(1 for h in history[-5:] if h['temperature'] > 0.5)
            if degraded_cycles >= 4 and current['ghost_score'] < 0.5:
                return "restore_from_clean"
        
        return None
    
    def _execute_action(self, region: str, action: str, current: dict,
                        history: List[dict], ghost_balancer) -> dict:
        """Ejecuta acción incluyendo fatality (restauración)"""
        
        if action.startswith("cooling"):
            # Cooling suave o intenso: ajustar decay_rate temporalmente
            intensity = 0.5 if "intense" in action else 0.2
            return self._apply_cooling(region, intensity, ghost_balancer)
        
        elif action.startswith("fatality"):
            # FATALITY: restaurar desde ciclo limpio
            clean_cycle = self._find_clean_cycle(region, history)
            if clean_cycle:
                return self._apply_fatality(region, clean_cycle, ghost_balancer, action)
            else:
                # No se encontró ciclo limpio → restaurar a kernel fundacional
                return self._apply_fatality_to_kernel(region, ghost_balancer, action)
        
        elif action == "restore_from_clean":
            # Restauración preventiva (menos agresiva que fatality)
            clean_cycle = self._find_last_clean_cycle(region, history)
            if clean_cycle:
                return self._apply_restore(region, clean_cycle, ghost_balancer)
        
        return {"region": region, "action": action, "status": "no_op"}
    
    def _find_clean_cycle(self, region: str, history: List[dict]) -> Optional[dict]:
        """Encuentra el último ciclo limpio para una región"""
        # Buscar desde el más reciente hacia atrás
        for cycle in reversed(history):
            if (cycle['temperature'] < 0.3 and 
                cycle['ghost_score'] > 0.8 and 
                cycle['coherence_score'] > 0.9):
                return cycle
        return None
    
    def _find_last_clean_cycle(self, region: str, history: List[dict]) -> Optional[dict]:
        """Encuentra el último ciclo limpio (menos estricto)"""
        for cycle in reversed(history):
            if cycle['temperature'] < 0.5 and cycle['ghost_score'] > 0.6:
                return cycle
        return None
    
    def _apply_fatality(self, region: str, clean_cycle: dict, 
                        ghost_balancer, reason: str) -> dict:
        """
        FATALITY: restaura región a estado de ciclo limpio.
        Esto es irreversible y drástico.
        """
        # 1. Registrar la fatality en el libro de personalidad
        # 2. Restaurar configuración del Ghost Balancer para esta región
        # 3. Forzar reset de eventos
        # 4. Opcional: notificar a humanos
        
        # Simulación de restauración
        ghost_balancer.events[region] = clean_cycle.get('window_events', [])
        
        # Si hay métricas de ASPR, restaurar también
        if 'active_clusters' in clean_cycle:
            # Llamar a ASPR para restaurar estructura
            pass
        
        return {
            "region": region,
            "action": "fatality",
            "reason": reason,
            "restored_to_cycle": clean_cycle.get('cycle_number', 'unknown'),
            "temperature_before": ghost_balancer._compute_temperature(ghost_balancer.events[region]),
            "status": "executed"
        }
    
    def _apply_fatality_to_kernel(self, region: str, ghost_balancer, reason: str) -> dict:
        """Fatality extrema: restaurar a kernel fundacional"""
        # Reset completo: limpiar todos los eventos
        ghost_balancer.events[region] = []
        
        return {
            "region": region,
            "action": "fatality_kernel",
            "reason": reason,
            "status": "executed_kernel_restore"
        }
    
    def _apply_cooling(self, region: str, intensity: float, ghost_balancer) -> dict:
        """Aplica cooling ajustando parámetros"""
        # Guardar decay_rate original si es necesario
        original_decay = getattr(ghost_balancer, 'decay_rate', 0.2)
        
        # Aumentar decay_rate temporalmente para ser más sensible a mejoras
        # (esto es simplificado; en implementación real se ajustaría el algoritmo)
        
        return {
            "region": region,
            "action": "cooling",
            "intensity": intensity,
            "status": "applied"
        }
    
    def _apply_restore(self, region: str, clean_cycle: dict, ghost_balancer) -> dict:
        """Restauración preventiva (menos agresiva que fatality)"""
        # Similar a fatality pero con menor impacto
        ghost_balancer.events[region] = clean_cycle.get('window_events', [])
        
        return {
            "region": region,
            "action": "restore",
            "restored_to_cycle": clean_cycle.get('cycle_number', 'unknown'),
            "status": "executed"
        }
    
    def _get_region_history(self, region: str, cycles_back: int) -> List[dict]:
        """Obtiene historial de ciclos para una región desde Caja Negra"""
        history = []
        # Implementación que lee ciclos desde Caja Negra
        # ...
        return history
    
    def _count_recent_interventions(self, region: str, cycles: int) -> int:
        """Cuenta intervenciones recientes en ciclos"""
        # Implementación que lee libro de personalidad
        # ...
        return 0
