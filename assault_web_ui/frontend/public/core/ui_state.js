// =================================================
// UI_STATE
// Centralized state that controls the visual layout
// and interaction modes of the application.
// =================================================

// Exposed globally for now (simple, no framework)
window.UI_STATE = {

  // ---------------------------------------------
  // PANEL VISIBILITY AND COLLAPSE STATES
  // ---------------------------------------------
  panels: {

    // Header area (top bar)
    header: {
      visible: true
    },

    // Left RAG stack
    rag: {
      chat: {
        visible: true,
        collapsed: false
      },
      strategyReplay: {
        visible: true,
        collapsed: true
      },
      strategyRuntime: {
        visible: true,
        collapsed: true
      },
      tacticalRuntime: {
        visible: true,
        collapsed: true
      }
    },

    // Right log panel
    log: {
      visible: true
    },

    // Footer panels
    footer: {
      unitState: {
        visible: true
      },
      combat: {
        visible: true,
        popup: false   // when true, combat panel moves to overlay
      }
    }
  },

  // ---------------------------------------------
  // CAMERA STATE (used by Pixi map)
  // ---------------------------------------------
  camera: {
    zoom: 1.0,
    panX: 0,
    panY: 0,
    rotation: 0
  },

  // ---------------------------------------------
  // GLOBAL UI OPTIONS
  // ---------------------------------------------
  options: {
    animationsEnabled: true,
    audioEnabled: true,
    hoverEnabled: true
  },

  // ---------------------------------------------
  // OVERLAYS AND TEMPORARY ELEMENTS
  // ---------------------------------------------
  overlays: {
    popup: null,       // generic popup descriptor
    highlight: null    // map highlight / focus effect
  }
};