# 🚀 ASSAULT AI UI — ROADMAP COMPLETO

---

# 🧭 VISIÓN

Construir un sistema completo:

- 🎮 Jugar vs AI (RL vs usuario)
- 🔁 Visualizar replays
- 🧠 Explainability (HRL + decisiones)
- 🤖 RAG Assistant flotante

---

# 🧱 ARQUITECTURA FINAL

## Backend
- Engine Assault (YA LO TIENES ✅)
- API REST:
  - /game/start
  - /game/state
  - /game/action
  - /game/actions
  - /explain
  - /rag/query

## Frontend
- React + TypeScript + Vite
- PixiJS (mapa)
- React UI (paneles)

---

# 📅 FASE 0 — ENTORNO ✅ (YA HECHO)

✅ Vite funcionando  
✅ React + TypeScript  
✅ npm run dev  

---

# 🚧 FASE 1 — BASE REAL (CRÍTICA)

## 🎯 Objetivo:
Mostrar un mapa básico en pantalla con Pixi

---

## ✅ Tareas

### 1. Crear GameCanvas
Archivo:
src/GameCanvas.tsx

- contenedor Pixi
- montar canvas
- fondo visible

---

### 2. Instalar PixiJS

```bash
npm install pixi.js