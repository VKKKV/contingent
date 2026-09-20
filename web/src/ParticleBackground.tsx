import { useEffect, useRef } from "react";
import type { Engine } from "@tsparticles/engine";
import { particleOptions, startParticleBackground } from "./particleOptions";

let engineReady: Promise<Engine> | undefined;
let nextInstance = 0;

function loadEngine(): Promise<Engine> {
  engineReady ??= Promise.all([
    import("@tsparticles/engine"),
    import("@tsparticles/slim"),
  ])
    .then(async ([{ tsParticles }, { loadSlim }]) => {
      await loadSlim(tsParticles, false);
      return tsParticles;
    })
    .catch((error: unknown) => {
      engineReady = undefined;
      throw error;
    });
  return engineReady;
}

export default function ParticleBackground() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element || typeof window.matchMedia !== "function") return;
    return startParticleBackground({
      motion: window.matchMedia("(prefers-reduced-motion: reduce)"),
      visibility: document,
      setVisible: (visible) => {
        element.style.visibility = visible ? "visible" : "hidden";
      },
      load: async (signal) => {
        const engine = await loadEngine();
        if (signal.aborted) return;
        // A fresh host AND engine id per load isolates StrictMode and motion toggles.
        const mount = document.createElement("div");
        mount.id = `instrument-particles-${++nextInstance}`;
        mount.style.width = "100%";
        mount.style.height = "100%";
        element.append(mount);
        const remove = () => mount.remove();
        signal.addEventListener("abort", remove, { once: true });
        try {
          const container = await engine.load({
            id: mount.id,
            element: mount,
            options: particleOptions,
          });
          if (!container) remove();
          return container;
        } catch (error) {
          // load() registers its container before asynchronous initialization.
          engine.items
            .find((container) => container.id.description === mount.id)
            ?.destroy();
          remove();
          signal.removeEventListener("abort", remove);
          throw error;
        }
      },
    });
  }, []);

  return (
    <div
      ref={host}
      id="instrument-particles"
      className="instrument-particles"
      aria-hidden="true"
      style={{ visibility: "hidden" }}
    />
  );
}
