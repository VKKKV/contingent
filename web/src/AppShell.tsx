import { useState } from "react";
import { GitBranch, Hexagon } from "lucide-react";
import AnalysisHome from "./AnalysisHome";
import RuntimeMeter from "./RuntimeMeter";
import ParticleBackground from "./ParticleBackground";
import "./styles.css";
import "./vision.css";

export default function AppShell() {
  const [page, setPage] = useState<"vision" | "meter">("vision");
  return (
    <>
      <ParticleBackground />
      <header className="vision-shell-header">
        <button
          type="button"
          className="vision-shell-brand"
          onClick={() => setPage("vision")}
          aria-label="Contingent 目标首页"
        >
          <Hexagon size={26} />
          <strong>Contingent</strong>
        </button>
        <nav aria-label="应用导航">
          <button
            type="button"
            data-testid="nav-meter"
            aria-current={page === "meter" ? "page" : undefined}
            onClick={() => setPage("meter")}
          >
            运行仪表
          </button>
          <button
            type="button"
            data-testid="nav-vision"
            aria-current={page === "vision" ? "page" : undefined}
            onClick={() => setPage("vision")}
          >
            <GitBranch size={14} />
            情景分析
          </button>
        </nav>
        <span className="vision-shell-caption">条件分析 · 路径比较</span>
      </header>
      {page === "meter" ? <RuntimeMeter /> : <AnalysisHome />}
    </>
  );
}
