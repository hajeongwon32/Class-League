// ===== 작은 도우미 =====
const $ = (id) => document.getElementById(id);

// 태그 만들기. 글자는 textContent로만 넣어서 HTML 태그가 실행되지 않게 한다.
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

// 서버 요청: body가 없으면 GET, 있으면 POST(JSON)
async function api(url, body) {
  const opts = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function setMsg(node, text, ok) {
  node.className = "msg " + (ok ? "ok" : "err");
  node.textContent = text || "";
}

// localStorage는 막혀 있을 수도 있어서 try로 감싼다 (새로고침 때 마지막 역할 기억용)
function remember(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* 저장 못 해도 앱은 그대로 동작 */ }
}
function recall(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

// ===== 시간 (서버는 UTC, 화면은 한국 시간) =====
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
let serverOffset = 0; // 서버 시계 - 내 시계 (ms)

function syncClock(nowIso) {
  if (nowIso) serverOffset = Date.parse(nowIso) - Date.now();
}
function serverNow() {
  return Date.now() + serverOffset;
}
// UTC ISO → 한국 시간 조각
function kst(iso) {
  const d = new Date(Date.parse(iso) + 9 * 3600 * 1000);
  return {
    y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(),
    wd: WEEKDAYS[d.getUTCDay()], hh: d.getUTCHours(), mm: d.getUTCMinutes(),
  };
}
const pad = (n) => String(n).padStart(2, "0");
function fmtDay(iso) {
  const t = kst(iso);
  return `${t.m}/${t.d}(${t.wd})`;
}
function fmtDT(iso) {
  const t = kst(iso);
  return `${t.m}/${t.d}(${t.wd}) ${pad(t.hh)}:${pad(t.mm)}`;
}
function fmtRemain(ms) {
  if (ms <= 0) return "마감됨";
  const min = Math.floor(ms / 60000);
  const d = Math.floor(min / 1440);
  const h = Math.floor((min % 1440) / 60);
  const m = min % 60;
  if (d > 0) return `${d}일 ${h}시간 남음`;
  if (h > 0) return `${h}시간 ${m}분 남음`;
  return `${Math.max(m, 1)}분 남음`;
}
// 남은 시간 표시 (30초마다 자동으로 바뀜)
function countdown(iso) {
  const span = el("span", "countdown");
  span.dataset.until = iso;
  span.textContent = fmtRemain(Date.parse(iso) - serverNow());
  return span;
}
setInterval(() => {
  let crossed = false;
  document.querySelectorAll(".countdown").forEach((span) => {
    const left = Date.parse(span.dataset.until) - serverNow();
    if (left <= 0 && span.textContent !== "마감됨") crossed = true;
    span.textContent = fmtRemain(left);
  });
  // 마감이 막 지났으면 지금 화면을 새로 불러온다
  if (crossed) refreshCurrentView();
}, 30000);

// 날짜 문자열("2026-10-12") 계산용
function addDays(ymd, n) {
  const [y, m, d] = ymd.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`;
}
function fmtYmd(ymd) {
  const [y, m, d] = ymd.split("-").map(Number);
  return `${m}/${d}(${WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]})`;
}
function todayKstYmd() {
  const t = kst(new Date(serverNow()).toISOString());
  return `${t.y}-${pad(t.m)}-${pad(t.d)}`;
}
// 학생 수 → 전체 주차 수 (홀수면 한 주씩 더: 매주 한 명씩 쉬니까)
function weeksFor(n, legs) {
  if (n < 2) return 0;
  return (n % 2 === 0 ? n - 1 : n) * legs;
}

// ===== 화면 전환 =====
let me = null;               // 로그인한 나 {user_id, nickname, student_league_id}
let pendingRole = null;      // 로그인 전에 고른 역할
let currentView = "landingView";
let adminLeagueId = null;    // 관리 중인 리그
let editingLeagueId = null;  // 설정 수정 중인 리그 (새로 만들 땐 null)
let studentData = null;      // 학생 리그 화면 데이터
let currentMatch = null;     // 이번 주 내 경기
let onlyMine = true;         // 일정: 내 경기만 볼지

function show(viewId) {
  document.querySelectorAll("main > .view").forEach((v) => v.classList.add("hidden"));
  $(viewId).classList.remove("hidden");
  currentView = viewId;
  window.scrollTo(0, 0);
}

function refreshCurrentView() {
  if (currentView === "studentView") openStudent();
  else if (currentView === "adminLeagueView") openAdminLeague(adminLeagueId);
}

function renderTopbar() {
  if (me) {
    $("guestArea").classList.add("hidden");
    $("userArea").classList.remove("hidden");
    $("navNickname").textContent = me.nickname;
  } else {
    $("guestArea").classList.remove("hidden");
    $("userArea").classList.add("hidden");
  }
}

async function loadMe() {
  const { data } = await api("/me");
  me = data.logged_in ? data : null;
  renderTopbar();
  return me;
}

function goLanding() {
  remember("role", null);
  $("landingSub").textContent = me
    ? `${me.nickname}님, 어디로 갈까요?`
    : "반 친구들과 서로 문제를 내고 풀어 승점을 쌓아요. 프리미어리그처럼 매주 한 경기씩, 순위를 겨뤄요.";
  show("landingView");
}

function goRole(role) {
  remember("role", role);
  if (role === "admin") openAdmin();
  else openStudent();
}

// 처음 화면에서 역할 고르기: 로그인 안 했으면 로그인 화면으로
document.querySelectorAll(".portal").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (me) goRole(btn.dataset.role);
    else showAuth(btn.dataset.role);
  });
});
document.querySelectorAll(".go-landing").forEach((b) => b.addEventListener("click", goLanding));
document.querySelectorAll(".go-student").forEach((b) => b.addEventListener("click", openStudent));
$("brandBtn").addEventListener("click", goLanding);

// ===== 로그인 / 회원가입 =====
function showAuth(role) {
  pendingRole = role || null;
  const hint = $("authRoleHint");
  if (role === "admin") {
    hint.textContent = "🧑‍🏫 선생님 관리실 — 로그인하면 리그를 만들고 관리할 수 있어요.";
  } else if (role === "student") {
    hint.textContent = "🎟️ 학생 입장 포털 — 로그인한 뒤 리그 코드로 입장해요.";
  }
  hint.classList.toggle("hidden", !role);
  show("authView");
}
$("authBackBtn").addEventListener("click", goLanding);
$("navLoginBtn").addEventListener("click", () => { showAuth(null); $("tabLogin").click(); });
$("navRegisterBtn").addEventListener("click", () => { showAuth(null); $("tabRegister").click(); });

$("tabLogin").addEventListener("click", () => {
  $("tabLogin").classList.add("active");
  $("tabRegister").classList.remove("active");
  $("loginForm").classList.remove("hidden");
  $("registerForm").classList.add("hidden");
});
$("tabRegister").addEventListener("click", () => {
  $("tabRegister").classList.add("active");
  $("tabLogin").classList.remove("active");
  $("registerForm").classList.remove("hidden");
  $("loginForm").classList.add("hidden");
});

$("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    username: $("regUsername").value,
    password: $("regPassword").value,
    nickname: $("regNickname").value,
  };
  const { ok, data } = await api("/register", body);
  if (ok) {
    // 가입하면 바로 로그인까지 해 준다
    const login = await api("/login", { username: body.username, password: body.password });
    $("registerForm").reset();
    setMsg($("registerMsg"), "");
    if (login.ok) return afterLogin();
    $("tabLogin").click();
    setMsg($("loginMsg"), "가입이 끝났어요. 로그인해 보세요!", true);
  } else {
    setMsg($("registerMsg"), data.error || "가입에 실패했어요.");
  }
});

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok, data } = await api("/login", {
    username: $("loginUsername").value,
    password: $("loginPassword").value,
  });
  if (ok) {
    $("loginForm").reset();
    setMsg($("loginMsg"), "");
    afterLogin();
  } else {
    setMsg($("loginMsg"), data.error || "로그인에 실패했어요.");
  }
});

async function afterLogin() {
  await loadMe();
  if (pendingRole) goRole(pendingRole);
  else goLanding();
}

$("logoutBtn").addEventListener("click", async () => {
  await api("/logout", {});
  me = null;
  renderTopbar();
  goLanding();
});

// ===== 공통 표시 =====
const STATUS_TEXT = { recruiting: "모집 중", running: "진행 중", finished: "끝남" };
const PHASE_TEXT = { upcoming: "예정", make: "문제 만들기", solve: "문제 풀기", done: "끝" };

function setStatusBadge(node, status) {
  node.textContent = STATUS_TEXT[status] || status;
  node.className = "badge badge-" + status;
}

// 주차 단계 표시: ① 문제 만들기 → ② 문제 풀기 → ③ 결과
function renderPhase(r, forStudent) {
  const box = el("div", "phase-box");
  const steps = el("div", "steps");
  const order = ["make", "solve", "done"];
  const cur = r.phase === "upcoming" ? -1 : order.indexOf(r.phase);
  const items = [
    ["① 만들기", "~" + fmtDT(r.make_deadline)],
    ["② 풀기", "~" + fmtDT(r.solve_deadline)],
    ["③ 결과", "자동 판정"],
  ];
  items.forEach(([name, when], i) => {
    const s = el("div", "step" + (i === cur ? " active" : i < cur ? " done" : ""));
    s.append(el("b", null, name), el("span", null, when));
    steps.appendChild(s);
  });
  box.appendChild(steps);

  const line = el("p", "deadline-line");
  if (r.phase === "upcoming") {
    line.append(`${r.week}주차 시작(${fmtDT(r.start_at)})까지 `, countdown(r.start_at));
    if (forStudent) line.append(" · 미리 문제를 만들어 둘 수 있어요");
  } else if (r.phase === "make") {
    line.append("문제 만들기 마감까지 ", countdown(r.make_deadline));
  } else if (r.phase === "solve") {
    line.append("문제 풀기 마감까지 ", countdown(r.solve_deadline));
  } else {
    line.textContent = "이번 주차 경기가 끝났어요.";
  }
  box.appendChild(line);
  return box;
}

// 순위표 (상품·벌칙 구간 색칠, 내 줄 강조)
function renderStandings(container, standings, rewards, myId) {
  container.innerHTML = "";
  const wrap = el("div", "table-wrap");
  const table = el("table", "standings");
  const head = el("tr");
  ["순위", "닉네임", "경기", "승", "무", "패", "득", "실", "득실", "승점"].forEach((h, i) =>
    head.appendChild(el("th", i === 6 || i === 7 ? "col-sub" : null, h))
  );
  const thead = el("thead");
  thead.appendChild(head);
  const tbody = el("tbody");
  for (const s of standings) {
    const tr = el("tr");
    const rw = rewards.find((r) => s.rank >= r.from && s.rank <= r.to);
    if (rw) tr.classList.add(rw.kind === "penalty" ? "zone-penalty" : "zone-reward");
    if (s.user_id === myId) tr.classList.add("me");
    const diff = s.diff > 0 ? `+${s.diff}` : String(s.diff);
    [s.rank, s.nickname, s.played, s.win, s.draw, s.lose, s.scored, s.conceded, diff, s.points]
      .forEach((v, i) => tr.appendChild(el("td", i === 9 ? "pts" : i === 6 || i === 7 ? "col-sub" : null, v)));
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  if (rewards.length) {
    const legend = el("div", "reward-legend");
    for (const r of rewards) {
      const range = r.from === r.to ? `${r.from}등` : `${r.from}~${r.to}등`;
      legend.appendChild(
        el("div", "legend-chip " + (r.kind === "penalty" ? "zone-penalty" : "zone-reward"),
          `${r.kind === "penalty" ? "😈 벌칙" : "🎁 상품"} ${range}: ${r.text}`)
      );
    }
    container.appendChild(legend);
  }
  container.appendChild(el("p", "hint legend-line",
    "득 = 내가 맞힌 문제 수 · 실 = 상대가 맞힌 문제 수 · 승점이 같으면 득실차 → 득점 순"));
}

// 경기 한 줄: A 2 : 1 B
function fixtureRow(m, myId) {
  const li = el("li", "fixture");
  if (myId && (m.p1.id === myId || m.p2.id === myId)) li.classList.add("mine");
  const p1 = el("span", "pl pl-1", m.p1.nickname);
  const p2 = el("span", "pl pl-2", m.p2.nickname);
  let mid;
  if (m.result === null) {
    mid = el("span", "sc sc-pending", "vs");
  } else if (m.result === "both_lose") {
    mid = el("span", "sc", "둘 다 기권");
  } else {
    mid = el("span", "sc", `${m.p1_score} : ${m.p2_score}`);
    if (m.result === "p1") p1.classList.add("winner");
    if (m.result === "p2") p2.classList.add("winner");
  }
  if (m.forfeit === "p1") p1.append(el("small", "ff", " 기권"));
  if (m.forfeit === "p2") p2.append(el("small", "ff", " 기권"));
  li.append(p1, mid, p2);
  return li;
}

// 전체 경기 일정 (주차별)
function renderSchedule(container, d, myId, mineOnly) {
  container.innerHTML = "";
  const legs = d.league.settings.legs;
  for (const r of d.rounds) {
    const matches = mineOnly
      ? r.matches.filter((m) => m.p1.id === myId || m.p2.id === myId)
      : r.matches;
    const myBye = r.bye && r.bye.id === myId;

    if (legs === 2 && r.week === d.total_weeks / 2 + 1) {
      container.appendChild(el("div", "half-divider", "— 후반기 —"));
    }
    const box = el("div", "round");
    if (r.week === d.focus_week && d.league.status === "running") box.classList.add("now");
    const head = el("div", "round-head");
    head.append(
      el("b", null, `${r.week}주차`),
      el("span", "round-date", `${fmtDay(r.start_at)} ~ ${fmtDay(r.solve_deadline)}`),
      el("span", "phase-badge ph-" + r.phase, PHASE_TEXT[r.phase])
    );
    box.appendChild(head);

    const ul = el("ul", "fixtures");
    matches.forEach((m) => ul.appendChild(fixtureRow(m, myId)));
    if (r.bye && (!mineOnly || myBye)) {
      const li = el("li", "fixture bye-row" + (myBye ? " mine" : ""));
      li.textContent = `😴 ${r.bye.nickname} — 쉬는 주`;
      ul.appendChild(li);
    }
    box.appendChild(ul);
    container.appendChild(box);
  }
}

function settingsLines(d) {
  const s = d.league.settings;
  const subjects = d.league.subjects.map((x) => `${x.name} ${x.count}문제`).join(", ");
  const lines = [
    ["과목", `${subjects} (경기마다 총 ${d.league.questions_per_match}문제)`],
    ["첫 경기", s.start_date ? fmtYmd(s.start_date) + " 시작" : "시작하는 날"],
    ["한 경기", `${s.round_days}일 — 문제 만들기 ${s.make_days}일, 풀기 ${s.round_days - s.make_days}일 (마감 ${s.deadline_time})`],
    ["대진", s.legs === 2 ? "모두와 두 번씩" : "모두와 한 번씩"],
    ["승점", `승 ${s.points.win} · 무 ${s.points.draw} · 패 ${s.points.lose}`],
    ["인원", s.max_members ? `최대 ${s.max_members}명` : "제한 없음"],
  ];
  if (d.league.rewards.length) {
    lines.push(["상품·벌칙", d.league.rewards.map((r) => {
      const range = r.from === r.to ? `${r.from}등` : `${r.from}~${r.to}등`;
      return `${range} ${r.kind === "penalty" ? "벌칙" : "상품"}: ${r.text}`;
    }).join(" / ")]);
  }
  return lines;
}

function renderSettings(dl, d) {
  dl.innerHTML = "";
  for (const [k, v] of settingsLines(d)) {
    dl.append(el("dt", null, k), el("dd", null, v));
  }
}

// ===== 관리자: 내 리그 목록 =====
async function openAdmin() {
  const { ok, data } = await api("/admin/leagues");
  if (!ok) return goLanding();
  const list = $("adminLeagueList");
  list.innerHTML = "";
  $("adminEmpty").classList.toggle("hidden", data.leagues.length > 0);
  for (const lg of data.leagues) {
    const li = el("li");
    const btn = el("button", "league-item");
    const top = el("div", "league-item-top");
    const badge = el("span");
    setStatusBadge(badge, lg.status);
    top.append(el("b", null, lg.name), badge);
    btn.append(top, el("span", "hint", `학생 ${lg.member_count}명 · 코드 ${lg.code}`));
    btn.addEventListener("click", () => openAdminLeague(lg.id));
    li.appendChild(btn);
    list.appendChild(li);
  }
  show("adminView");
}
$("newLeagueBtn").addEventListener("click", () => openLeagueForm(null));

// ===== 관리자: 리그 만들기 / 설정 수정 =====
function fillSelect(sel, from, to, labelFn, value) {
  sel.innerHTML = "";
  for (let n = from; n <= to; n++) {
    const o = el("option", null, labelFn(n));
    o.value = n;
    sel.appendChild(o);
  }
  sel.value = Math.min(Math.max(value, from), to);
}
function dayLabel(n) {
  return n === 7 ? "7일 (1주)" : n === 14 ? "14일 (2주)" : `${n}일`;
}
function syncMakeDays() {
  const rd = Number($("fRoundDays").value);
  fillSelect($("fMakeDays"), 1, rd - 1, (n) => `${n}일`, Number($("fMakeDays").value) || 3);
}

function openLeagueForm(detail) {
  editingLeagueId = detail ? detail.league.id : null;
  $("formTitle").textContent = detail ? "리그 설정 수정" : "새 리그 만들기";
  $("formSubmitBtn").textContent = detail ? "설정 저장하기" : "리그 만들기 (코드 발급)";
  setMsg($("formMsg"), "");
  const s = detail ? detail.league.settings : null;
  const today = todayKstYmd();

  $("fName").value = detail ? detail.league.name : "";
  $("fNotice").value = detail ? detail.league.notice : "";
  $("fStartDate").min = today;
  $("fStartDate").value = s && s.start_date && s.start_date >= today ? s.start_date : today;
  $("fDeadlineTime").value = s ? s.deadline_time : "22:00";
  fillSelect($("fRoundDays"), 2, 14, dayLabel, s ? s.round_days : 7);
  $("fMakeDays").value = s ? s.make_days : 3;
  syncMakeDays();
  $("fMakeDays").value = s ? s.make_days : 3;
  $("fLegs").value = s ? s.legs : 1;
  $("fPtsWin").value = s ? s.points.win : 3;
  $("fPtsDraw").value = s ? s.points.draw : 1;
  $("fPtsLose").value = s ? s.points.lose : 0;
  $("fMax").value = s ? s.max_members : 0;
  $("fExpect").value = detail && detail.members.length >= 2 ? detail.members.length : 20;

  $("subjectRows").innerHTML = "";
  const subjects = detail ? detail.league.subjects : [{ name: "", count: 3 }];
  subjects.forEach((x) => addSubjectRow(x.name, x.count));
  $("rewardRows").innerHTML = "";
  (detail ? detail.league.rewards : []).forEach((r) => addRewardRow(r));

  updatePreview();
  show("leagueFormView");
}

$("formBackBtn").addEventListener("click", () => {
  if (editingLeagueId) openAdminLeague(editingLeagueId);
  else openAdmin();
});
$("fRoundDays").addEventListener("change", () => { syncMakeDays(); updatePreview(); });
["fStartDate", "fDeadlineTime", "fMakeDays", "fLegs", "fExpect"].forEach((id) =>
  $(id).addEventListener("input", updatePreview)
);

// 일정 미리보기: 1주차가 실제로 어떻게 흘러가는지, 몇 주가 걸리는지
function updatePreview() {
  const start = $("fStartDate").value || todayKstYmd();
  const rd = Number($("fRoundDays").value);
  const md = Number($("fMakeDays").value);
  const time = $("fDeadlineTime").value || "22:00";
  const legs = Number($("fLegs").value);
  const ol = $("schedulePreview");
  ol.innerHTML = "";
  [
    `${fmtYmd(start)} 0시 — 1주차 시작, 상대 공개`,
    `~ ${fmtYmd(addDays(start, md - 1))} ${time} — 상대에게 낼 문제 만들기 (${md}일)`,
    `~ ${fmtYmd(addDays(start, rd - 1))} ${time} — 상대 문제 풀기 · 자동 채점 (${rd - md}일)`,
    `${fmtYmd(addDays(start, rd))} — 다음 주차 시작`,
  ].forEach((t) => ol.appendChild(el("li", null, t)));

  const n = Math.max(2, Math.min(60, Number($("fExpect").value) || 2));
  const weeks = weeksFor(n, legs);
  $("previewWeeks").textContent =
    `총 ${weeks}주 · ${fmtYmd(addDays(start, weeks * rd - 1))}에 끝`;
  $("previewBye").textContent = n % 2 === 1
    ? `😴 홀수라서 매주 1명씩 돌아가며 쉬어요 (한 사람당 ${legs}번). 쉬는 주는 승점에 영향 없어요.`
    : "짝수라서 매주 모두 경기해요.";

  const total = [...document.querySelectorAll("#subjectRows .subject-row")]
    .reduce((sum, row) => sum + (Number(row.querySelector(".subject-count").value) || 0), 0);
  $("subjectTotal").textContent = `경기마다 총 ${total}문제`;
}

function addSubjectRow(name = "", count = 3) {
  const row = el("div", "subject-row");
  const nameInput = el("input", "subject-name");
  nameInput.type = "text";
  nameInput.placeholder = "과목 (예: 영어)";
  nameInput.maxLength = 20;
  nameInput.value = name;
  const countInput = el("input", "subject-count");
  countInput.type = "number";
  countInput.min = 1;
  countInput.max = 20;
  countInput.value = count;
  countInput.title = "문제 수";
  countInput.addEventListener("input", updatePreview);
  const unit = el("span", "unit", "문제");
  const del = el("button", "subject-del", "✕");
  del.type = "button";
  del.addEventListener("click", () => { row.remove(); updatePreview(); });
  row.append(nameInput, countInput, unit, del);
  $("subjectRows").appendChild(row);
  updatePreview();
}
$("addSubjectBtn").addEventListener("click", () => addSubjectRow());

function addRewardRow(r) {
  const row = el("div", "reward-row");
  const from = el("input", "reward-from");
  from.type = "number";
  from.min = 1;
  from.placeholder = "1";
  from.title = "시작 등수";
  const to = el("input", "reward-to");
  to.type = "number";
  to.min = 1;
  to.placeholder = "3";
  to.title = "끝 등수";
  const kind = el("select", "reward-kind");
  kind.append(new Option("상품", "reward"), new Option("벌칙", "penalty"));
  const text = el("input", "reward-text");
  text.type = "text";
  text.placeholder = "내용 (예: 치킨)";
  text.maxLength = 100;
  if (r) {
    from.value = r.from;
    to.value = r.to;
    kind.value = r.kind;
    text.value = r.text;
  }
  const del = el("button", "subject-del", "✕");
  del.type = "button";
  del.addEventListener("click", () => row.remove());
  row.append(from, el("span", null, "~"), to, el("span", null, "등"), kind, text, del);
  $("rewardRows").appendChild(row);
}
$("addRewardBtn").addEventListener("click", () => addRewardRow());

$("leagueForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const subjects = [];
  document.querySelectorAll("#subjectRows .subject-row").forEach((row) => {
    const name = row.querySelector(".subject-name").value.trim();
    if (name) subjects.push({ name, count: parseInt(row.querySelector(".subject-count").value) });
  });
  const rewards = [];
  for (const row of document.querySelectorAll("#rewardRows .reward-row")) {
    const text = row.querySelector(".reward-text").value.trim();
    const fromV = row.querySelector(".reward-from").value;
    if (!text && !fromV) continue; // 빈 줄은 무시
    rewards.push({
      from: parseInt(fromV),
      to: parseInt(row.querySelector(".reward-to").value || fromV),
      kind: row.querySelector(".reward-kind").value,
      text,
    });
  }
  const body = {
    name: $("fName").value,
    notice: $("fNotice").value,
    subjects,
    start_date: $("fStartDate").value,
    deadline_time: $("fDeadlineTime").value,
    round_days: parseInt($("fRoundDays").value),
    make_days: parseInt($("fMakeDays").value),
    legs: parseInt($("fLegs").value),
    points: {
      win: parseInt($("fPtsWin").value),
      draw: parseInt($("fPtsDraw").value),
      lose: parseInt($("fPtsLose").value),
    },
    max_members: parseInt($("fMax").value) || 0,
    rewards,
  };
  const url = editingLeagueId ? `/leagues/${editingLeagueId}/settings` : "/leagues";
  const { ok, data } = await api(url, body);
  if (ok) openAdminLeague(editingLeagueId || data.league_id);
  else setMsg($("formMsg"), data.error || "저장하지 못했어요.");
});

// ===== 관리자: 리그 관리 화면 =====
let adminDetail = null;

async function openAdminLeague(id) {
  const { ok, data } = await api(`/leagues/${id}`);
  if (!ok) {
    alert(data.error || "리그를 불러오지 못했어요.");
    return openAdmin();
  }
  adminLeagueId = id;
  adminDetail = data;
  syncClock(data.now);
  const d = data;
  const lg = d.league;
  const recruiting = lg.status === "recruiting";
  const running = lg.status === "running";

  $("aName").textContent = lg.name;
  setStatusBadge($("aStatus"), lg.status);
  $("aCode").textContent = lg.code;
  $("aCodeHint").textContent = recruiting
    ? "학생들에게 이 코드를 알려 주세요"
    : "리그가 시작돼서 더 이상 들어올 수 없어요";

  // 주차 안내
  const weekInfo = $("aWeekInfo");
  weekInfo.classList.toggle("hidden", recruiting);
  if (running) weekInfo.textContent = `${d.focus_week}주차 / 총 ${d.total_weeks}주`;
  if (lg.status === "finished") weekInfo.textContent = `🏁 리그가 끝났어요! (총 ${d.total_weeks}주)`;

  // 이번 주 진행 상황 + 단계 넘기기
  $("aProgressCard").classList.toggle("hidden", !running);
  if (running) {
    const r = d.rounds.find((x) => x.week === d.focus_week);
    $("aProgressTitle").textContent = `${r.week}주차 진행 상황`;
    const phaseBox = $("aPhaseBox");
    phaseBox.innerHTML = "";
    phaseBox.appendChild(renderPhase(r, false));
    const list = $("aProgressList");
    list.innerHTML = "";
    const mark = (made, done) => `${made ? "✏️✔" : "✏️✘"} ${done ? "🎯✔" : "🎯✘"}`;
    for (const m of r.matches) {
      const li = el("li");
      li.append(
        el("span", "pg-name", m.p1.nickname),
        el("span", "pg-mark", mark(m.p1_made, m.p1_done)),
        el("span", "pg-vs", "vs"),
        el("span", "pg-mark", mark(m.p2_made, m.p2_done)),
        el("span", "pg-name", m.p2.nickname)
      );
      list.appendChild(li);
    }
    if (r.bye) list.appendChild(el("li", "bye-row", `😴 ${r.bye.nickname} — 쉬는 주`));

    const advance = {
      upcoming: ["start_now", `▶️ ${r.week}주차 지금 바로 시작하기`],
      make: ["open_solve", "⏩ 문제 만들기 마감하고 지금 풀기 시작"],
      solve: ["close", "🏁 이번 주 경기 지금 마감하기"],
    }[r.phase];
    const btn = $("aAdvanceBtn");
    btn.classList.toggle("hidden", !advance);
    if (advance) {
      btn.textContent = advance[1];
      btn.dataset.action = advance[0];
    }
    setMsg($("aAdvanceMsg"), "");
  }

  // 순위표 · 전체 일정
  $("aStandingsCard").classList.toggle("hidden", recruiting);
  $("aScheduleCard").classList.toggle("hidden", recruiting);
  if (!recruiting) {
    renderStandings($("aStandings"), d.standings, lg.rewards, null);
    renderSchedule($("aSchedule"), d, null, false);
  }

  // 참가 학생 (모집 중이면 내보내기 가능)
  const ul = $("aMemberList");
  ul.innerHTML = "";
  $("aMemberCount").textContent = lg.settings.max_members
    ? `${d.members.length}/${lg.settings.max_members}명`
    : `${d.members.length}명`;
  $("aEmptyMembers").classList.toggle("hidden", d.members.length > 0);
  for (const m of d.members) {
    const li = el("li", null, m.nickname);
    if (recruiting) {
      const x = el("button", "kick", "✕");
      x.title = "내보내기";
      x.addEventListener("click", async () => {
        if (!confirm(`${m.nickname} 학생을 리그에서 내보낼까요?`)) return;
        await api(`/leagues/${id}/kick`, { user_id: m.id });
        openAdminLeague(id);
      });
      li.appendChild(x);
    }
    ul.appendChild(li);
  }

  // 시작 버튼 + 예상 일정
  $("aStartBox").classList.toggle("hidden", !recruiting);
  if (recruiting) {
    const n = d.members.length;
    const weeks = weeksFor(n, lg.settings.legs);
    let hint = n < 2
      ? "학생이 2명 이상 들어오면 시작할 수 있어요."
      : `지금 ${n}명 → 총 ${weeks}주 경기. 시작하면 대진이 무작위로 추첨돼요.`;
    if (n >= 2 && n % 2 === 1) hint += " 홀수라서 매주 1명씩 돌아가며 쉬어요.";
    $("aStartHint").textContent = hint;
    $("aStartBtn").disabled = n < 2;
    setMsg($("aStartMsg"), "");
  }

  renderSettings($("aSettings"), d);
  if (lg.notice) {
    $("aSettings").append(el("dt", null, "안내"), el("dd", null, lg.notice));
  }
  $("aEditBtn").classList.toggle("hidden", !recruiting);
  $("aDeleteBtn").classList.toggle("hidden", !recruiting);

  show("adminLeagueView");
}

$("adminLeagueBackBtn").addEventListener("click", openAdmin);
$("aEditBtn").addEventListener("click", () => openLeagueForm(adminDetail));

$("aStartBtn").addEventListener("click", async () => {
  if (!confirm("리그를 시작할까요? 시작하면 학생이 더 들어올 수 없고 설정도 바꿀 수 없어요.")) return;
  const { ok, data } = await api(`/leagues/${adminLeagueId}/start`, {});
  if (ok) openAdminLeague(adminLeagueId);
  else setMsg($("aStartMsg"), data.error || "리그를 시작하지 못했어요.");
});

$("aAdvanceBtn").addEventListener("click", async () => {
  const btn = $("aAdvanceBtn");
  if (!confirm(`${btn.textContent.trim()}?\n원래 일정보다 앞당겨져요.`)) return;
  const { ok, data } = await api(`/leagues/${adminLeagueId}/advance`, { action: btn.dataset.action });
  if (ok) openAdminLeague(adminLeagueId);
  else setMsg($("aAdvanceMsg"), data.error || "바꾸지 못했어요.");
});

$("aDeleteBtn").addEventListener("click", async () => {
  if (!confirm("이 리그를 지울까요? 되돌릴 수 없어요.")) return;
  const { ok, data } = await api(`/leagues/${adminLeagueId}/delete`, {});
  if (ok) openAdmin();
  else alert(data.error || "지우지 못했어요.");
});

// ===== 학생: 입장 =====
$("joinForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const { ok, data } = await api("/leagues/join", { code: $("joinCode").value.trim() });
  if (ok) {
    $("joinForm").reset();
    setMsg($("joinMsg"), "");
    openStudent();
  } else {
    setMsg($("joinMsg"), data.error || "입장하지 못했어요.");
  }
});

// ===== 학생: 리그 홈 =====
async function openStudent() {
  await loadMe();
  if (!me) return goLanding();
  if (!me.student_league_id) return show("joinView");

  const [detail, cur] = await Promise.all([
    api(`/leagues/${me.student_league_id}`),
    api("/matches/current"),
  ]);
  if (!detail.ok) return show("joinView");
  studentData = detail.data;
  currentMatch = cur.data;
  syncClock(studentData.now);
  renderStudent();
  show("studentView");
}

function renderStudent() {
  const d = studentData;
  const lg = d.league;
  const recruiting = lg.status === "recruiting";

  $("sName").textContent = lg.name;
  setStatusBadge($("sStatus"), lg.status);
  $("sWeekInfo").classList.toggle("hidden", recruiting);
  if (lg.status === "running") $("sWeekInfo").textContent = `${d.focus_week}주차 / 총 ${d.total_weeks}주`;
  if (lg.status === "finished") $("sWeekInfo").textContent = "🏁 리그가 끝났어요! 최종 순위를 확인하세요";
  $("sNotice").classList.toggle("hidden", !lg.notice);
  $("sNotice").textContent = lg.notice ? `📢 ${lg.notice}` : "";

  // 모집 중: 규칙과 명단을 보여 주고 기다린다
  $("sWaitCard").classList.toggle("hidden", !recruiting);
  if (recruiting) {
    const dl = el("dl", "settings-list");
    for (const [k, v] of settingsLines(d)) dl.append(el("dt", null, k), el("dd", null, v));
    $("sRules").innerHTML = "";
    $("sRules").appendChild(dl);
    $("sMemberCount").textContent = `${d.members.length}명`;
    const ul = $("sMemberList");
    ul.innerHTML = "";
    d.members.forEach((m) => {
      const li = el("li", null, m.nickname);
      if (m.id === d.my_user_id) li.classList.add("me");
      ul.appendChild(li);
    });
    setMsg($("sLeaveMsg"), "");
  }

  ["sMatchCard", "sStandingsCard", "sScheduleCard", "sRecordCard"].forEach((id) =>
    $(id).classList.toggle("hidden", recruiting)
  );
  if (recruiting) return;

  renderMatchCard();
  renderStandings($("sStandings"), d.standings, lg.rewards, d.my_user_id);
  renderSchedule($("sSchedule"), d, d.my_user_id, onlyMine);
  renderRecord();
}

const OUTCOME = {
  win: ["승", "o-win"], lose: ["패", "o-lose"], draw: ["무", "o-draw"],
};

function renderMatchCard() {
  const c = currentMatch;
  const body = $("sMatchBody");
  body.innerHTML = "";
  ["sMakeBtn", "sSolveBtn", "sReviewBtn"].forEach((id) => $(id).classList.add("hidden"));
  if (!c || !c.week) return;

  $("sMatchTitle").textContent = c.state === "finished" ? `🏁 마지막 경기 (${c.week}주차)` : `⚽ ${c.week}주차 경기`;

  if (c.bye) {
    body.appendChild(el("p", "opponent", "😴 이번 주는 쉬는 주예요"));
    body.appendChild(el("p", "hint",
      "참가 인원이 홀수라 매주 한 명씩 돌아가며 쉬어요. 쉬는 주는 경기수·승점에 영향이 없어요."));
    const next = studentData.rounds.find((r) => r.week === c.week + 1);
    if (next) {
      const line = el("p", "deadline-line");
      line.append(`다음 경기: ${next.week}주차, ${fmtDT(next.start_at)} 시작 (`, countdown(next.start_at), ")");
      body.appendChild(line);
    }
    return;
  }

  const opp = el("p", "opponent");
  opp.append("상대: ", el("strong", null, c.opponent.nickname));
  body.appendChild(opp);
  body.appendChild(renderPhase(c, true));

  // 결과가 났으면 크게 보여 준다
  if (c.result) {
    const [label, cls] = OUTCOME[c.outcome] || ["", ""];
    const res = el("div", "match-result " + cls);
    let text = `${label === "승" ? "🎉 승리" : label === "무" ? "🤝 무승부" : "😢 패배"}`;
    if (c.forfeit === "both") text += " (둘 다 문제를 안 만들어 기권)";
    else if (c.forfeit) text += c.outcome === "win" ? " (상대 기권)" : " (문제를 안 만들어 기권)";
    res.append(el("b", null, text));
    if (c.forfeit !== "both") {
      res.append(el("span", "match-score", `${c.my_score ?? 0} : ${c.opp_score ?? 0}`));
    }
    body.appendChild(res);
  }

  // 양쪽 진행 상황
  const grid = el("ul", "status-grid");
  const item = (ok, text) => grid.appendChild(el("li", ok ? "st-ok" : "st-wait", `${ok ? "✅" : "⬜"} ${text}`));
  item(c.my_made, c.my_made ? `내 문제 ${c.total}개 완성` : `내 문제 아직 (${c.total}개 필요)`);
  item(c.opp_made, c.opp_made ? "상대 문제 준비됨" : "상대 문제 아직");
  item(c.i_solved, c.i_solved ? `내 풀이 제출 (${c.my_score}/${c.total} 맞힘)` : "내 풀이 아직");
  item(c.opp_solved, c.opp_solved ? "상대 풀이 제출" : "상대 풀이 아직");
  body.appendChild(grid);

  // 안내 + 버튼
  const tip = el("p", "match-status");
  if (c.phase === "upcoming" || c.phase === "make") {
    $("sMakeBtn").classList.remove("hidden");
    $("sMakeBtn").textContent = c.my_made ? "✏️ 내 문제 고치기" : "✏️ 내 문제 만들기";
    tip.textContent = c.my_made
      ? "문제를 다 만들었어요! 마감 전까지는 고칠 수 있어요. 마감 뒤에 서로의 문제를 풀어요."
      : "⚠️ 마감까지 문제를 안 만들면 기권패예요.";
  } else if (c.phase === "solve" && !c.result) {
    if (c.i_solved) {
      tip.textContent = "상대가 풀면 바로 결과가 나와요. 안 풀면 마감 때 0점 처리돼요.";
    } else if (c.opp_made) {
      $("sSolveBtn").classList.remove("hidden");
      tip.textContent = "상대 문제가 열렸어요! 마감 전에 풀어 주세요. 안 풀면 0점이에요.";
    } else {
      tip.textContent = "상대가 문제를 만들지 않아서 이 경기는 상대 기권으로 처리돼요.";
    }
  }
  if (tip.textContent) body.appendChild(tip);
  if (c.i_solved) $("sReviewBtn").classList.remove("hidden");
}

function renderRecord() {
  const d = studentData;
  const myId = d.my_user_id;
  const ul = $("sRecordList");
  ul.innerHTML = "";
  let w = 0, dr = 0, l = 0;
  for (const r of d.rounds) {
    if (r.bye && r.bye.id === myId && r.phase === "done") {
      const li = el("li");
      li.append(el("span", "wk", `${r.week}주차`), el("span", "bye", "😴 쉬는 주"));
      ul.appendChild(li);
      continue;
    }
    const m = r.matches.find((x) => x.p1.id === myId || x.p2.id === myId);
    if (!m || m.result === null) continue;
    const isP1 = m.p1.id === myId;
    const opp = isP1 ? m.p2 : m.p1;
    let outcome;
    if (m.result === "draw") outcome = "draw";
    else if (m.result === "both_lose") outcome = "lose";
    else outcome = (m.result === "p1") === isP1 ? "win" : "lose";
    if (outcome === "win") w++;
    else if (outcome === "draw") dr++;
    else l++;
    const myFf = m.forfeit === "both" || m.forfeit === (isP1 ? "p1" : "p2");
    const oppFf = m.forfeit === (isP1 ? "p2" : "p1");
    const [label, cls] = OUTCOME[outcome];
    const li = el("li");
    li.append(
      el("span", "wk", `${r.week}주차`),
      el("span", "h-opp", `vs ${opp.nickname}`),
      el("span", "h-score", m.result === "both_lose" ? "-" : `${isP1 ? m.p1_score : m.p2_score} : ${isP1 ? m.p2_score : m.p1_score}`),
      el("span", "h-outcome " + cls, myFf ? "기권패" : oppFf ? "기권승" : label)
    );
    ul.appendChild(li);
  }
  $("sRecordSummary").textContent = `${w}승 ${dr}무 ${l}패`;
  if (!ul.children.length) ul.appendChild(el("li", "hint", "아직 끝난 경기가 없어요."));
}

$("sOnlyMineBtn").addEventListener("click", () => setScheduleFilter(true));
$("sAllBtn").addEventListener("click", () => setScheduleFilter(false));
function setScheduleFilter(mine) {
  onlyMine = mine;
  $("sOnlyMineBtn").classList.toggle("active", mine);
  $("sAllBtn").classList.toggle("active", !mine);
  renderSchedule($("sSchedule"), studentData, studentData.my_user_id, onlyMine);
}

$("sLeaveBtn").addEventListener("click", async () => {
  if (!confirm("리그에서 나갈까요?")) return;
  const { ok, data } = await api("/leagues/leave", {});
  if (ok) openStudent();
  else setMsg($("sLeaveMsg"), data.error || "나가지 못했어요.");
});

// ===== 문제 만들기 =====
async function openQuestions() {
  const { ok, data } = await api("/questions/mine");
  if (!ok) return alert(data.error || "문제 화면을 열 수 없어요.");

  const info = $("qInfo");
  info.innerHTML = "";
  info.append(`${data.week}주차 · 상대 `, el("b", null, data.opponent),
    `에게 낼 문제 · 마감 ${fmtDT(data.make_deadline)} (`, countdown(data.make_deadline), ")");
  $("qHint").textContent = data.editable
    ? "과목별로 정해진 개수만큼 만들어 주세요. 마감 전까지는 몇 번이든 고칠 수 있어요."
    : "마감이 지나서 더 이상 고칠 수 없어요.";
  $("saveBox").classList.toggle("hidden", !data.editable);

  const bySubject = {};
  for (const q of data.questions) (bySubject[q.subject] = bySubject[q.subject] || []).push(q);

  const forms = $("questionForms");
  forms.innerHTML = "";
  for (const subj of data.subjects) {
    const card = el("div", "card");
    card.appendChild(el("h3", null, `${subj.name} (${subj.count}문제)`));
    for (let i = 0; i < subj.count; i++) {
      card.appendChild(buildQuestionBlock(subj.name, i, (bySubject[subj.name] || [])[i] || null));
    }
    forms.appendChild(card);
  }
  forms.querySelectorAll("input, textarea, select, button").forEach((x) => (x.disabled = !data.editable));
  setMsg($("saveQMsg"), "");
  show("questionsView");
}

function buildQuestionBlock(subject, index, existing) {
  const box = el("div", "q-block");
  box.dataset.subject = subject;
  box.appendChild(el("div", "q-title", `${index + 1}번 문제`));

  const content = el("textarea", "q-content");
  content.placeholder = "문제 내용을 적어 주세요";
  content.rows = 2;
  if (existing) content.value = existing.content;
  box.appendChild(label("문제", content));

  const typeSel = el("select", "q-type");
  typeSel.append(new Option("객관식", "mc"), new Option("주관식", "sa"));
  if (existing) typeSel.value = existing.qtype;
  box.appendChild(label("유형", typeSel));

  // 객관식: 보기 2~5개, 동그라미로 정답 고르기
  const mcArea = el("div", "mc-area");
  const choiceWrap = el("div", "choice-wrap");
  const group = `${subject}-${index}`;
  const isMc = existing && existing.qtype === "mc";
  const choices = isMc ? existing.choices : ["", "", "", ""];
  const answerIdx = isMc ? parseInt(existing.answer) : 0;
  choices.forEach((c, i) => choiceWrap.appendChild(makeChoiceRow(group, i, c, answerIdx === i)));
  mcArea.appendChild(choiceWrap);
  const tools = el("div", "choice-tools");
  const addBtn = el("button", "btn btn-small", "+ 보기");
  addBtn.type = "button";
  const delBtn = el("button", "btn btn-small", "− 보기");
  delBtn.type = "button";
  addBtn.addEventListener("click", () => {
    const n = choiceWrap.children.length;
    if (n < 5) choiceWrap.appendChild(makeChoiceRow(group, n, "", false));
  });
  delBtn.addEventListener("click", () => {
    if (choiceWrap.children.length > 2) choiceWrap.lastChild.remove();
    if (!choiceWrap.querySelector(".choice-radio:checked")) choiceWrap.querySelector(".choice-radio").checked = true;
  });
  tools.append(addBtn, delBtn, el("span", "hint", "왼쪽 동그라미로 정답을 고르세요 (보기 2~5개)"));
  mcArea.appendChild(tools);
  box.appendChild(mcArea);

  const saArea = el("div", "sa-area");
  const saAnswer = el("input", "sa-answer");
  saAnswer.placeholder = "정답 (띄어쓰기·대소문자는 채점 때 무시돼요)";
  if (existing && existing.qtype === "sa") saAnswer.value = existing.answer;
  saArea.appendChild(label("정답", saAnswer));
  box.appendChild(saArea);

  const expl = el("textarea", "q-expl");
  expl.placeholder = "해설 (채점 뒤 상대에게 보여요. 안 써도 돼요)";
  expl.rows = 2;
  if (existing) expl.value = existing.explanation;
  box.appendChild(label("해설", expl));

  function sync() {
    mcArea.classList.toggle("hidden", typeSel.value !== "mc");
    saArea.classList.toggle("hidden", typeSel.value === "mc");
  }
  typeSel.addEventListener("change", sync);
  sync();
  return box;
}

function makeChoiceRow(group, idx, value, checked) {
  const row = el("div", "choice-row");
  const radio = el("input", "choice-radio");
  radio.type = "radio";
  radio.name = group;
  radio.checked = checked;
  const text = el("input", "choice-text");
  text.type = "text";
  text.placeholder = `보기 ${idx + 1}`;
  text.value = value || "";
  row.append(radio, text);
  return row;
}

function label(text, node) {
  const l = el("label", null, text);
  l.appendChild(node);
  return l;
}

$("saveQuestionsBtn").addEventListener("click", async () => {
  const questions = [];
  $("questionForms").querySelectorAll(".q-block").forEach((box) => {
    const q = {
      subject: box.dataset.subject,
      qtype: box.querySelector(".q-type").value,
      content: box.querySelector(".q-content").value,
      explanation: box.querySelector(".q-expl").value,
    };
    if (q.qtype === "mc") {
      q.choices = [];
      q.answer = 0;
      box.querySelectorAll(".choice-row").forEach((r, i) => {
        q.choices.push(r.querySelector(".choice-text").value);
        if (r.querySelector(".choice-radio").checked) q.answer = i;
      });
    } else {
      q.answer = box.querySelector(".sa-answer").value;
    }
    questions.push(q);
  });
  const { ok, data } = await api("/questions", { questions });
  if (ok) setMsg($("saveQMsg"), "저장했어요! 👍 마감 전까지는 다시 고칠 수 있어요.", true);
  else setMsg($("saveQMsg"), data.error || "저장하지 못했어요.");
});
$("sMakeBtn").addEventListener("click", openQuestions);

// ===== 상대 문제 풀기 =====
async function openSolve() {
  const c = currentMatch;
  const { ok, data } = await api(`/matches/${c.match_id}/questions`);
  if (!ok) return alert(data.error || "문제를 불러올 수 없어요.");

  const info = $("solveInfo");
  info.innerHTML = "";
  info.append(`${c.week}주차 · `, el("b", null, c.opponent.nickname),
    `가 낸 문제 ${data.questions.length}개 · 마감 ${fmtDT(data.solve_deadline)} (`,
    countdown(data.solve_deadline), ")");

  const forms = $("solveForms");
  forms.innerHTML = "";
  data.questions.forEach((q, i) => forms.appendChild(buildSolveBlock(q, i)));
  setMsg($("submitMsg"), "");
  $("submitAnswersBtn").disabled = false;
  show("solveView");
}

function buildSolveBlock(q, i) {
  const box = el("div", "card q-block");
  box.dataset.qid = q.id;
  box.dataset.qtype = q.qtype;
  box.appendChild(el("div", "q-title", `${i + 1}. [${q.subject}] ${q.qtype === "mc" ? "객관식" : "주관식"}`));
  box.appendChild(el("p", "solve-content", q.content));
  if (q.qtype === "mc") {
    q.choices.forEach((c, ci) => {
      const row = el("label", "solve-choice");
      const radio = el("input");
      radio.type = "radio";
      radio.name = "solve-" + q.id;
      radio.value = ci;
      row.append(radio, el("span", null, c));
      box.appendChild(row);
    });
  } else {
    const input = el("input", "solve-answer");
    input.type = "text";
    input.placeholder = "정답을 입력하세요";
    box.appendChild(input);
  }
  return box;
}

$("submitAnswersBtn").addEventListener("click", async () => {
  const answers = {};
  let blank = 0;
  $("solveForms").querySelectorAll(".q-block").forEach((box) => {
    let v;
    if (box.dataset.qtype === "mc") {
      const checked = box.querySelector("input[type=radio]:checked");
      v = checked ? checked.value : "";
    } else {
      v = box.querySelector(".solve-answer").value;
    }
    if (!String(v).trim()) blank++;
    answers[box.dataset.qid] = v;
  });
  const ask = blank
    ? `안 푼 문제가 ${blank}개 있어요. 그래도 제출할까요? (제출은 한 번만 할 수 있어요)`
    : "제출할까요? 제출은 한 번만 할 수 있어요.";
  if (!confirm(ask)) return;
  $("submitAnswersBtn").disabled = true;
  const { ok, data } = await api(`/matches/${currentMatch.match_id}/submit`, { answers });
  if (ok) showResult(data);
  else {
    $("submitAnswersBtn").disabled = false;
    setMsg($("submitMsg"), data.error || "제출하지 못했어요.");
  }
});
$("sSolveBtn").addEventListener("click", openSolve);

// ===== 채점 결과 =====
function showResult(data) {
  $("resultScore").textContent = `${data.total}문제 중 ${data.score}개 맞았어요!`;
  const list = $("resultList");
  list.innerHTML = "";
  data.results.forEach((r, i) => {
    const box = el("div", "card result-block " + (r.is_correct ? "correct" : "wrong"));
    box.appendChild(el("div", "result-q", `${i + 1}. [${r.subject}] ${r.content}`));
    box.appendChild(el("p", "result-mark", r.is_correct ? "⭕ 정답" : "❌ 오답"));
    let line;
    if (r.qtype === "mc") {
      const mine = r.choices[parseInt(r.given)];
      line = `내 답: ${mine !== undefined ? mine : "(안 고름)"} · 정답: ${r.choices[parseInt(r.correct_answer)]}`;
    } else {
      line = `내 답: ${r.given || "(빈칸)"} · 정답: ${r.correct_answer}`;
    }
    box.appendChild(el("p", "result-line", line));
    if (r.explanation) box.appendChild(el("p", "result-expl", "해설: " + r.explanation));
    list.appendChild(box);
  });
  show("resultView");
}

$("sReviewBtn").addEventListener("click", async () => {
  const { ok, data } = await api(`/matches/${currentMatch.match_id}/review`);
  if (ok) showResult(data);
  else alert(data.error || "결과를 불러올 수 없어요.");
});

// ===== 페이지 열 때: 로그인 상태 확인, 마지막 역할 화면으로 =====
(async function start() {
  await loadMe();
  const role = recall("role");
  if (me && role) goRole(role);
  else goLanding();
})();
