# Static Divergence Meter artwork

Contingent vendors only the eleven **unmodified static PNGs** `0.png`–`9.png` and
`p.png` in this directory. Each is 130 × 384 pixels. These are the upstream
image files, not newly drawn CSS approximations. The application uses eight
images to show device time in UTC as `HH.MM.SS`; it does not present statistics
as a fictional divergence value.

## Exact sources and attribution

- Immediate source: [FrancescoCaracciolo/DivergenceMeter at
  `abf507e7b30eb45fbd412d9a9847ef8f1054391e`](https://github.com/FrancescoCaracciolo/DivergenceMeter/tree/abf507e7b30eb45fbd412d9a9847ef8f1054391e),
  paths [`Website/images/0.png`–`9.png`, `p.png`](https://github.com/FrancescoCaracciolo/DivergenceMeter/tree/abf507e7b30eb45fbd412d9a9847ef8f1054391e/Website/images).
  Its [README, Credits](https://github.com/FrancescoCaracciolo/DivergenceMeter/blob/abf507e7b30eb45fbd412d9a9847ef8f1054391e/README.md#credits)
  credits **LuqueDaniel/Divergence-Meter “for images and gifs”** and describes
  the project as made by the Nyarch Linux lead developer. These are upstream
  attribution statements, not independent proof of image authorship.
- Corroborating earlier source: [LuqueDaniel/Divergence-Meter at
  `78cf84dfcb2278725e058f50c8018c3d300e544c`](https://github.com/LuqueDaniel/Divergence-Meter/tree/78cf84dfcb2278725e058f50c8018c3d300e544c),
  paths [`divergence_meter/images/0.png`–`9.png`, `point.png`](https://github.com/LuqueDaniel/Divergence-Meter/tree/78cf84dfcb2278725e058f50c8018c3d300e544c/divergence_meter/images).
  All ten numbered PNGs are byte-identical across these revisions;
  `Website/images/p.png` is byte-identical to `divergence_meter/images/point.png`.
  Its [README](https://github.com/LuqueDaniel/Divergence-Meter/blob/78cf84dfcb2278725e058f50c8018c3d300e544c/readme.md)
  says “Licensed under: **GPL v3**”. Its
  [COPYING](https://github.com/LuqueDaniel/Divergence-Meter/blob/78cf84dfcb2278725e058f50c8018c3d300e544c/COPYING)
  contains the complete GPL version 3.

Verbatim source READMEs are preserved under `upstream/` as evidence and to retain
notices. Those documents describe the original projects, not Contingent; their
external links and image references are documentation only, never runtime
resources. The immediate source's complete GPLv3 `LICENSE` is also retained
there. `COPYING` here is a verbatim copy of the earlier source's full GPLv3 text.
`SHA256SUMS` covers every PNG and preserved upstream notice (not this local
README). Verify from this directory with `sha256sum -c SHA256SUMS`.

## License basis and source distribution

Redistribution relies on the **project-level GPLv3 declarations** above,
corroborated by byte identity with the credited earlier GPL project. Neither
inspected source provides a separate image-specific originality/ownership
declaration or editable layered artwork/source files. Do not claim that this
establishes original image authorship or an independent chain-of-title audit.
The unmodified PNGs are the available artwork form in both inspected trees.

Keep these attribution records, upstream notices, hashes, and the full GPL text
with redistributed assets. Contingent is also distributed under GPLv3. Distributors
of a bundled/minified application must meet the applicable GPL corresponding
source obligations for the covered work, including the application source and
build material; merely linking to an upstream repository or shipping this asset
folder is not a substitute. Preserve these source PNGs as part of that source
distribution. If a preferred editable source form is subsequently identified,
review and include the required corresponding material before further
redistribution. This notice does not grant rights beyond the upstream license.

## Intentionally excluded

No animated GIFs (`11.gif`, `12.gif`), audio from the visual novel, upstream
application JavaScript, external runtime scripts, or upstream news/API responses
are included or requested at runtime. Separately installed MIT-licensed
`@tsparticles/engine` and `@tsparticles/slim` 3.9.1 are bundled locally; their
configuration in `src/particleOptions.ts` adapts the pinned upstream particle
settings without hover/click spawning. They are not part of this asset directory. The README's broad GIF credit
does not resolve the GIFs' ancestry; it is not used as permission to vendor them.

The clock preserves complete images and aspect ratios with pixelated rendering
on black, following the upstream flex-image presentation with 2px gaps and a
150-pixel image-width cap (reduced from upstream’s 200 pixels). The clock is centered in a full-viewport hero and scales
down on small screens without cropping. UTC labels, navigation and application
reports intentionally differ from upstream. Side-by-side meter inspection checks
composition and proportions, not pixel-identical reproduction.
