# Language evidence: Web-first bidirectional simulation lab

## Decision first

**Recommend a TypeScript Web client plus a Python experiment service, with FastAPI as the proposed experiment API boundary. Introduce Python incrementally; do not authorize a whole-backend migration from this research.** The discovered project guidance describes Tianji as an existing Rust engine with an axum API and a retired Python oracle. Preserve that Rust implementation and its contracts; add a bounded Python experiment adapter only after approval of its scope. The long-term experiment-layer preference is TS + Python, while the least-disruptive transition may temporarily contain TS, Rust, and Python. New Rust experiment kernels should follow demonstrated performance or deployment requirements, not trigger a rewrite of the research layer by default.

The deciding requirement is sustained experimentation with forward simulations and goal-directed inverse searches, not simply displaying a world map or invoking LLM agents. Python provides direct access to the ABM and planning interfaces verified below. This is an ecosystem-fit recommendation, **not a performance benchmark, migration estimate, or prediction-accuracy claim**.

Scope: bounded README/manifest research, verified on 2026-09-10. No installs, code execution of the candidate projects, deep Tianji audit, implementation, or migration. Product constraints supplied by the task: Web first; forward and inverse experiments remain core; every product operation must be Agent-accessible; large migrations need confirmation. Team capacity, workload scale, and latency targets remain unknown.

## Comparable options

| Option | Main advantage for this lab | Main cost / limitation | Recommendation |
|---|---|---|---|
| **TS Web + Python/FastAPI** | Use Python ABM, scientific data tooling, and native-backed planning interfaces without reimplementing them; keep browser interaction in TS. | Two runtimes, contract/version coordination, worker lifecycle, scientific/native dependency management. Async HTTP is not a substitute for compute workers. | Preferred long-term experiment boundary; validate with one bounded vertical slice before moving existing services. |
| **TS full stack** | One language and shared application types. Suitable for a small purpose-built model if product iteration dominates scientific reuse. | Tianji is described as Rust today, so a TS backend is itself a migration, not the continuity option. Accessing the verified Python interfaces later requires a worker/service boundary or reimplementation. No claim that TS lacks simulation libraries generally. | Not the default here: neither replacing Rust nor forgoing direct Python-library access is justified by language uniformity alone. |
| **TS + Rust** | Strongest continuity with the existing Rust engine/API described by project guidance; candidate for tightly specified, resource-constrained kernels. WebAssembly remains an architectural possibility, not a verified result. | Does not directly reuse the verified Python ABM/planning interfaces. Bindings, a separate Python service, or equivalent algorithms add work. Performance superiority for this workload has not been measured. | Preserve the existing Rust system. Prefer this alone if the bounded prototype shows Python reuse is marginal; add Python for experiments rather than replacing working Rust indiscriminately. |

No ranking here uses repository counts, stars, or language percentages. In particular, OpenSpiel's primary language is C++, yet its Python interface is directly relevant to a Python experiment layer [S2]. “Use Python” need not mean “execute every numerical operation in Python.”

## Exactly three reasons supporting a Python experiment-layer migration

1. **ABM primitives and analysis belong together.** Mesa describes modular agent-based models, spatial grids/schedulers, browser visualization, and analysis; its manifest declares NumPy, pandas, and SciPy, with NetworkX optional [S1]. Reusing those interfaces is relevant to repeated scenario modeling, parameter sweeps, and analysis rather than rebuilding a research toolbox around a dashboard. Specific sweep/calibration behavior still needs a prototype; the manifest alone does not prove it.
2. **Inverse experiments need evaluable search, not just generated narratives.** OpenSpiel explicitly covers search/planning, cooperative and general-sum interactions, imperfect information, and evaluation tools. Its C++ core is exposed to Python [S2]. This is useful methodological and implementation material for bounded strategic scenarios. Adapting a world scenario to its game/state/action formalism remains our work; OpenSpiel is not an off-the-shelf world inverse solver.
3. **Scientific access can coexist with a Web product and native performance.** Mesa separates modeling/analysis from browser visualization [S1], and OpenSpiel demonstrates a Python-facing native core [S2]. Combined with a separately implemented browser visualization surface [S3], these support a TS presentation layer with replaceable experiment adapters. Python's value is integration and experimentation; it need not own browser rendering or every future hot loop.

## Exactly three reasons against a broad Python migration

1. **Library suitability does not establish rewrite value.** None of [S1–S3] proves that Tianji's existing Rust backend should be replaced. Project guidance says its prior Python oracle was retired; reintroducing Python must therefore earn its operational cost through new experiment capability, not duplicate the old path. A Rust control plane can call an isolated Python worker. Without a repository audit, migration sizing, or team-capacity evidence, an all-at-once rewrite adds unquantified cost and regression risk. Prefer an additive boundary and obtain explicit approval before a large migration.
2. **Python does not remove compute or model-validity constraints.** OpenSpiel deliberately uses a C++ core, and its source-build manifest requires CMake and a C++ toolchain [S2]. Python access is not evidence that pure-Python agent stepping meets our throughput targets. Nor do either project's README claims validate geopolitical/social forecasting or identify a unique cause from an observed outcome. Keep Rust/native kernels available and measure before optimizing.
3. **Compatibility and operational cost are real.** The checked Mesa development manifest requires Python >=3.12, labels development status Alpha, and has a visualization extra constrained to `starlette<1.0`; its README distinguishes stable Mesa 3 from Mesa 4 development [S1]. OpenSpiel declares Python >=3.11 and a native extension build [S2]. Choose and lock tested releases rather than using repository HEAD blindly; do not import Mesa's visualization stack merely to embed it in our TS UI. Two runtimes also require explicit contracts, cancellation, observability, and deployment ownership.

## What “bidirectional” should mean

- **Forward:** versioned initial state, assumptions, interventions, horizon, model, and random seed produce trajectories and outcome distributions. Preserve provenance and uncertainty; reproducibility is not proof of real-world accuracy.
- **Inverse:** a desired outcome and constraints produce candidate interventions, policies, or initial conditions. Search over candidates and evaluate them through the same forward engine; report feasibility, cost, uncertainty, and alternatives. This is not running time backward. Historical explanation/latent-state inference is a separate, often non-identifiable problem and must be labeled as such.
- **Long-term Python value:** connect ABM state transitions [S1] with bounded planning/evaluation interfaces [S2] and scientific analysis [S1]. Treat these as optional adapters, not commitments to use every library or to represent the entire world as one game.

## Smallest adoption gate, not an implementation claim

Use one bounded scenario, explicit actors/actions, a finite horizon, and a measurable target. Implement forward runs and an inverse candidate search evaluated by that same runner. Compare with a simple baseline under equal compute budgets; inspect reproducibility, constraint violations, result quality, latency, and resource use before moving more services.

Proposed boundary: TS Web UI and Agent clients share typed, authenticated commands for scenario editing, branching, run start/cancel, inverse search, comparison, and export. Expose every product operation through this contract rather than relying on Agent browser clicks or a second hidden control path. The existing Rust API may delegate experiment jobs to a FastAPI service; alternatively, FastAPI may own new experiment endpoints without taking over unrelated services. Keep long simulations out of HTTP request lifetimes; store job/event records and stream progress separately. Use schema-generated clients, explicit authorization and confirmations for consequential operations. Agent controllability is a protocol/design property, not a reason to select Python, TS, or Rust by itself.

A Rust kernel is justified only after the representative workload exposes a specific bottleneck or hard constraint and an equivalent kernel demonstrates a benefit while preserving model semantics. Do not migrate unrelated Web, ingest, or product code merely to unify languages.

## Pinned sources and observed facts

### S1 — Mesa

- Queried repository: `projectmesa/mesa`; the returned README/project URLs refer to `mesa/mesa`.
- Commit: `a5dfcd6ad2bb7863a00d8735649d4c3ebaf014f8`.
- [README](https://github.com/projectmesa/mesa/blob/a5dfcd6ad2bb7863a00d8735649d4c3ebaf014f8/README.md) · [pyproject.toml](https://github.com/projectmesa/mesa/blob/a5dfcd6ad2bb7863a00d8735649d4c3ebaf014f8/pyproject.toml).
- GitHub metadata reports primary language Python and Apache-2.0 license. README claims and manifest facts are distinguished above. This development snapshot is not presented as a recommended release or a successful installation.

### S2 — OpenSpiel

- Repository: `google-deepmind/open_spiel`.
- Commit: `48401890ee9857e611678302371378175a8e4c6b`.
- [README](https://github.com/google-deepmind/open_spiel/blob/48401890ee9857e611678302371378175a8e4c6b/README.md) · [setup.py](https://github.com/google-deepmind/open_spiel/blob/48401890ee9857e611678302371378175a8e4c6b/setup.py).
- GitHub metadata reports primary language C++ and Apache-2.0 license. README explicitly describes C++ games/core exposed to Python, with algorithms/tools in both languages. The manifest builds `pyspiel` using CMake. No installation, algorithm run, or throughput result was produced.

### S3 — God's Eye View, existing verified local snapshot

- Repository: `bilawalsidhu/gods-eye-view`.
- Commit: `759652207fd1279ece97f0f19af566feb9a82146`; local Git HEAD and origin verified; working tree clean.
- [package.json](https://github.com/bilawalsidhu/gods-eye-view/blob/759652207fd1279ece97f0f19af566feb9a82146/package.json).
- Manifest declares Vite, Cesium, and `satellite.js`. This supports browser/geospatial presentation as a separate concern, not the existence of a simulation engine or a TS full-stack architecture. This manifest does not declare TypeScript; it must not be relabeled as a TS project.

### Supplemental local snapshots — not SHA-pinned in this pass

Read the supplied Shadowbroker frontend/backend manifests and MiroFish backend manifest. Shadowbroker declares Next/React/TypeScript plus FastAPI/Pydantic/NumPy/NetworkX; MiroFish declares Flask, `camel-oasis`, and `camel-ai`, not FastAPI. Their supplied extracted directories have no Git metadata, so exact source SHAs were not established here. They are contextual observations only, not the pinned basis of the recommendation. Source entry points: [Shadowbroker](https://github.com/BigBodyCobain/Shadowbroker), [MiroFish](https://github.com/666ghj/MiroFish). Do not cite these local files as verified upstream HEAD or infer runnability from their dependencies.

## Verification record and limits

Executed local manifest reads, `git rev-parse HEAD`, origin/status checks, and bounded GitHub source retrieval for Mesa and OpenSpiel via `gh api repos/<repo>`, `gh api repos/<repo>/commits/HEAD`, and SHA-qualified contents endpoints. The retrieval command included one retry and a public `curl` fallback; successful returned metadata/content was used, but the command did not log which transport supplied each response. Initial `gh auth status` timed out; this did not block subsequent source retrieval. No credentials were printed.

No dependency installs, builds, benchmarks, source-tree/deep-code audit, or runtime verification were performed. Current Rust architecture is taken from discovered `.trellis/AGENTS.md` project guidance, not independently audited source; local repository HEAD was `a5a3c656e779f6444cc4408cc02a7a8dac4e5e64`. This report is source-backed stack guidance only. FastAPI is a proposed boundary, not independently benchmarked here. Parent task owns exact-target readback, PRD integration, migration approval, and implementation validation.
