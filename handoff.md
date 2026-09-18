# Current development state

TianJi develops only the Python service and TypeScript workbench. Historical code and plans are
available through Git; existing local databases remain untouched.

The product supports forward simulation, goal search, disturbances, forks, comparison, replay,
role-scoped observations and independent adjudication previews. Only the director credential exists;
actor/referee labels are not participant authentication.

Current work: integrate explicit local model proposals into the existing observation panel. Keep
model inference separate from adjudication and branch creation. No automatic multi-turn agent loop,
remote provider or automatic world-state update.

Documentation describes current behavior. Run normal tests without storing recurring reports or
prompt/response archives. Preserve explicit product data and user-selected exports.
