import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import ParticleBackground from "./ParticleBackground";
import { particleOptions, startParticleBackground } from "./particleOptions";

class Motion extends EventTarget {
  matches = false;
  change(matches: boolean) {
    this.matches = matches;
    this.dispatchEvent(new Event("change"));
  }
}

class Visibility extends EventTarget {
  hidden = false;
  change(hidden: boolean) {
    this.hidden = hidden;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}

function container() {
  return { destroy: vi.fn(), pause: vi.fn(), play: vi.fn(), pageHidden: false };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

function setup(reduced = false, hidden = false) {
  const motion = new Motion();
  motion.matches = reduced;
  const visibility = new Visibility();
  visibility.hidden = hidden;
  const particles = container();
  const load = vi.fn((_signal: AbortSignal) => Promise.resolve(particles));
  const setVisible = vi.fn();
  return { motion, visibility, particles, load, setVisible };
}

describe("decorative particle options", () => {
  it("adapts reference particles to v3 without mouse effects or spawning", () => {
    expect(particleOptions).toMatchObject({
      autoPlay: false,
      fpsLimit: 30,
      fullScreen: { enable: false },
      pauseOnBlur: false,
      pauseOnOutsideViewport: false,
      interactivity: {
        detectsOn: "canvas",
        events: {
          onHover: { enable: false, mode: [] },
          onClick: { enable: false, mode: [] },
        },
      },
      particles: {
        number: {
          value: 70,
          density: { enable: true, width: 1000, height: 800 },
        },
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
          outModes: { default: "out" },
        },
      },
    });
    expect(particleOptions).not.toHaveProperty("emitters");
    expect(particleOptions).not.toHaveProperty("interactivity.modes.push");
  });

  it("renders only an initially hidden, inaccessible decorative host on the server", () => {
    expect(renderToStaticMarkup(createElement(ParticleBackground))).toBe(
      '<div id="instrument-particles" class="instrument-particles" aria-hidden="true" style="visibility:hidden"></div>',
    );
  });
});

describe("particle lifecycle", () => {
  it("does not invoke the lazy loader under reduced motion, and responds live", async () => {
    const state = setup(true);
    const stop = startParticleBackground(state);
    expect(state.load).not.toHaveBeenCalled();
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
    state.motion.change(false);
    await flush();
    expect(state.load).toHaveBeenCalledTimes(1);
    expect(state.particles.play).toHaveBeenCalledTimes(1);
    state.motion.change(true);
    expect(state.particles.destroy).toHaveBeenCalledTimes(1);
    expect(state.load.mock.calls[0][0].aborted).toBe(true);
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
    stop();
    expect(state.particles.destroy).toHaveBeenCalledTimes(1);
  });

  it("delays hidden-tab loading, then pauses/hides and explicitly resumes", async () => {
    const state = setup(false, true);
    const stop = startParticleBackground(state);
    expect(state.load).not.toHaveBeenCalled();
    state.visibility.change(false);
    await flush();
    expect(state.particles.play).toHaveBeenCalledTimes(1);
    expect(state.setVisible).toHaveBeenLastCalledWith(true);
    state.visibility.change(true);
    expect(state.particles.pageHidden).toBe(true);
    expect(state.particles.pause).toHaveBeenCalledTimes(1);
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
    state.visibility.change(false);
    expect(state.particles.pageHidden).toBe(false);
    expect(state.particles.play).toHaveBeenCalledTimes(2);
    expect(state.load).toHaveBeenCalledTimes(1);
    stop();
  });

  it("does not play if loading completes in a hidden tab", async () => {
    const state = setup();
    const pending = deferred<ReturnType<typeof container>>();
    state.load.mockReturnValue(pending.promise);
    const stop = startParticleBackground(state);
    state.visibility.change(true);
    pending.resolve(state.particles);
    await flush();
    expect(state.particles.play).not.toHaveBeenCalled();
    expect(state.particles.pause).toHaveBeenCalledTimes(1);
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
    state.visibility.change(false);
    expect(state.particles.play).toHaveBeenCalledTimes(1);
    stop();
  });

  it.each(["unmount", "reduced motion"])(
    "destroys a late container after %s",
    async (reason) => {
      const state = setup();
      const pending = deferred<ReturnType<typeof container>>();
      state.load.mockReturnValue(pending.promise);
      const stop = startParticleBackground(state);
      if (reason === "unmount") stop();
      else state.motion.change(true);
      expect(state.load.mock.calls[0][0].aborted).toBe(true);
      pending.resolve(state.particles);
      await flush();
      expect(state.particles.destroy).toHaveBeenCalledTimes(1);
      expect(state.particles.play).not.toHaveBeenCalled();
      expect(state.setVisible).toHaveBeenLastCalledWith(false);
      stop();
    },
  );

  it("isolates slow StrictMode setup/cleanup/setup loads", async () => {
    const state = setup();
    const stale = deferred<ReturnType<typeof container>>();
    const current = container();
    state.load
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(current);
    const stopFirst = startParticleBackground(state);
    stopFirst();
    const stopSecond = startParticleBackground(state);
    await flush();
    stale.resolve(state.particles);
    await flush();
    expect(state.particles.destroy).toHaveBeenCalledTimes(1);
    expect(state.particles.play).not.toHaveBeenCalled();
    expect(current.play).toHaveBeenCalledTimes(1);
    expect(current.destroy).not.toHaveBeenCalled();
    expect(state.setVisible).toHaveBeenLastCalledWith(true);
    stopSecond();
    expect(current.destroy).toHaveBeenCalledTimes(1);
  });

  it("isolates rapid reduced-motion toggles while initialization is pending", async () => {
    const state = setup();
    const stale = deferred<ReturnType<typeof container>>();
    const current = container();
    state.load
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(current);
    const stop = startParticleBackground(state);
    state.motion.change(true);
    state.motion.change(false);
    await flush();
    stale.resolve(state.particles);
    await flush();
    expect(state.particles.destroy).toHaveBeenCalledTimes(1);
    expect(current.destroy).not.toHaveBeenCalled();
    expect(current.play).toHaveBeenCalledTimes(1);
    expect(state.setVisible).toHaveBeenLastCalledWith(true);
    stop();
  });

  it("absorbs import/init failures, including late rejections after cleanup", async () => {
    const state = setup();
    state.load.mockRejectedValueOnce(new Error("chunk unavailable"));
    const stop = startParticleBackground(state);
    await flush();
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
    expect(state.particles.play).not.toHaveBeenCalled();
    const late = deferred<ReturnType<typeof container>>();
    state.load.mockReturnValueOnce(late.promise);
    state.visibility.change(false);
    stop();
    late.reject(new Error("init failed after unmount"));
    await flush();
    expect(state.setVisible).toHaveBeenLastCalledWith(false);
  });

  it("removes both listeners and destroys the owned container exactly once", async () => {
    const state = setup();
    const removeMotion = vi.spyOn(state.motion, "removeEventListener");
    const removeVisibility = vi.spyOn(state.visibility, "removeEventListener");
    const stop = startParticleBackground(state);
    await flush();
    stop();
    stop();
    expect(removeMotion).toHaveBeenCalledWith("change", expect.any(Function));
    expect(removeVisibility).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
    expect(state.particles.destroy).toHaveBeenCalledTimes(1);
    state.motion.change(false);
    state.visibility.change(false);
    expect(state.load).toHaveBeenCalledTimes(1);
    expect(state.particles.play).toHaveBeenCalledTimes(1);
  });
});
