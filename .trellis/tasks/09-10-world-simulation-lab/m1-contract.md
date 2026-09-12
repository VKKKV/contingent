# M1 executable contract — approved TS/Python implementation

This is the bounded first release, not the whole architecture roadmap. All new code lives under `backend/` and `web/`; preserve `src/`, Cargo files and `runs/`. Python 3.12+, React/TypeScript/Vite. Root plan must distinguish legacy from this slice. No real LLM calls or external datasets: label policy `rules-v1`, scenario `fictional`, outputs `model-conditional`. A free-text pseudo-chat is not a substitute for a real agent; external MCP operation control is required now.

## Domain modules owned by kernel implementer

`backend/tianji_lab/models.py` and `kernel.py`, plus `backend/tests/test_kernel.py`.

Use Pydantic v2, extra=forbid, finite bounded integers. Contract models exported:

- `Scenario`: name:str (1..100), horizon:int (1..10, default 6), initial_inventory:int (0..100, default12), initial_cash:int (0..10000, default160), demand_per_tick:int(1..20,default4), supplier_stock:int(0..200,default40), shipment_size:int(1..20,default8), standard_cost:int(1..1000,default16), express_cost:int(1..1000,default32), standard_lead:int(1..5,default2), express_lead:int(1..5,default1). Also optional description:str <=2000 default clear fictional supply-chain description. Zero hidden real data; all model fields operator-visible. Participant observation model below.
- `Goal`: max_shortage:int(0..200,default0), min_cash:int(0..10000,default0), max_spend:int(0..10000,default100), min_inventory:int(0..100,default0).
- `Action` is Literal['wait','order_standard','order_express'] (plain string).
- `Shipment`: due_tick:int, quantity:int.
- `State`: tick, inventory, cash, supplier_stock, delivered, shortage, spent (integer), shipments:list[Shipment].
- `Frame`: state:State, action:str (initial frame action='initial'), events:list[str], state_hash:str.
- `Trajectory`: frames:list[Frame], actions:list[Action], final_state:State, state_hash:str, goal_met:bool|None; include `rule_version='supply-chain.v1'` if useful.
- `SearchResult`: plans:list[Trajectory], expanded:int, exhausted:bool, status:Literal['found','no_solution','budget_exhausted'], rule_version. `exhausted` means frontier exhausted, NOT budget consumed. If plans found + still unsearched states, status found and exhausted false. No_solution only if complete finite search, no plans. Search goal checked at horizon. Rank plans by spent then shortage then lexicographic action sequence; max3 results. No numeric 'probability'.

Functions exact names:
`initial_state(scenario)->State`; `state_hash(state)->str` canonical sha256 JSON; `step(scenario,state,action)->Frame`; `simulate(scenario,actions:list[str],goal:Goal|None=None, start:State|None=None)->Trajectory`; `search(scenario,goal,max_nodes:int=5000,start:State|None=None)->SearchResult`; `observe(state,role:Literal['director','retailer','supplier'])->dict`; `validate_trajectory(scenario,trajectory, start=None)->bool` may raise ValueError.

Rules: action validated before mutation; order purchases shipment_size from finite supplier_stock, consumes cash, queues due at current tick+lead; reject insufficient cash/stock or tick>=horizon, unknown action. Advance tick, deliver shipments now due, meet that tick's demand from inventory, add unmet demand to cumulative shortage (not recoverable backlog), track delivered. Wait allowed. Preserve goods invariant inventory + in-transit + delivered + supplier_stock = initial_inventory+initial_supplier_stock; cash+spent=initial_cash. No in-place mutation of supplied models. Each simulate begins with initial/start frame, pads action list with wait to scenario horizon, rejects too many actions. Search explores legal actions from initial/start state, dedups only on full sufficient state, bounded max_nodes 1..50000; forward verify chosen candidates. Strictly label budget failure vs no solution. Observe retailer excludes supplier_stock, supplier excludes cash and retail demand/shortage fields; director all. Do not claim this is realistic bargaining or general multi-agent dynamics.

## Service modules owned by service implementer

`backend/tianji_lab/{__init__,store,service,api,mcp_server,__main__}.py`, `backend/pyproject.toml`, `backend/tests/test_service.py` and test_api.py/test_mcp.py as time permits. Do not write models.py/kernel.py or kernel tests; rely on above interface. Own installation `uv sync --python 3.12` in backend, generate uv.lock. FastAPI,Pydantic,uvicorn,httpx,mcp + pytest/ruff dev. Use official MCP Python SDK lowlevel Server or FastMCP with actual tools schemas, not fake JSON-RPC.

Runtime CLI: `uv run python -m tianji_lab serve --host 127.0.0.1 --port 8787 --data-dir .local-data` and `... mcp --url http://127.0.0.1:8787` (stdio adapter proxies API with env TIANJI_TOKEN). Local user supplies TIANJI_TOKEN externally for repeatable tests. If missing, server generates token to data-dir/token mode0600 and prints only that local path; never commit or leak key to logs. Bind loopback only. Frontend presents token field initially, stores memory/sessionStorage; no token in URL.

SQLite separate from legacy, thread-safe connections per transaction, bounded JSON blobs. Tables scenario(id,revision,spec_json), branch(id,scenario_id,parent_id,fork_tick,name,trajectory_json), jobs(id,kind,status,input_json,result_json,error,created_at), workspace(id,revision,state_json,last_seen), idempotency. Freeze scenario per branch/job via stored spec snapshot/revision; no silent old mutation. No delete operations in M1.

HTTP public: GET /health -> {ok:true,version:'0.3.0'} only; authorized GET /api/capabilities -> list entries {name,description,input_schema,mutating}. POST /api/operations/{name} with JSON body {arguments:object,request_id?:string} -> {ok:true,data:any}; failures {ok:false,error:{code,message}} with status401/403/404/409/422. Authorization Bearer; require valid token for everything except health/static; deny cross-site Origin/Sec-Fetch-Site writes, no wildcard CORS. Limit request body <=1MB. OpenAPI may be auth-gated.

Every capability's schema generates Web forms/types (UI may keep hand typed response only until generator integration) and MCP tools/list. Dispatch one shared service execute operation, validate inputs with per-operation Pydantic. Mutation request_id required and stored transactionally or require for branch/scenario/job creations at minimum; same operation/request_id+args returns same result; reuse with different args->409. No filesystem paths from operation args.

Exact operation names & input/output:
- `scenario_list` {} -> {items:[{id,revision,spec:Scenario}]}; on new DB seed exactly one fictional default scenario.
- `scenario_create` {spec:Scenario} -> {id,revision:1,spec}; `scenario_update` {id,revision,spec} -> updated envelope (409 stale).
- `branch_list` {scenario_id} -> {items:[Branch]}; `branch_get` {id}->Branch.
- `run_forward` {scenario_id,actions:Action[],name?:str} -> Job (bounded asynchronous). Save a branch when worker finishes. Job.result {branch:Branch}.
- `run_backward` {scenario_id,goal:Goal,max_nodes:int=5000,name?:str}->Job; worker search saves plan branches. Job.result {search:SearchResult,branches:[Branch]}.
- `branch_fork` {id,tick:int,actions:Action[],name?:str}->Job; validate tick exists in original; use frame state/spec frozen on branch. Store the continuation trajectory plus complete inherited `provenance.prefix_actions`. Import must independently replay that prefix from the frozen scenario initial state and verify the continuation starts there; never trust the caller-controlled start snapshot. This proves model consistency, not the identity or authenticity of an external parent. Branch retains parent_id/fork_tick. Job.result {branch:Branch}.
- `branch_compare` {left_id,right_id}-> {left:Branch,right:Branch,delta:{inventory,cash,shortage,spent,delivered}}; same frozen scenario specification required or error409.
- `branch_export` {id}-> {schema_version:'tianji.lab.bundle.v1',branch:Branch,digest:str}; digest canonical JSON of branch. `branch_import` {bundle:object}->Branch with new ID; validate schema,size,digest,rules,spec and forward replay/invariants, never trust hashes alone. Preserve prior parent identity only as provenance, no dangling FK.
- `job_get` {id}->Job; `job_cancel` {id}->Job. States queued,running,succeeded,failed,cancelled,interrupted. Background single worker (thread supervisor spawning process or ProcessPoolExecutor) loads durable queued jobs; results stored after completion. Restart marks running interrupted, queued resumes. Cancellation must prevent result branch commit; compute bounded so cooperative cancellation can wait, expose behavior. Never call CPU search on async HTTP loop.
- `workspace_attach` {id?:str}->Workspace; `workspace_get` {id}->Workspace; `workspace_update` {id,revision,scenario_id?:str|null,branch_id?:str|null,compare_branch_id?:str|null,tick?:int|null,panel?:'timeline'|'compare'|'goal'|null}->Workspace. Validate branch/tick and branch-scenario membership; changing scenario clears stale branch/tick/comparison; comparison requires equal frozen specs. On new attach state {tick:0,panel:'timeline'}, revision1. Browser polling workspace_get updates state, use revision CAS. These are shared desired-state commands, not browser-acknowledged rendering; no claim action visually applied unless heartbeat/ack implemented. Keep capability description explicit.

Branch={id,name,scenario_id,scenario_revision,spec:Scenario,parent_id:null|string,fork_tick:null|int,trajectory:Trajectory,mode:'forward'|'backward'|'fork'|'import',created_at}; Job={id,kind,status,result:null|object,error:null|string}. Workspace={id,revision,branch_id:null|string,tick:int,panel:string} (flattened).

MCP stdio server discovers capabilities over authorized HTTP and proxies each validated operation; generates UUID request_id for mutation calls; maps errors to MCP isError. Token only via env; adapter URL loopback by default; no new network exposure. Real SDK client test must initialize/list_tools/call_tool.

## Frontend owned by Web implementer

`web/` only: React,TypeScript,Vite, CSS, package/lockfiles/tests. `npm install` allowed after parent registry ping. Proxy /api and /health to localhost8787 for dev; normal build served by Python API from web/dist. Pure node-free production assets. TypeScript strict. Do NOT create synthetic API/mock backend data to make page look alive. Data only real HTTP backend.

Design: elegant dense dark laboratory (not military dashboard), background #101319, warm-white text, cyan or amber accent, fine dividers, no emoji in app. Title 天机 / TIANJI; subtitle 双向世界推演实验室; explicit 规则模型 · 虚构供应链 label. No fake chat: display 外部 Agent · API / MCP 已开放, MCP setup/help as text. Left scenario list/editor, center branch cards/tree + SVG state trace chart/time slider/events, right operation panel forward action selector, backward goal/budget form, fork and compare. Local token form; actionable errors, loading states, jobs poll, import/export actual JSON. Mobile narrow column layout.

Each product data mutation/view workspace selection via operation API; token input/download do not need agent tooling. Auth fetch wrapper uses Authorization, UUID request_id for mutations; frontend response state must not drift, stale CAS handled visible. On connect call scenario_list, workspace_attach, then branch_list. Select branch -> workspace_update, poll workspace_get to accept external MCP select/tick/panel changes; discard stale loads; show workspace ID and API connection. Tick slider references actual trajectory frames; fork chooses actual tick, not array index.

Minimum accessible data-testid: token-input, connect-button, scenario-name, save-scenario, run-forward, run-backward, fork-branch, branch-list, timeline-slider, export-branch, import-bundle, error-banner, job-status. Functional buttons/forms must be wired. Default forward actions wait; backward default goal above. Show branch goal_met, cost/shortage; hide no-result junk. Poll jobs until terminal; refresh list/select resulting branch and display search budget status; server CPU work is never represented as finished before result.

## Integration and non-goals

Parent owns plan/README/specs, root gitignore, e2e scripts and verification orchestration. No source deletion or paid provider. Do not add a general expression DSL, global feeds, model loop, remote users, custom rules plugin or full approval workflow in this slice. Do not claim unsupported pause/resume, SSE or real-time browser acknowledgement; this slice uses bounded jobs + cancel + restart interruption and polling.

Acceptance: kernel tests cover invariants/invalid/actions/replay/search ground truth; service/API tests auth, validation, idempotency, frozen specs, fork/import replay integrity and workspace revision; actual MCP stdio client controls API; actual browser creates scenario, forward, backward, fork, compare/export/import and reacts to external workspace change; fresh build/test and legacy untouched checks. Later development extends contract deliberately, not by describing stubs as delivered.
