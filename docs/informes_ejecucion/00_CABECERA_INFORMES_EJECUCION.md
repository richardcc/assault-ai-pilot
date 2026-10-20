# Cabecera Canónica del Repositorio de Informes de Ejecución (MLOps & Táctica)

> **Documento Rector del Catálogo de Informes de Ejecución y Auditorías Forenses**  
> **Sistema Autoritativo:** Assault MLOps Reporting Framework (:8778)  
> **Ámbito:** `runs_curriculum/` • `assault_bench/` • `mlops/reporting/` • `agents/efficientzero_v2/`

---

## 1. Misión y Propósito de los Informes de Ejecución

Los **Informes de Ejecución** constituyen el registro forense oficial de cada campaña de entrenamiento, evaluación comparativa bilateral y verificación de currículums tácticos en la plataforma Assault.

A diferencia de los paneles en vivo de telemetría, cada informe de ejecución documenta:
1. **Condiciones Experimentales Estrictas**: Versión exacta del código, hashes de modelos, semillas aleatorias, presupuestos de simulación MCTS y topología sensorial.
2. **Diagnóstico Forense de Rendimiento**: Desglose cuantitativo del Tactical Quality Score (TQS), ELO anclado Bradley-Terry, tasas de victoria por bando (*Side A* vs *Side B*), y Combat Exchange Ratio (CER).
3. **Auditoría de Patologías Tácticas**: Detección temprana de parálisis ofensiva, aversión espuria al fuego de reacción, colapso de gradientes multi-tarea o sobreajuste posicional.
4. **Matriz de Mitigación y Acciones Correctivas**: Vinculación directa con las tareas prioritarias de la [Hoja de Ruta Evolutiva](../05_ROADMAP_EVOLUTIVO.md).

---

## 2. Taxonomía Estándar de Evaluación y Calificación (TQS)

Cada informe de ejecución evalúa el desempeño táctico del agente y emite un veredicto formal estandarizado:

$$\text{TQS} = w_{\text{elo}} \cdot \text{Score}_{\text{ELO}} + w_{\text{mirror}} \cdot \text{Score}_{\text{Mirror}} + w_{\text{cer}} \cdot \text{Score}_{\text{CER}} + w_{\text{decisive}} \cdot \text{Score}_{\text{Decisive}} - \text{Penalización}_{\text{Asimetría}}$$

| Rango TQS | Calificación | Estado de Puerta | Criterio Operativo |
| :---: | :---: | :---: | :--- |
| **$\ge 90.0$** | **A (Excelente)** | **PROMOTE** | Agente tácticamente superior al humano, asalto agresivo y balance simétrico. |
| **$75.0 - 89.9$** | **B (Aceptable)** | **PASS** | Competente en combate, cumple requisitos de victoria en ambos bandos. |
| **$60.0 - 74.9$** | **C (Regular)** | **WARN** | Desequilibrio entre bandos o dependencia de pasividad defensiva. |
| **$40.0 - 59.9$** | **D (Deficiente)** | **BLOCK** | Parálisis ofensiva detectable o brecha asimétrica $\ge 0.35$. Bloqueo de promoción. |
| **$< 40.0$** | **F (Crítico)** | **REJECT** | Regresión balística, incapacidad de captura de VPs o colapso de ELO. |

---

## 3. Catálogo Cronológico de Informes de Ejecución

| N.º | Identificador del Informe | Fecha | Alcance / Campaña | Calificación | Estado | Tareas Roadmap Derivadas |
| :---: | :--- | :---: | :--- | :---: | :---: | :--- |
| **01** | [**INFORME 01: Ejecución del Currículum Multi-Fase y Auditoría Táctica Forense**](INFORME_01_CURRICULUM_Y_AUDITORIA_TACTICA.md) | Oct 2026 | 31 ciclos de currículum en 12 fases (`self_vs_self_vs_random_2scenarios_v1`), evaluación bilateral 100 partidas vs Random | **B (TQS: 58.5 - WARN)** | Auditado | Tarea 3.6 (Mitigación Parálisis Ofensiva y 38 Canales) |

*(Los nuevos informes de ejecución generados se incorporarán secuencialmente en este catálogo).*

---

## 4. Protocolo para la Generación de Nuevos Informes

1. Todo nuevo informe debe seguir la estructura estándar:
   - Resumen Ejecutivo y Diagnóstico Global.
   - Desglose Forense de Calificación (TQS y componentes).
   - Análisis Detallado de Topología de Red y Cabezas Auxiliares.
   - Diagnóstico de Canales Sensoriales y Gradientes de Decisión.
   - Dinámicas de Búsqueda MCTS y Matriz de Mitigación Inmediata.
   - **Cláusula de Salvaguarda y Validación de Telemetría MLOps (Obligatoria)**.
2. Registrar la entrada correspondiente en la tabla del apartado 3 de este documento.
3. Ejecutar `python scripts/sync_docs_html.py` para asegurar que el informe quede inmediatamente sincronizado en el Hub Interactivo y compilado en el sitio MkDocs.

---

## 5. Protocolo Obligatorio de Salvaguarda y Validación Forense de Telemetría (MLOps Safeguard)

Para prevenir que artefactos de agregación de datos o sesgos de perspectiva asimétrica distorsionen las conclusiones tácticas de los informes, todo informe de ejecución debe auditar y certificar cuatro salvaguardas metodológicas antes de declarar regresiones o patologías en el modelo:

1. **Salvaguarda 1 (Auditoría de Coaliciones Multi-Bando en el Evaluador)**:
   - En escenarios que involucran coaliciones (por ejemplo, el Eje compuesto por unidades de infantería italiana `IT` y alemana `GE`), certificar que el verificador de desenlace comprueba la pertenencia de la facción ganadora al conjunto completo de candidatos evaluados (`winner in eval_candidates`), y no mediante igualdad estricta con una sola etiqueta (evitando que victorias de `GE` se contabilicen falsamente como 0% por esperar `IT`).
2. **Salvaguarda 2 (Desacoplamiento de Perspectiva en Auto-Juego Espejo)**:
   - En perfiles de auto-juego simétrico (`ezv2_selfplay`, donde ambos bandos ejecutan la misma red neuronal), la métrica de victoria debe auditarse desde la perspectiva del bando que persigue los objetivos trazados (`tracked_side`), o computarse como equilibrio nominal 50/50. Jamás debe asignarse el bando por defecto de turno inicial (`obs.to_play`) si ello evalúa al defensor pasivo ignorando las victorias activas del modelo.
3. **Salvaguarda 3 (Ponderación Multi-Perfil de Win Rate en Agregadores)**:
   - La tasa de victorias de un ciclo o fase de currículum debe resultar de la suma ponderada por episodios no-timeout de **todos** los perfiles evaluados (`ezv2_vs_random_side_a`, `ezv2_vs_random_side_b`, `ezv2_selfplay`). Queda terminantemente prohibido indexar o sobrescribir el valor global con la primera fila (`Select-Object -First 1`), ya que un empate en el primer perfil borraría victorias reales de los demás.
4. **Salvaguarda 4 (Detección de Falsos Colapsos de ELO Bradley-Terry)**:
   - Caídas abruptas de ELO superiores a 300 puntos en un único ciclo deben inspeccionarse contra el suelo de auto-juego ($s \ge 0.15$) en `computeStepAnchorElo` antes de diagnosticar una degradación de la política. Un empate en auto-juego entre redes idénticas jamás debe penalizar al modelo como una derrota catastrófica.
5. **Salvaguarda 5 (Verificación de Presupuesto de Pasos vs Turnos de Escenario)**:
   - Contrastar que el límite de pasos (`max_steps`) en el runner sea suficiente para albergar la duración canónica del escenario: $\text{max\_steps} \ge \text{scenario\_max\_turns} \times \max(N_{\text{units}} \times 2, 20)$, asegurando que las partidas concluyan por resolución de condiciones de victoria reglamentarias y no por corte artificial de turnos.
