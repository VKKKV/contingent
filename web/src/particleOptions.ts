import type { Container, ISourceOptions } from "@tsparticles/engine";

// DivergenceMeter/Website/particles.js, abf507e7b30eb45fbd412d9a9847ef8f1054391e.
// v3 density uses width * height instead of v2's area * 1000.
export const particleOptions = {
  autoPlay: false,
  fullScreen: { enable: false },
  fpsLimit: 30,
  detectRetina: true,
  // This fixed decorative layer has one lifecycle owner below. Library
  // IntersectionObserver callbacks must not resume a deliberately paused tab.
  pauseOnBlur: false,
  pauseOnOutsideViewport: false,
  interactivity: {
    detectsOn: "canvas",
    events: {
      onHover: { enable: false, mode: [] },
      onClick: { enable: false, mode: [] },
      resize: { enable: true },
    },
  },
  particles: {
    number: { value: 70, density: { enable: true, width: 1000, height: 800 } },
    color: { value: ["#FF4500", "#FF6347", "#FF7F50", "#FFA500"] },
    shape: { type: "circle" },
    opacity: { value: { min: 0.1, max: 0.6 } },
    size: { value: { min: 0.1, max: 7 } },
    links: {
      enable: true,
      distance: 150,
      color: "#FF7000",
      opacity: 0.15,
      width: 1,
    },
    move: {
      enable: true,
      direction: "top",
      speed: 0.8,
      random: true,
      straight: false,
      outModes: { default: "out" },
    },
  },
} satisfies ISourceOptions;

type ParticleContainer = Pick<
  Container,
  "destroy" | "pause" | "play" | "pageHidden"
>;

type ParticleLifecycle = {
  motion: Pick<
    MediaQueryList,
    "matches" | "addEventListener" | "removeEventListener"
  >;
  visibility: Pick<
    Document,
    "hidden" | "addEventListener" | "removeEventListener"
  >;
  load: (signal: AbortSignal) => Promise<ParticleContainer | undefined>;
  setVisible: (visible: boolean) => void;
};

// DOM-independent ownership: an obsolete async load may never adopt a new mount.
export function startParticleBackground({
  motion,
  visibility,
  load,
  setVisible,
}: ParticleLifecycle): () => void {
  let stopped = false;
  let active:
    { abort: AbortController; container?: ParticleContainer } | undefined;

  const release = () => {
    const previous = active;
    active = undefined;
    previous?.abort.abort();
    previous?.container?.destroy();
  };
  const update = () => {
    if (stopped) return;
    if (motion.matches) {
      setVisible(false);
      release();
      return;
    }
    const container = active?.container;
    setVisible(!visibility.hidden && !!container);
    if (container) {
      // Explicit resume also covers initialization while the tab was hidden.
      container.pageHidden = visibility.hidden;
      if (visibility.hidden) container.pause();
      else container.play();
    } else if (!active && !visibility.hidden) {
      const run = {
        abort: new AbortController(),
        container: undefined as ParticleContainer | undefined,
      };
      active = run;
      void (async () => {
        try {
          const loaded = await load(run.abort.signal);
          if (stopped || active !== run || run.abort.signal.aborted) {
            loaded?.destroy();
            return;
          }
          run.container = loaded;
          if (loaded) update();
        } catch {
          // Decoration is optional; chunk/init failures must not reject into React.
          if (active === run) {
            setVisible(false);
            release();
          }
        }
      })();
    }
  };

  motion.addEventListener("change", update);
  visibility.addEventListener("visibilitychange", update);
  update();
  return () => {
    stopped = true;
    motion.removeEventListener("change", update);
    visibility.removeEventListener("visibilitychange", update);
    setVisible(false);
    release();
  };
}
