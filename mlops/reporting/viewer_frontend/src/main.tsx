import React, { Component, ErrorInfo, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { CatalogPage } from "./pages/CatalogPage";
import { ModelPage } from "./pages/ModelPage";
import "./styles.css";

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 24, background: "#0f172a", color: "#f87171", fontFamily: "monospace", minHeight: "100vh" }}>
          <h2>⚠️ React Error in Curriculum Reporting Viewer</h2>
          <pre style={{ background: "#1e293b", padding: 16, borderRadius: 8, whiteSpace: "pre-wrap" }}>
            {this.state.error?.stack || String(this.state.error)}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CatalogPage />} />
        <Route path="/model" element={<ModelPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

