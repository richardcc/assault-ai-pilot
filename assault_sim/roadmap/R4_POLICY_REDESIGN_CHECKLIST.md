R4 CHECKLIST
- [ ] Objetivo único: mejorar vp_stepin_selection_rate con policy redesign.
- [ ] No tocar guardrails adicionales.
- [ ] Implementar cabeza explícita de selección de step-in legal (mask/head auxiliar).
- [ ] Micro-benchmark 20 episodios (seed 42):
      target: vp_stepin_selection_rate >= 0.50
- [ ] Solo si pasa micro-benchmark: subir a 120 episodios.
- [ ] Criterio kill inmediato:
      - selection_rate < 0.35 en 20 eps, o
      - vp_entry_missed_rate >= 0.92
