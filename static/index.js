// ===== 화면 요소 =====
const authView = document.getElementById("authView");
const homeView = document.getElementById("homeView");
const userArea = document.getElementById("userArea");
const navNickname = document.getElementById("navNickname");

// 랜딩 화면 요소
const landingView = document.getElementById("landingView");
const authBackBtn = document.getElementById("authBackBtn");

// 로그인 후 첫 화면(리그 없음): 고르기 / 코드 입력 / 리그 만들기
const chooseView = document.getElementById("chooseView");
const joinView = document.getElementById("joinView");
const createView = document.getElementById("createView");

// 모집 중: 대기 안내 + 리그 나가기
const waitHint = document.getElementById("waitHint");
const leaveBtn = document.getElementById("leaveBtn");
const leaveMsg = document.getElementById("leaveMsg");

// 상단바 게스트 버튼 (로그인 안 했을 때)
const guestArea = document.getElementById("guestArea");
const navLoginBtn = document.getElementById("navLoginBtn");
const navRegisterBtn = document.getElementById("navRegisterBtn");

// 리그 화면 요소
const noLeagueView = document.getElementById("noLeagueView");
const leagueView = document.getElementById("leagueView");
const joinForm = document.getElementById("joinForm");
const joinMsg = document.getElementById("joinMsg");
const createForm = document.getElementById("createForm");
const createMsg = document.getElementById("createMsg");
const leagueName2 = document.getElementById("leagueName2");
const leagueStatus = document.getElementById("leagueStatus");
const adminCodeBox = document.getElementById("adminCodeBox");
const leagueCode = document.getElementById("leagueCode");
const memberList = document.getElementById("memberList");
const memberCount = document.getElementById("memberCount");
const emptyMembers = document.getElementById("emptyMembers");

// 3단계 요소: 주차/이번주 경기/일정/순위표/시작버튼
const weekInfo = document.getElementById("weekInfo");
const matchCard = document.getElementById("matchCard");
const opponentText = document.getElementById("opponentText");
const scheduleCard = document.getElementById("scheduleCard");
const scheduleList = document.getElementById("scheduleList");
const standingsCard = document.getElementById("standingsCard");
const standingsHead = document.getElementById("standingsHead");
const standingsBody = document.getElementById("standingsBody");
const standingsTitle = document.getElementById("standingsTitle");
const standingsRule = document.getElementById("standingsRule");
const rewardLegend = document.getElementById("rewardLegend");
const historyCard = document.getElementById("historyCard");
const historyList = document.getElementById("historyList");
const historyEmpty = document.getElementById("historyEmpty");
const finalCard = document.getElementById("finalCard");
const finalWinner = document.getElementById("finalWinner");
const finalMyRank = document.getElementById("finalMyRank");
const finalAwards = document.getElementById("finalAwards");
const membersCard = document.getElementById("membersCard");
const startBtn = document.getElementById("startBtn");
const startMsg = document.getElementById("startMsg");

// 문제 만들기 화면 요소
const questionsView = document.getElementById("questionsView");
const makeQuestionsBtn = document.getElementById("makeQuestionsBtn");
const backBtn = document.getElementById("backBtn");
const questionForms = document.getElementById("questionForms");
const saveQuestionsBtn = document.getElementById("saveQuestionsBtn");
const saveQMsg = document.getElementById("saveQMsg");

// 문제 풀기 / 결과 화면 요소
const solveBtn = document.getElementById("solveBtn");
const matchStatus = document.getElementById("matchStatus");
const solveView = document.getElementById("solveView");
const solveForms = document.getElementById("solveForms");
const solveBackBtn = document.getElementById("solveBackBtn");
const submitAnswersBtn = document.getElementById("submitAnswersBtn");
const submitMsg = document.getElementById("submitMsg");
const resultView = document.getElementById("resultView");
const resultScore = document.getElementById("resultScore");
const resultBackBtn = document.getElementById("resultBackBtn");
const resultList = document.getElementById("resultList");
let currentMatchId = null;

const tabLogin = document.getElementById("tabLogin");
const tabRegister = document.getElementById("tabRegister");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginMsg = document.getElementById("loginMsg");
const registerMsg = document.getElementById("registerMsg");
const logoutBtn = document.getElementById("logoutBtn");

// ===== 서버에 요청 보내는 함수 =====
// lockBtn을 주면 처리하는 동안 그 버튼을 잠가서 두 번 눌리지 않게 한다
async function postJSON(url, body, lockBtn) {
  if (lockBtn) {
    if (lockBtn.disabled) return { ok: false, status: 0, data: { error: "처리하고 있어요. 잠시만 기다려 주세요." } };
    lockBtn.disabled = true;
  }
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    // 인터넷이 끊기는 등 서버에 닿지 못했을 때
    return { ok: false, status: 0, data: { error: "서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요." } };
  } finally {
    if (lockBtn) lockBtn.disabled = false;
  }
}

// ===== 화면 전환 =====
// 로그인 후 화면들: 한 번에 하나만 보인다
const APP_SECTIONS = ["homeView", "questionsView", "solveView", "resultView",
  "noteView", "reviewView", "studentQView", "pastView", "pastDetailView"].map((id) => document.getElementById(id));

function showOnly(section) {
  APP_SECTIONS.forEach((el) => el.classList.toggle("hidden", el !== section));
  window.scrollTo(0, 0);
}

// 홈(리그 화면)으로 돌아가기
function goHome() {
  setCountdown("qCountdown", null);
  setCountdown("solveCountdown", null);
  showOnly(homeView);
  loadMyLeague();
}

function showLoggedIn(nickname) {
  landingView.classList.add("hidden");
  authView.classList.add("hidden");
  showOnly(homeView);
  guestArea.classList.add("hidden");
  userArea.classList.remove("hidden");
  navNickname.textContent = nickname;
  loadMyLeague();
}

// 로그인 안 된 상태: 처음엔 랜딩을 보여준다
function showLoggedOut() {
  landingView.classList.remove("hidden");
  authView.classList.add("hidden");
  showOnly(null);
  guestArea.classList.remove("hidden");
  userArea.classList.add("hidden");
  renderAdminTodo(null); // 할 일 탭은 화면 밖(body)에 있어서 따로 숨긴다
}

// 로그인/회원가입 화면 보여 주기 (학생·관리자는 여기서 고르지 않는다)
function showAuth(tab) {
  landingView.classList.add("hidden");
  authView.classList.remove("hidden");
  homeView.classList.add("hidden");
  guestArea.classList.remove("hidden");
  userArea.classList.add("hidden");
  if (tab === "register") tabRegister.click();
  else tabLogin.click();
}

// 처음 화면 버튼과 위쪽 바 버튼
document.getElementById("landingLoginBtn").addEventListener("click", () => showAuth("login"));
document.getElementById("landingRegisterBtn").addEventListener("click", () => showAuth("register"));
document.getElementById("previewRegisterBtn").addEventListener("click", () => showAuth("register"));
navLoginBtn.addEventListener("click", () => showAuth("login"));
navRegisterBtn.addEventListener("click", () => showAuth("register"));
// 로그인 화면에서 처음으로 돌아가기
authBackBtn.addEventListener("click", showLoggedOut);

// ===== 로그인 후 첫 화면: 학생 / 관리자 고르기 =====
// which: "choose"(고르기) / "join"(코드 입력) / "create"(리그 만들기)
function showNoLeague(which) {
  chooseView.classList.toggle("hidden", which !== "choose");
  joinView.classList.toggle("hidden", which !== "join");
  createView.classList.toggle("hidden", which !== "create");
  joinMsg.textContent = "";
  createMsg.textContent = "";
  window.scrollTo(0, 0);
}
document.querySelectorAll("#chooseView .portal").forEach((btn) => {
  btn.addEventListener("click", () => showNoLeague(btn.dataset.go));
});
document.querySelectorAll(".back-choose").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (editingSettings) closeSettingsEdit();
    else showNoLeague("choose");
  });
});

// ===== 탭 전환 (로그인 / 회원가입) =====
tabLogin.addEventListener("click", () => {
  tabLogin.classList.add("active");
  tabRegister.classList.remove("active");
  loginForm.classList.remove("hidden");
  registerForm.classList.add("hidden");
});
tabRegister.addEventListener("click", () => {
  tabRegister.classList.add("active");
  tabLogin.classList.remove("active");
  registerForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
});

// ===== 회원가입 =====
registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  registerMsg.textContent = "";
  const body = {
    username: document.getElementById("regUsername").value,
    password: document.getElementById("regPassword").value,
    nickname: document.getElementById("regNickname").value,
  };
  const { ok, data } = await postJSON("/register", body, registerForm.querySelector("button[type=submit]"));
  if (ok) {
    // 서버가 가입과 동시에 로그인해 준다 → 바로 다음 화면으로
    registerForm.reset();
    showLoggedIn(data.nickname);
  } else {
    registerMsg.className = "msg err";
    registerMsg.textContent = data.error || "가입에 실패했어요.";
  }
});

// ===== 로그인 =====
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginMsg.textContent = "";
  const body = {
    username: document.getElementById("loginUsername").value,
    password: document.getElementById("loginPassword").value,
  };
  const { ok, data } = await postJSON("/login", body, loginForm.querySelector("button[type=submit]"));
  if (ok) {
    loginForm.reset();
    showLoggedIn(data.nickname);
  } else {
    loginMsg.className = "msg err";
    loginMsg.textContent = data.error || "로그인에 실패했어요.";
  }
});

// ===== 리그: 내 리그 정보 불러오기 =====
const STATUS_TEXT = {
  recruiting: "모집 중",
  running: "진행 중",
  finished: "끝남",
};

async function loadMyLeague() {
  const res = await fetch("/leagues/mine");
  const data = await res.json().catch(() => ({}));

  // 할 일 탭은 먼저 숨기고, 관리자 + 모집 중일 때만 아래에서 다시 보여 준다
  // (로그아웃 뒤 다른 계정으로 들어와도 남아 있지 않게)
  renderAdminTodo(null);

  // 오답 노트 카드는 리그가 시작된(진행 중·끝) 학생에게만
  // (모집 중에는 경기가 없어 틀린 문제가 생길 수 없고, 관리자는 문제를 풀지 않는다)
  const started = data.in_league && ["running", "finished"].includes(data.league.status);
  const showWrongNotes = started && !data.is_admin;
  studyCard.classList.toggle("hidden", !showWrongNotes);
  if (showWrongNotes) loadWrongNoteCount();
  else renderWrongNoteCount(0, 0);

  if (!data.in_league) {
    // 리그 없음 → 학생/관리자 고르기 화면
    noLeagueView.classList.remove("hidden");
    leagueView.classList.add("hidden");
    showNoLeague("choose");
    loadPastLink();
    return;
  }

  lastLeagueData = data;
  // 리그 있음 → 리그 정보 화면
  noLeagueView.classList.add("hidden");
  leagueView.classList.remove("hidden");

  leagueName2.textContent = data.league.name;
  leagueStatus.textContent = STATUS_TEXT[data.league.status] || data.league.status;

  const isRecruiting = data.league.status === "recruiting";
  const isRunning = data.league.status === "running" || data.league.status === "finished";

  loadPastLink();
  // 관리자 + 모집 중: 할 일 목록, 리그 코드, 설정 고치기 버튼
  const adminRecruiting = data.is_admin && isRecruiting;
  adminCodeBox.classList.toggle("hidden", !adminRecruiting);
  document.getElementById("editSettingsBtn").classList.toggle("hidden", !adminRecruiting);
  leagueCode.textContent = data.league.code;
  renderAdminTodo(adminRecruiting ? data : null);
  // 관리자 + 진행 중: 라운드별 출제 범위 카드
  const adminRunning = data.is_admin && data.league.status === "running";
  scopeCard.classList.toggle("hidden", !adminRunning);
  if (adminRunning) loadScopes();
  // 관리자 + 진행 중·끝: 진행 상황표·과목별 정답률
  const adminStarted = data.is_admin && isRunning;
  document.getElementById("progressCard").classList.toggle("hidden", !adminStarted);
  document.getElementById("accuracyCard").classList.toggle("hidden", !adminStarted);
  document.getElementById("reportCard").classList.toggle("hidden", !adminStarted);
  if (adminStarted) loadReports();
  else setCountdown("reportDeadline", null);
  if (adminStarted) {
    loadAdminProgress(data.league.status);
    loadAdminAccuracy();
  } else {
    setCountdown("progressCountdown", null);
  }

  // 참가자 명단
  memberList.innerHTML = "";
  memberCount.textContent = `(${data.members.length}명)`;
  if (data.members.length === 0) {
    emptyMembers.classList.remove("hidden");
  } else {
    emptyMembers.classList.add("hidden");
    for (const m of data.members) {
      const li = document.createElement("li");
      if (data.is_admin && isRunning) {
        // 관리자: 이름을 누르면 그 학생이 만든 문제 (끝난 경기만)
        const btn = el("button", "member-link", `${m.nickname} 📝`);
        btn.type = "button";
        btn.title = "이 학생이 만든 문제 보기";
        btn.addEventListener("click", () => openStudentQuestions(m.id));
        li.append(btn);
      } else {
        li.textContent = m.nickname; // textContent라 HTML 태그가 실행되지 않음
      }
      // 관리자: 학생 내보내기 (모집 중·진행 중, 전학 등)
      if (data.is_admin && (isRecruiting || data.league.status === "running")) {
        li.classList.add("member-row");
        const rm = el("button", "btn btn-small remove-btn", "내보내기");
        rm.type = "button";
        rm.setAttribute("aria-label", `${m.nickname} 내보내기`);
        rm.addEventListener("click", () => removeStudent(m, isRecruiting, rm));
        li.append(rm);
      }
      memberList.appendChild(li);
    }
    if (data.is_admin && isRunning) {
      memberList.setAttribute("aria-label", "학생 이름을 누르면 만든 문제를 볼 수 있어요");
    }
  }

  // ---- 주차 안내 ----
  if (isRunning && data.week) {
    weekInfo.classList.remove("hidden");
    let info = `${data.week}라운드 / 전체 ${data.total_weeks}라운드`;
    const lastRound = (data.rounds || [])[data.rounds.length - 1];
    if (lastRound && lastRound.solve_deadline) {
      info += ` · ${fmtDeadline(lastRound.solve_deadline, true)} 끝`;
    }
    weekInfo.textContent = info;
  } else {
    weekInfo.classList.add("hidden");
  }

  // ---- 이번 경기 카드 (학생, 진행 중) ----
  if (data.league.status === "running" && !data.is_admin) {
    refreshMatchStatus();
  } else {
    matchCard.classList.add("hidden");
  }

  // ---- 내 전체 일정 (학생, 진행 중) ----
  if (isRunning && Array.isArray(data.schedule) && data.schedule.length > 0) {
    scheduleCard.classList.remove("hidden");
    scheduleList.innerHTML = "";
    for (const row of data.schedule) {
      const li = document.createElement("li");
      const isNow = row.week === data.week;
      if (isNow) li.classList.add("now");
      const wk = document.createElement("span");
      wk.className = "wk";
      wk.textContent = `${row.week}라운드`;
      const rd = (data.rounds || []).find((r) => r.round === row.week);
      if (rd && rd.start) {
        const dt = document.createElement("span");
        dt.className = "rd-date";
        dt.textContent = `만들기 ~${fmtDeadline(rd.make_deadline)} · 풀기 ~${fmtDeadline(rd.solve_deadline)}`;
        wk.append(dt);
      }
      const opp = document.createElement("span");
      if (row.bye) {
        opp.textContent = "😴 쉬는 라운드";
        opp.className = "bye";
      } else {
        opp.textContent = `vs ${row.nickname}`;
      }
      li.append(wk, opp);
      scheduleList.appendChild(li);
    }
  } else {
    scheduleCard.classList.add("hidden");
  }

  // ---- 순위표·최종 결과 ----
  if (isRunning && Array.isArray(data.standings)) {
    standingsCard.classList.remove("hidden");
    renderStandings(data);
    if (!data.is_admin) loadHistory();
  } else {
    standingsCard.classList.add("hidden");
    historyCard.classList.add("hidden");
  }
  if (data.league.status === "finished" && data.final) {
    renderFinal(data);
    renderLifecycle(data);
  } else {
    finalCard.classList.add("hidden");
  }

  // ---- 리그 시작 (관리자 + 모집 중): 첫 경기 날짜 고르기 ----
  if (data.is_admin && isRecruiting) {
    startPanel.classList.remove("hidden");
    setupStartPanel(data);
  } else {
    startPanel.classList.add("hidden");
  }
  startMsg.textContent = "";

  // ---- 학생 + 모집 중: 대기 안내와 [리그 나가기] ----
  const studentWaiting = !data.is_admin && isRecruiting;
  waitHint.classList.toggle("hidden", !studentWaiting);
  leaveBtn.classList.toggle("hidden", !studentWaiting);
  leaveMsg.textContent = "";
  renderLeagueInfo(studentWaiting ? data : null);
  leagueView.classList.toggle("recruiting-solo", studentWaiting); // 한 칸 가운데 정렬

  // ---- 관리자 + 진행 중·끝: 메뉴 탭 ----
  applyAdminTabs(data.is_admin && isRunning, data.league.status);
}

// 모집 중 학생에게 리그 설정을 읽기 전용으로 보여 준다 (고칠 수는 없다)
function renderLeagueInfo(data) {
  const card = document.getElementById("leagueInfoCard");
  card.classList.toggle("hidden", !data);
  if (!data) return;
  const lg = data.league;
  const dl = document.getElementById("leagueInfoList");
  dl.innerHTML = "";
  const add = (label, value) => {
    dl.append(el("dt", "", label), el("dd", "", value));
  };
  const subjects = (lg.subjects || []).map((x) => `${x.name} ${x.count}문제`).join(" · ");
  add("과목", subjects || "—");
  (lg.subjects || []).forEach((x) => add(`${x.name} 출제 범위`, x.scope || "자유 출제"));
  add("리그 방식", lg.league_mode === "short" ? "시험 대비 단기 리그" : "전체 리그");
  const days = (lg.match_days || []).map((d) => DAY_NAMES[d]).join("·");
  add("경기 요일", days ? `${days}요일` : "—");
  add("마감 시각", lg.deadline_time || "—");
  add("문제 만들기 기간", lg.make_days ? `${lg.make_days}일` : "자동 (라운드의 절반)");
  if (lg.league_mode === "short" && lg.end_date) add("종료 희망일", fmtDate(lg.end_date));
  const prizes = (lg.rewards || []).filter((r) => r.kind !== "penalty");
  if (prizes.length) {
    add("상품", prizes.map((r) => `${r.from === r.to ? r.from + "등" : r.from + "~" + r.to + "등"} ${r.text}`).join(" · "));
  }
}

// ===== 관리자 메뉴 탭 =====
// 카드마다 data-panel(어느 탭인지)이 있고, 고른 탭의 카드만 보여 준다.
// 카드 자체를 보일지(hidden)는 원래 코드가 정하고, 탭은 그 위에 'tab-hide'만 덧씌운다.
const adminTabs = document.getElementById("adminTabs");
const tabButtons = [...adminTabs.querySelectorAll(".admin-tab")];
const TAB_KEY = "classLeague.adminTab";
let tabsOn = false;

function panelsOf(tab) {
  return [...leagueView.querySelectorAll(`[data-panel="${tab}"]`)];
}
function tabHasContent(tab) {
  return panelsOf(tab).some((c) => !c.classList.contains("hidden"));
}
function selectAdminTab(tab, focus = false) {
  sessionStorage.setItem(TAB_KEY, tab);
  tabButtons.forEach((b) => {
    const on = b.dataset.tab === tab;
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1; // 탭 묶음 안에서는 방향키로 옮긴다
    if (on && focus) b.focus();
  });
  leagueView.querySelectorAll("[data-panel]").forEach((c) => {
    c.classList.toggle("tab-hide", tabsOn && c.dataset.panel !== tab);
  });
}
function applyAdminTabs(on, status) {
  tabsOn = on;
  adminTabs.classList.toggle("hidden", !on);
  leagueView.classList.toggle("tabs-on", on);
  if (!on) {
    leagueView.querySelectorAll(".tab-hide").forEach((c) => c.classList.remove("tab-hide"));
    return;
  }
  // 내용이 없는 탭은 숨긴다 (예: 끝난 리그는 출제 범위가 없다)
  tabButtons.forEach((b) => b.classList.toggle("hidden", !tabHasContent(b.dataset.tab)));
  const visible = tabButtons.filter((b) => !b.classList.contains("hidden")).map((b) => b.dataset.tab);
  const saved = sessionStorage.getItem(TAB_KEY);
  selectAdminTab(visible.includes(saved) ? saved : visible[0]);
}

tabButtons.forEach((b) => b.addEventListener("click", () => selectAdminTab(b.dataset.tab)));
adminTabs.addEventListener("keydown", (e) => {
  const visible = tabButtons.filter((b) => !b.classList.contains("hidden"));
  const i = visible.indexOf(document.activeElement);
  if (i < 0) return;
  let next = null;
  if (e.key === "ArrowRight") next = visible[(i + 1) % visible.length];
  else if (e.key === "ArrowLeft") next = visible[(i - 1 + visible.length) % visible.length];
  else if (e.key === "Home") next = visible[0];
  else if (e.key === "End") next = visible[visible.length - 1];
  if (!next) return;
  e.preventDefault();
  selectAdminTab(next.dataset.tab, true);
});

// ===== 확인 창 (confirm 대신) =====
// 사용법: if (!(await askConfirm({ title, text, ok, icon, danger }))) return;
const confirmModal = document.getElementById("confirmModal");
const confirmIcon = document.getElementById("confirmIcon");
const confirmTitle = document.getElementById("confirmTitle");
const confirmText = document.getElementById("confirmText");
const confirmOk = document.getElementById("confirmOk");
const confirmCancel = document.getElementById("confirmCancel");
const confirmAlt = document.getElementById("confirmAlt");

// alt를 주면 버튼이 3개가 된다: ok → true, alt → "alt", 취소 → false
function askConfirm({ title, text = "", ok = "확인", icon = "❓", danger = false, alt = "", cancel = "취소" }) {
  return new Promise((resolve) => {
    const lastFocus = document.activeElement;
    confirmIcon.textContent = icon;
    confirmTitle.textContent = title; // textContent라 태그가 실행되지 않음
    confirmText.textContent = text;
    confirmOk.textContent = ok;
    confirmCancel.textContent = cancel;
    confirmAlt.textContent = alt;
    confirmAlt.classList.toggle("hidden", !alt);
    confirmModal.querySelector(".modal-actions").classList.toggle("three", !!alt);
    confirmOk.classList.toggle("btn-danger", danger);
    confirmModal.classList.remove("hidden");
    confirmCancel.focus(); // 실수로 Enter를 눌러도 '취소'가 되게

    function close(result) {
      confirmModal.classList.add("hidden");
      confirmOk.removeEventListener("click", onOk);
      confirmCancel.removeEventListener("click", onCancel);
      confirmAlt.removeEventListener("click", onAlt);
      confirmModal.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKey);
      if (lastFocus) lastFocus.focus();
      resolve(result);
    }
    const onOk = () => close(true);
    const onCancel = () => close(false);
    const onAlt = () => close("alt");
    const onBackdrop = (e) => { if (e.target === confirmModal) close(false); };
    const onKey = (e) => { if (e.key === "Escape") close(false); };
    confirmOk.addEventListener("click", onOk);
    confirmCancel.addEventListener("click", onCancel);
    confirmAlt.addEventListener("click", onAlt);
    confirmModal.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKey);
  });
}

// ===== 순위표·최종 결과 (F11·F15) =====
function formatAverage(n) {
  return Number(n || 0).toFixed(2);
}
function formatGoalDiff(n) {
  const v = Number(n || 0);
  return v > 0 ? `+${v}` : String(v);
}
function renderStandings(data) {
  const finished = data.league.status === "finished";
  standingsTitle.textContent = finished ? "🏆 최종 순위" : "🏆 순위표";
  // 관리자: 순위표에서 학생 이름을 누르면 그 학생 화면(만든 문제·내보내기)
  const onName = data.is_admin ? (row) => openStudentQuestions(row.user_id) : null;
  fillStandingsTable(standingsHead, standingsBody, standingsRule, data, onName);
  const rewards = prizeTiers(data.league);
  rewardLegend.innerHTML = "";
  if (rewards.length) {
    rewardLegend.classList.remove("hidden");
    rewards.forEach((r) => {
      const chip = el("div", "legend-chip");
      const sw = el("span", "legend-swatch");
      sw.style.background = r.color;
      sw.setAttribute("aria-hidden", "true");
      chip.append(sw, el("span", "", `${rankRange(r)} · ${r.text}`));
      rewardLegend.append(chip);
    });
  } else {
    rewardLegend.classList.add("hidden");
  }
}

// 상품 구간마다 다른 색 (순위표 왼쪽 선과 아래 설명에 같은 색을 쓴다)
const PRIZE_COLORS = ["#2b6cd4", "#1e9e5a", "#e08a00", "#8e44ad", "#d23f62", "#0e9aa7"];
function prizeTiers(league) {
  return (league.rewards || [])
    .filter((r) => r.kind !== "penalty")
    .slice()
    .sort((a, b) => a.from - b.from)
    .map((r, i) => ({ ...r, color: PRIZE_COLORS[i % PRIZE_COLORS.length] }));
}
function rankRange(r) {
  return r.from === r.to ? `${r.from}등` : `${r.from}~${r.to}등`;
}

// 순위표 그리기 (지금 리그·지난 리그에서 같이 쓴다)
function fillStandingsTable(head, body, ruleEl, data, onName = null) {
  const short = data.league.league_mode === "short";
  const standingsHead = head, standingsBody = body;
  ruleEl.textContent = short
    ? "시험 대비 단기 리그 · 경기당 평균 승점 → 경기당 평균 득실차 → 정답률 순"
    : "전체 리그 · 총 승점 → 득실차 → 맞힌 문제 수 순";

  const headers = short
    ? ["순위", "닉네임", "경기", "승", "무", "패", "평균 득실", "정답률", "평균 승점"]
    : ["순위", "닉네임", "경기", "승", "무", "패", "득실", "맞힌 수", "승점"];
  const PTS_COL = headers.length - 1; // 승점은 맨 뒤 칸 (굵게)
  const hr = el("tr");
  headers.forEach((text, i) => {
    const th = el("th", i === PTS_COL ? "pts" : "", text);
    th.scope = "col";
    hr.append(th);
  });
  standingsHead.innerHTML = "";
  standingsHead.append(hr);
  standingsBody.innerHTML = "";

  const rewards = prizeTiers(data.league);
  for (const row of data.standings) {
    const tr = el("tr");
    if (row.user_id === data.my_user_id) tr.classList.add("me");
    const rw = rewards.find((r) => row.rank >= r.from && row.rank <= r.to);
    const values = short
      ? [row.rank, row.nickname, row.played, row.win, row.draw, row.lose,
          formatAverage(row.goal_diff_per_game), `${Math.round((row.accuracy || 0) * 100)}%`,
          formatAverage(row.points_per_game)]
      : [row.rank, row.nickname, row.played, row.win, row.draw, row.lose,
          formatGoalDiff(row.goal_diff), row.scored, row.points];
    values.forEach((value, i) => {
      const td = el("td", i === PTS_COL ? "pts" : "", i === 1 && onName ? "" : value);
      // 맨 왼쪽 등수 칸: 상품 받는 등수면 왼쪽 모서리에 그 상품 색 선 (아래 설명과 같은 색)
      if (i === 0 && rw) {
        td.classList.add("rank-reward");
        td.style.setProperty("--prize", rw.color);
        td.title = `상품: ${rw.text}`;
        td.append(el("span", "sr-only", ` (상품: ${rw.text})`));
      }
      if (i === 1 && onName) {
        // 키보드(Tab·Enter)로도 열 수 있게 이름 칸에 버튼을 둔다. 누르면 아래 행 클릭으로 이어진다
        const btn = el("button", "member-link", `${row.nickname} 📝`);
        btn.type = "button";
        btn.setAttribute("aria-label", `${row.nickname}이(가) 만든 문제 보기`);
        td.append(btn);
      }
      tr.append(td);
    });
    // 관리자: 행 어디를 눌러도 그 학생 화면
    if (onName) {
      tr.classList.add("row-link");
      tr.title = "이 학생이 만든 문제 보기";
      tr.addEventListener("click", () => onName(row));
    }
    standingsBody.append(tr);
  }
}

// 최종 결과의 상품 목록 (지금 리그·지난 리그에서 같이 쓴다)
function fillAwards(box, awards) {
  box.innerHTML = "";
  const colorOf = (a) => (prizeTiers({ rewards: awards }).find((t) => t.from === a.from && t.to === a.to) || {}).color;
  const prizes = awards.filter((a) => a.kind !== "penalty").slice().sort((x, y) => x.from - y.from);
  if (!prizes.length) {
    box.append(el("p", "hint", "설정된 상품은 없어요."));
    return;
  }
  prizes.forEach((a) => {
    const item = el("div", "final-award prize-tier");
    item.style.setProperty("--prize", colorOf(a) || PRIZE_COLORS[0]);
    const range = rankRange(a);
    item.append(el("strong", "", `상품 · ${range}`),
                el("span", "", a.text),
                el("small", "", a.recipients.length ? `대상: ${a.recipients.join(", ")}` : "해당 학생 없음"));
    box.append(item);
  });
}

function renderFinal(data) {
  finalCard.classList.remove("hidden");
  finalWinner.textContent = data.final.winner ? `우승 · ${data.final.winner} 🎉` : "최종 결과가 나왔어요";
  if (data.final.my_rank) {
    finalMyRank.textContent = `내 최종 순위는 ${data.final.my_rank}등이에요.`;
    finalMyRank.classList.remove("hidden");
  } else {
    finalMyRank.classList.add("hidden");
  }
  fillAwards(finalAwards, data.final.awards);
  // 신고 처리 중이면 아직 확정 아님
  const pend = document.getElementById("finalPending");
  if (!data.final.finalized) {
    pend.textContent = `🚩 신고 처리 중 (${data.final.pending_reports}개) · 판정이 끝나면 최종 확정돼요.` +
      (data.final.report_deadline ? ` ${fmtDeadline(data.final.report_deadline, true)}까지 판정하지 않으면 '문제없음'으로 확정돼요.` : "");
    pend.classList.remove("hidden");
    finalWinner.textContent = `(잠정) ${finalWinner.textContent}`;
  } else {
    pend.classList.add("hidden");
  }
}

// ===== 리그 생명주기 (F15): 보관·닫기·삭제·내보내기 =====
const lifecycleBox = document.getElementById("lifecycleBox");
const lifecycleText = document.getElementById("lifecycleText");
const lifecycleMsg = document.getElementById("lifecycleMsg");
const archiveBtn = document.getElementById("archiveBtn");
const closeLeagueBtn = document.getElementById("closeLeagueBtn");

function renderLifecycle(data) {
  lifecycleBox.classList.remove("hidden");
  lifecycleMsg.textContent = "";
  const ready = data.final.finalized;
  archiveBtn.classList.toggle("hidden", data.is_admin || !ready);
  closeLeagueBtn.classList.toggle("hidden", !data.is_admin || !ready);
  if (!ready) {
    lifecycleText.textContent = data.is_admin
      ? "처리하지 않은 신고를 판정하면 리그를 닫고 새 리그를 만들 수 있어요."
      : "신고 판정이 끝나 최종 결과가 확정되면 이 리그를 보관하고 새 리그에 들어갈 수 있어요.";
  } else {
    lifecycleText.textContent = data.is_admin
      ? "리그를 닫으면 새 리그를 만들 수 있어요. 이 리그의 순위와 기록은 [📚 지난 리그]에서 계속 볼 수 있어요."
      : "보관하면 새 리그 코드를 넣을 수 있어요. 이 리그의 순위·경기 기록·오답 노트는 그대로 남아요.";
  }
}

archiveBtn.addEventListener("click", async () => {
  const yes = await askConfirm({ icon: "📚", title: "이 리그를 지난 리그로 보관할까요?",
    text: "보관하면 리그 홈에서 사라지고 새 리그 코드를 넣을 수 있어요. 순위·경기 기록·오답 노트는 [📚 지난 리그]와 오답 노트에서 계속 볼 수 있어요.",
    ok: "보관하기" });
  if (!yes) return;
  const { ok, data } = await postJSON("/leagues/archive", {}, archiveBtn);
  if (!ok) {
    lifecycleMsg.className = "msg err";
    lifecycleMsg.textContent = data.error || "보관하지 못했어요.";
    return;
  }
  await loadMyLeague();
});

closeLeagueBtn.addEventListener("click", async () => {
  const yes = await askConfirm({ icon: "📚", title: "이 리그를 닫을까요?",
    text: "닫으면 새 리그를 만들 수 있어요. 학생들의 기록은 지워지지 않고, 학생들은 각자 [보관]을 눌러 새 리그에 들어가요.",
    ok: "닫기" });
  if (!yes) return;
  const { ok, data } = await postJSON("/leagues/close", {}, closeLeagueBtn);
  if (!ok) {
    lifecycleMsg.className = "msg err";
    lifecycleMsg.textContent = data.error || "닫지 못했어요.";
    return;
  }
  await loadMyLeague();
});

const deleteLeagueBtn = document.getElementById("deleteLeagueBtn");
deleteLeagueBtn.addEventListener("click", async () => {
  const n = (lastLeagueData && lastLeagueData.members.length) || 0;
  const yes = await askConfirm({ icon: "🗑️", title: "리그를 삭제할까요?", danger: true, ok: "삭제하기",
    text: (n ? `들어와 있는 학생 ${n}명도 리그에서 빠져요. ` : "") +
      "삭제하면 이 리그 코드로 더 들어올 수 없고, 되돌릴 수 없어요." });
  if (!yes) return;
  const msg = document.getElementById("deleteMsg");
  const { ok, data } = await postJSON("/leagues/delete", {}, deleteLeagueBtn);
  if (!ok) {
    msg.className = "msg err";
    msg.textContent = data.error || "삭제하지 못했어요.";
    return;
  }
  await loadMyLeague();
});

async function removeStudent(m, recruiting, btn) {
  const yes = await askConfirm(recruiting
    ? { icon: "🚪", title: `${m.nickname}을(를) 내보낼까요?`, danger: true, ok: "내보내기",
        text: "모집 중이라 참가 기록만 지워져요. 코드를 다시 넣으면 다시 들어올 수 있어요." }
    : { icon: "🚪", title: `${m.nickname}을(를) 내보낼까요?`, danger: true, ok: "내보내기",
        text: "전학 등으로 빠질 때 써요. 이 학생은 순위표에서 빠지고, 이 학생과 한 경기는 양쪽 모두 순위에 들어가지 않아요. 남은 경기의 상대는 쉬는 라운드가 돼요. 되돌릴 수 없어요." });
  if (!yes) return false;
  const { ok, data } = await postJSON(`/admin/students/${m.id}/remove`, {}, btn);
  if (!ok) {
    await askConfirm({ icon: "⚠️", title: "내보내지 못했어요", text: data.error || "", ok: "확인" });
    return false;
  }
  if (data.league_status === "finished") {
    await askConfirm({ icon: "🏁", title: "리그가 끝났어요", text: "활동 중인 학생이 1명만 남아 리그를 마쳤어요.", ok: "확인" });
  }
  await loadMyLeague();
  return true;
}

// ===== 지난 리그 (F15) =====
let pastCache = [];
async function loadPastLink() {
  try {
    const res = await fetch("/leagues/past");
    pastCache = res.ok ? (await res.json()).leagues || [] : [];
  } catch (err) {
    pastCache = [];
  }
  const n = pastCache.length;
  document.getElementById("pastLink").classList.toggle("hidden", n === 0);
  document.getElementById("pastLinkText").textContent = n ? `📚 지난 리그 ${n}개의 결과와 기록을 다시 볼 수 있어요.` : "";
  document.getElementById("pastFromLeagueBtn").classList.toggle("hidden", n === 0);
}

async function openPast() {
  await loadPastLink();
  const list = document.getElementById("pastList");
  list.innerHTML = "";
  if (!pastCache.length) list.append(el("div", "card empty-card", "아직 지난 리그가 없어요."));
  pastCache.forEach((p) => {
    const card = el("div", "card past-item");
    card.append(el("h3", "", p.name));
    const mode = p.league_mode === "short" ? "📝 시험 대비 단기 리그" : "🏟️ 전체 리그";
    card.append(el("p", "hint", `${mode} · 학생 ${p.players}명` + (p.first_date ? ` · ${fmtDate(p.first_date)} 시작` : "")));
    card.append(el("p", "", p.role === "admin"
      ? `📋 관리자로 운영했어요 · 우승 ${p.winner || "-"}`
      : `내 순위 ${p.my_rank ?? "-"}등 · 우승 ${p.winner || "-"}`));
    const btn = el("button", "btn btn-outline", "결과·기록 보기 →");
    btn.type = "button";
    btn.addEventListener("click", () => openPastDetail(p.league_id));
    card.append(btn);
    list.append(card);
  });
  showOnly(pastView);
}

async function openPastDetail(leagueId) {
  let data = null;
  try {
    const res = await fetch(`/leagues/past/${leagueId}`);
    data = res.ok ? await res.json() : null;
  } catch (err) {
    data = null;
  }
  if (!data) {
    await askConfirm({ icon: "⚠️", title: "지난 리그를 열지 못했어요", ok: "확인" });
    return;
  }
  document.getElementById("pastTitle").textContent = `📚 ${data.league.name}`;
  document.getElementById("pastWinner").textContent = data.final.winner ? `우승 · ${data.final.winner} 🎉` : "";
  document.getElementById("pastMyRank").textContent = data.final.my_rank ? `내 최종 순위는 ${data.final.my_rank}등이었어요.` : "";
  fillAwards(document.getElementById("pastAwards"), data.final.awards);
  fillStandingsTable(document.getElementById("pastHead"), document.getElementById("pastBody"),
    document.getElementById("pastRule"), { league: data.league, standings: data.standings, my_user_id: data.my_user_id });
  const hcard = document.getElementById("pastHistoryCard");
  hcard.classList.toggle("hidden", data.role !== "student");
  if (data.role === "student") {
    let rows = [];
    try {
      const res = await fetch(`/matches/history?league_id=${leagueId}`);
      rows = res.ok ? (await res.json()).history || [] : [];
    } catch (err) {
      rows = [];
    }
    renderHistoryList(document.getElementById("pastHistoryList"), document.getElementById("pastHistoryEmpty"),
      rows, () => openPastDetail(leagueId));
  }
  showOnly(pastDetailView);
}

const pastView = document.getElementById("pastView");
const pastDetailView = document.getElementById("pastDetailView");
document.getElementById("openPastBtn").addEventListener("click", openPast);
document.getElementById("pastFromLeagueBtn").addEventListener("click", openPast);
document.getElementById("pastDetailBack").addEventListener("click", openPast);

// ===== 리그 나가기 (학생, 모집 중일 때만) =====
leaveBtn.addEventListener("click", async () => {
  const yes = await askConfirm({
    icon: "🚪",
    title: "리그에서 나갈까요?",
    text: "모집 중이라 코드를 다시 넣으면 언제든 다시 들어올 수 있어요.",
    ok: "나가기",
    danger: true,
  });
  if (!yes) return;
  leaveMsg.textContent = "";
  const { ok, data } = await postJSON("/leagues/leave", {}, leaveBtn);
  if (ok) {
    await loadMyLeague();
  } else {
    leaveMsg.className = "msg err";
    leaveMsg.textContent = data.error || "나가지 못했어요.";
  }
});

// ===== 리그 코드 복사 (관리자) =====
const copyCodeBtn = document.getElementById("copyCodeBtn");
copyCodeBtn.addEventListener("click", async () => {
  const code = leagueCode.textContent;
  try {
    await navigator.clipboard.writeText(code);
  } catch (err) {
    // 복사 기능을 못 쓰는 브라우저용 예비 방법
    const ta = document.createElement("textarea");
    ta.value = code;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  copyCodeBtn.textContent = "✅ 복사했어요";
  setTimeout(() => (copyCodeBtn.textContent = "📋 코드 복사"), 1500);
});

// ===== 경기 일정 계산 (서버 app.py의 build_schedule과 같은 규칙) =====
// 날짜는 "YYYY-MM-DD"(한국 날짜) 글자로 다룬다. 요일은 월=0 … 일=6
const DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"];


function todayKST() {
  // 브라우저 시간대와 상관없이 한국 날짜
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
}
// 서버가 준 UTC 시각(ISO 글자)을 한국 날짜 "YYYY-MM-DD"로
function isoToKstDate(iso) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date(iso));
}
// 서버가 준 마감 시각(UTC)을 한국 시간 "10/21(수) 22:00"으로. 0시 정각은 전날 23:59로 보여 준다
function fmtDeadline(iso, long = false) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(iso));
  let ymd = isoToKstDate(iso);
  let hm = parts;
  if (hm === "00:00") {
    ymd = addDays(ymd, -1);
    hm = "23:59";
  }
  return `${long ? fmtDate(ymd) : fmtShort(ymd)} ${hm}`;
}
// ===== 마감·시작까지 남은 시간 =====
function remainingText(ms, label) {
  if (ms <= 0) return "⌛ 마감됐어요";
  const total = Math.floor(ms / 1000);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (days > 0) return `${label} ${days}일 ${hours}시간 ${mins}분`;
  if (hours > 0) return `${label} ${hours}시간 ${mins}분`;
  return `${label} ${mins}분 ${String(secs).padStart(2, "0")}초`;
}

function setCountdown(id, target, label = "마감까지") {
  const node = document.getElementById(id);
  if (!node) return;
  if (!target) {
    delete node.dataset.target;
    node.classList.add("hidden");
    node.textContent = "";
    return;
  }
  node.dataset.target = target;
  node.dataset.label = label;
  node.classList.remove("hidden");
  updateCountdownNode(node);
}
const countdownReloaded = new Set();
function updateCountdownNode(node) {
  const ms = Date.parse(node.dataset.target) - Date.now();
  node.textContent = remainingText(ms, node.dataset.label || "마감까지");
  node.classList.toggle("urgent", ms > 0 && ms <= 3 * 3600000);
  // 홈을 열어 둔 사이 시작·마감되면 서버에서 다음 상태를 다시 받아 온다.
  // 문제 작성/풀기 화면은 작성 중인 내용을 잃지 않도록 자동으로 나가지 않는다.
  const key = `${node.id}:${node.dataset.target}`;
  if (ms <= 0 && node.id === "matchCountdown" && !homeView.classList.contains("hidden") && !countdownReloaded.has(key)) {
    countdownReloaded.add(key);
    setTimeout(loadMyLeague, 500);
  }
}
function updateCountdowns() {
  document.querySelectorAll(".countdown[data-target]").forEach(updateCountdownNode);
}
setInterval(updateCountdowns, 1000);

function addDays(ymd, n) {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
function weekdayOf(ymd) {
  const [y, m, d] = ymd.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // 일요일=0 → 월요일=0으로
}
function daysBetween(a, b) {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}
function fmtDate(ymd) {
  const [, m, d] = ymd.split("-").map(Number);
  return `${m}월 ${d}일(${DAY_NAMES[weekdayOf(ymd)]})`;
}
function fmtShort(ymd) {
  const [, m, d] = ymd.split("-").map(Number);
  return `${m}/${d}(${DAY_NAMES[weekdayOf(ymd)]})`;
}
function roundCount(n) {
  if (n < 2) return 0;
  return n % 2 === 0 ? n - 1 : n;
}
// 경기 요일 검사: 맞으면 "" , 틀리면 안내 글
function matchDaysError(days) {
  if (days.length === 0) return "경기 요일을 하나 이상 골라 주세요.";
  if (days.length > 3) return "경기 요일은 1주일에 3번까지 고를 수 있어요.";
  if (days.length > 1) {
    const s = [...days].sort((a, b) => a - b);
    const gaps = s.slice(1).map((v, i) => v - s[i]).concat(s[0] + 7 - s[s.length - 1]);
    if (Math.min(...gaps) < 2) return "경기 요일끼리는 하루 이상 띄워 주세요 (예: 월·화는 안 돼요).";
  }
  return "";
}
function matchDatesFrom(first, days, count) {
  const out = [];
  let d = first;
  while (out.length < count) {
    if (days.includes(weekdayOf(d))) out.push(d);
    d = addDays(d, 1);
  }
  return out;
}
// 가장 짧은 라운드의 날 수 (요일 하나면 7일)
function shortestRoundDays(days) {
  const s = [...days].sort((a, b) => a - b);
  if (s.length === 1) return 7;
  return Math.min(...s.slice(1).map((v, i) => v - s[i]).concat(s[0] + 7 - s[s.length - 1]));
}
// 라운드별 날짜: start(시작일), makeLast(만들기 마지막 날), last(라운드 마지막 날)
// makeDays: 0이면 자동(라운드의 절반), 아니면 그 날 수
function buildSchedule(first, days, nRounds, makeDays = 0) {
  if (nRounds <= 0) return [];
  let starts = matchDatesFrom(first, days, nRounds + 1);
  // 첫날이 경기 요일이 아니면(오늘 바로 시작) 그날이 1라운드 시작 (서버와 같은 규칙)
  if (!days.includes(weekdayOf(first))) starts = [first, ...starts.slice(0, nRounds)];
  const rounds = [];
  for (let i = 0; i < nRounds; i++) {
    const len = daysBetween(starts[i], starts[i + 1]);
    let make = makeDays > 0 ? makeDays : Math.max(1, Math.floor(len / 2));
    make = Math.min(make, len - 1); // 풀기 기간이 하루는 남게
    rounds.push({
      round: i + 1,
      start: starts[i],
      makeLast: addDays(starts[i], make - 1),
      solveFirst: addDays(starts[i], make),
      last: addDays(starts[i + 1], -1),
    });
  }
  return rounds;
}
function rangeText(a, b) {
  return a === b ? fmtShort(a) : `${fmtShort(a)}~${fmtShort(b)}`;
}
// 미리 보기 글과 라운드 목록 그리기
// 작은 요소 만들기 도우미 (글자는 항상 textContent로)
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// 미리 보기 그리기
// summaryEl: ① 요약(몇 라운드, 언제 시작·끝) ② 한 라운드 진행 방식(요일·시각)
// tbodyEl: 라운드별 표 (만들기 기간·마감, 풀기 기간·마감)
// 마감 시각 글자 ("23:59", "22:00" …)를 받아 "수 22:00"처럼 쓴다
// compact: 리그 시작 화면처럼 요약만 크게 보이고 '한 라운드 진행 방식'은 접어 둘 때
// endDate(YYYY-MM-DD)를 주면 시험 대비 단기 리그: 그날 마감까지 끝나는 라운드만 (서버 rounds_until과 같은 규칙)
function shortRoundCount(first, days, makeDays, endDate, nMax) {
  if (!endDate || first > endDate) return 0;
  return buildSchedule(first, days, nMax, makeDays).filter((r) => r.last <= endDate).length;
}

function renderPreview(summaryEl, tbodyEl, first, days, nPlayers, makeDays = 0, dl = "23:59", compact = false, endDate = "") {
  summaryEl.innerHTML = "";
  tbodyEl.innerHTML = "";
  const nFull = roundCount(nPlayers);
  if (nFull === 0) {
    summaryEl.append(el("p", "preview-empty", "학생이 2명 이상이어야 일정이 생겨요."));
    return;
  }
  let n = nFull;
  if (endDate) {
    n = shortRoundCount(first, days, makeDays, endDate, nFull);
    if (n === 0) {
      summaryEl.append(el("p", "preview-empty",
        `⚠️ ${fmtDate(endDate)}까지 끝낼 수 있는 라운드가 없어요. 종료 희망일을 늦추거나 경기 요일을 늘려 주세요.`));
      return;
    }
  }
  const rounds = buildSchedule(first, days, n, makeDays);
  const end = rounds[rounds.length - 1].last;
  const weeks = Math.ceil((daysBetween(first, end) + 1) / 7);

  // ① 요약
  const big = el("div", "preview-big");
  big.append(el("strong", "", `총 ${n}라운드`), el("span", "", ` · 약 ${weeks}주`));
  const period = el("div", "preview-period");
  period.append(
    el("span", "", `🏁 ${fmtDate(first)} 00:00 시작`),
    el("span", "arrow", "→"),
    el("span", "", `🏆 ${fmtDate(end)} ${dl} 끝`)
  );
  summaryEl.append(big, period);
  if (endDate) {
    summaryEl.append(el("p", "hint",
      `📝 시험 대비 단기 리그: ${fmtDate(endDate)}까지 ${n}라운드 (모두와 다 붙으려면 ${nFull}라운드). 학생마다 서로 다른 상대와 경기해요.`));
    if (n < 2 && nPlayers > 2) {
      summaryEl.append(el("p", "msg err", "⚠️ 라운드가 너무 적어요. 종료 희망일을 늦추거나 경기 요일을 늘리면 더 많이 경기할 수 있어요."));
    }
    if (nPlayers % 2 === 1 && n < nFull) {
      summaryEl.append(el("p", "hint", `학생이 ${nPlayers}명(홀수)이라 쉬는 횟수가 학생마다 다를 수 있어서, 순위는 경기당 평균 승점으로 정해요.`));
    }
  } else if (rounds.length >= 6) {
    // 전체 리그는 길어질 수 있어서 시험 전에 끝내야 하면 단기 리그를 알려 준다
    summaryEl.append(el("p", "hint", "💡 시험 전까지 끝내야 하면 ② 리그 기간에서 '시험 대비 단기 리그'를 골라 보세요."))
  }
  if (nPlayers % 2 === 1 && !endDate) {
    summaryEl.append(el("p", "hint", `학생이 ${nPlayers}명(홀수)이라 라운드마다 한 명씩 돌아가며 쉬어요.`));
  }

  // ② 한 라운드는 이렇게 (경기 요일마다 같은 모양이 매주 반복)
  let howParent = summaryEl;
  if (compact) {
    howParent = el("details", "preview-details");
    howParent.append(el("summary", "", "한 라운드 진행 방식 보기"));
    summaryEl.append(howParent);
  } else {
    summaryEl.append(el("p", "preview-sub", "한 라운드는 이렇게 진행돼요 (매주 반복)"));
  }
  const howWrap = el("div", "table-wrap");
  const how = el("table", "round-table how-table");
  const hh = el("thead");
  const hr = el("tr");
  ["라운드 시작", "✏️ 문제 만들기 마감", "🎯 문제 풀기 마감"].forEach((t) => {
    const th = el("th", "", t);
    th.scope = "col";
    hr.append(th);
  });
  hh.append(hr);
  const hb = el("tbody");
  // 첫 주에 나오는 경기 요일마다 한 줄 (요일 순서대로)
  const seen = new Set();
  for (const r of rounds) {
    const wd = weekdayOf(r.start);
    if (seen.has(wd)) break;
    seen.add(wd);
    const tr = el("tr");
    tr.append(
      el("td", "", `${DAY_NAMES[wd]} 00:00`),
      el("td", "", `${DAY_NAMES[weekdayOf(r.makeLast)]} ${dl}`),
      el("td", "", `${DAY_NAMES[weekdayOf(r.last)]} ${dl}`)
    );
    hb.append(tr);
  }
  how.append(hh, hb);
  howWrap.append(how);
  howParent.append(howWrap);
  howParent.append(el("p", "hint",
    "만들기 마감 전까지 상대에게 낼 문제를 만들고(몇 번이든 고칠 수 있어요), 만들기 마감 바로 뒤부터 풀기 마감까지 상대 문제를 풀어요. [완성]을 눌러도 만들기 마감 전까지는 [다시 고치기]로 고칠 수 있어요."));

  // ③ 라운드별 표
  for (const r of rounds) {
    const tr = el("tr");
    const th = el("th", "", `${r.round}R`);
    th.scope = "row";
    const make = el("td");
    make.append(el("span", "range", rangeText(r.start, r.makeLast)), el("span", "deadline", `마감 ${fmtShort(r.makeLast)} ${dl}`));
    const solve = el("td");
    solve.append(el("span", "range", rangeText(r.solveFirst, r.last)), el("span", "deadline", `마감 ${fmtShort(r.last)} ${dl}`));
    tr.append(th, make, solve);
    tbodyEl.append(tr);
  }
}

// ===== 리그 만들기: 경기 요일 고르기 + 미리 보기 =====
const dayButtons = document.getElementById("dayButtons");
const dayMsg = document.getElementById("dayMsg");
const previewCount = document.getElementById("previewCount");
const createPreview = document.getElementById("createPreview");
const createPreviewList = document.getElementById("createPreviewList");
const selectedDays = new Set([0, 3]); // 기본값: 월·목

DAY_NAMES.forEach((name, i) => {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "day-btn";
  b.textContent = name;
  b.setAttribute("aria-pressed", selectedDays.has(i) ? "true" : "false");
  b.addEventListener("click", () => {
    if (selectedDays.has(i)) selectedDays.delete(i);
    else selectedDays.add(i);
    b.setAttribute("aria-pressed", selectedDays.has(i) ? "true" : "false");
    updateCreatePreview();
  });
  dayButtons.appendChild(b);
});

const deadlineTime = document.getElementById("deadlineTime");
const makeDaysSel = document.getElementById("makeDays");

// 문제 만들기 기간 고르기: 자동 + 1일 ~ (가장 짧은 라운드 - 1)일
function fillMakeDays(days) {
  const prev = makeDaysSel.value || "0";
  const max = days.length && !matchDaysError(days) ? shortestRoundDays(days) - 1 : 1;
  makeDaysSel.innerHTML = "";
  const auto = el("option", "", "자동 (라운드의 절반)");
  auto.value = "0";
  makeDaysSel.append(auto);
  for (let i = 1; i <= max; i++) {
    const o = el("option", "", `${i}일 (나머지는 풀기)`);
    o.value = String(i);
    makeDaysSel.append(o);
  }
  makeDaysSel.value = [...makeDaysSel.options].some((o) => o.value === prev) ? prev : "0";
}

function settingText(days, dl, makeDays) {
  const dayText = [...days].sort((a, b) => a - b).map((d) => DAY_NAMES[d]).join("·") || "요일 없음";
  return `📌 ${dayText} 경기 · 마감 ${dl} · 문제 만들기 ${makeDays ? makeDays + "일" : "자동(라운드의 절반)"}`;
}

function updateCreatePreview() {
  const days = [...selectedDays];
  const err = matchDaysError(days);
  dayMsg.textContent = err;
  fillMakeDays(days);
  document.getElementById("settingSummary").textContent =
    settingText(days, deadlineTime.value, parseInt(makeDaysSel.value, 10) || 0) +
    (getLeagueMode() === "short" && endDate.value ? ` · ${fmtShort(endDate.value)}까지 단기 리그` : "");
  if (err) {
    createPreview.innerHTML = "";
    createPreview.append(el("p", "preview-empty", "경기 요일을 바르게 고르면 일정이 보여요."));
    createPreviewList.innerHTML = "";
    return;
  }
  let n = parseInt(previewCount.value, 10);
  if (!(n >= 2)) n = 2;
  if (n > 30) n = 30;
  // 미리 보기: 내일 이후 가장 가까운 경기 요일부터 시작한다고 보고 계산
  // (실제 첫 경기 날짜는 [리그 시작] 때 오늘 또는 경기 요일 중에서 고른다)
  const first = matchDatesFrom(addDays(todayKST(), 1), days, 1)[0];
  renderPreview(createPreview, createPreviewList, first, days, n,
    parseInt(makeDaysSel.value, 10) || 0, deadlineTime.value, false,
    getLeagueMode() === "short" ? endDate.value : "");
}

// ===== 리그 기간 방식 (전체 / 시험 대비 단기) =====
const endDate = document.getElementById("endDate");
const endDateWrap = document.getElementById("endDateWrap");
function getLeagueMode() {
  const checked = document.querySelector('input[name="leagueMode"]:checked');
  return checked ? checked.value : "full";
}
function setLeagueMode(mode, end) {
  document.querySelectorAll('input[name="leagueMode"]').forEach((r) => (r.checked = r.value === mode));
  if (end !== undefined) endDate.value = end;
  syncLeagueMode();
}
function syncLeagueMode() {
  const short = getLeagueMode() === "short";
  endDateWrap.classList.toggle("hidden", !short);
  endDate.min = addDays(todayKST(), 1);
  if (short && !endDate.value) endDate.value = addDays(todayKST(), 21); // 기본: 3주 뒤
  showEndDateText();
  updateCreatePreview();
}
// 고른 날짜를 읽기 쉽게: "11월 14일(토) · 오늘부터 21일 뒤 (3주)"
function showEndDateText() {
  const box = document.getElementById("endDateText");
  const v = endDate.value;
  if (!v) {
    box.textContent = "📅 칸을 눌러 달력에서 날짜를 골라 주세요";
    box.className = "date-text";
    return;
  }
  const d = daysBetween(todayKST(), v);
  const weeks = d % 7 === 0 ? ` (${d / 7}주)` : "";
  const bad = v < endDate.min;
  box.textContent = bad ? "⚠️ 내일 이후 날짜로 골라 주세요" : `${fmtDate(v)} · 오늘부터 ${d}일 뒤${weeks}`;
  box.className = bad ? "date-text bad" : "date-text";
  document.querySelectorAll(".date-quick [data-weeks]").forEach((b) => {
    b.setAttribute("aria-pressed", v === addDays(todayKST(), b.dataset.weeks * 7) ? "true" : "false");
  });
}
// 칸 어디를 눌러도 달력 열기 (지원하지 않는 브라우저는 원래대로 동작)
function openEndDatePicker() {
  try {
    if (typeof endDate.showPicker === "function") endDate.showPicker();
  } catch (err) {
    /* 이미 열려 있거나 지원하지 않으면 무시 */
  }
}
document.querySelector(".date-field").addEventListener("click", openEndDatePicker);
endDate.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openEndDatePicker();
  }
});
document.querySelectorAll(".date-quick [data-weeks]").forEach((b) => b.addEventListener("click", () => {
  endDate.value = addDays(todayKST(), b.dataset.weeks * 7);
  showEndDateText();
  updateCreatePreview();
}));
document.querySelectorAll('input[name="leagueMode"]').forEach((r) => r.addEventListener("change", syncLeagueMode));
endDate.addEventListener("change", () => {
  showEndDateText();
  updateCreatePreview();
});
deadlineTime.addEventListener("change", updateCreatePreview);
makeDaysSel.addEventListener("change", updateCreatePreview);
previewCount.addEventListener("input", updateCreatePreview);
updateCreatePreview();

// ===== 관리자 화면 (F16·F16-1·F16-2) =====
const studentQView = document.getElementById("studentQView");
// ✅ 함 · ⏳ 아직 · ❌ 마감까지 못 함 · ➖ 해당 없음 (만들기에서 몰수돼 풀기가 열리지 않음)
function mark(done, finished, notApplicable = false) {
  if (done) return "✅";
  if (!finished) return "⏳";
  return notApplicable ? "➖" : "❌";
}

async function loadAdminProgress(status) {
  const body = document.getElementById("progressBody");
  const summary = document.getElementById("progressSummary");
  let data = null;
  try {
    const res = await fetch("/admin/progress");
    data = res.ok ? await res.json() : null;
  } catch (err) {
    data = null;
  }
  body.innerHTML = "";
  if (!data) {
    summary.textContent = "진행 상황을 불러오지 못했어요.";
    return;
  }
  document.getElementById("progressTitle").textContent =
    status === "finished" ? `📋 마지막 ${data.round}라운드 결과` : `📋 ${data.round}라운드 진행 상황`;
  const left = [];
  if (data.todo.make) left.push(`아직 [완성] 안 한 학생 ${data.todo.make}명`);
  if (data.todo.solve) left.push(`아직 제출 안 한 학생 ${data.todo.solve}명`);
  const forfeits = data.matches.filter((m) => m.forfeit).length;
  const allDone = forfeits ? `모두 끝났어요 · 마감을 어겨 몰수된 경기 ${forfeits}개` : "모두 끝났어요 🎉";
  summary.textContent = `${data.round} / ${data.total_rounds}라운드 · ` + (left.length ? left.join(" · ") : allDone);
  // 남은 시간: 만들기 마감 전이면 만들기, 아니면 풀기 마감
  const now = Date.now();
  if (status !== "finished" && data.make_deadline && Date.parse(data.make_deadline) > now) {
    setCountdown("progressCountdown", data.make_deadline, "만들기 마감까지");
  } else if (status !== "finished" && data.solve_deadline && Date.parse(data.solve_deadline) > now) {
    setCountdown("progressCountdown", data.solve_deadline, "풀기 마감까지");
  } else {
    setCountdown("progressCountdown", null);
  }
  data.matches.forEach((m) => {
    const tr = el("tr", m.finished ? "done-row" : "");
    // 둘 중 한 명이라도 [완성]을 못 했으면 풀기 단계가 열리지 않았으므로 제출 칸은 해당 없음
    const noSolve = m.finished && !(m.p1.made && m.p2.made);
    tr.append(
      el("th", "", m.p1.nickname), el("td", "", mark(m.p1.made, m.finished)),
      el("td", "", mark(m.p1.submitted, m.finished, noSolve)),
      el("th", "", m.p2.nickname), el("td", "", mark(m.p2.made, m.finished)),
      el("td", "", mark(m.p2.submitted, m.finished, noSolve))
    );
    tr.children[0].scope = "row";
    if (m.forfeit) tr.title = "마감을 어겨 몰수로 끝난 경기";
    body.append(tr);
  });
  document.getElementById("progressByes").textContent =
    data.byes.length ? `😴 이번 라운드 쉬는 학생: ${data.byes.join(", ")}` : "";
}

function pct(rate) {
  return rate === null || rate === undefined ? "기록 없음" : `${Math.round(rate * 100)}%`;
}

async function loadAdminAccuracy() {
  const bars = document.getElementById("accuracyLeague");
  let data = null;
  try {
    const res = await fetch("/admin/accuracy");
    data = res.ok ? await res.json() : null;
  } catch (err) {
    data = null;
  }
  bars.innerHTML = "";
  if (!data) {
    bars.append(el("p", "hint", "정답률을 불러오지 못했어요."));
    return;
  }
  if (data.league.every((x) => !x.total)) {
    bars.append(el("p", "hint", "아직 끝난 경기가 없어요. 경기가 끝나면 과목별 정답률이 보여요."));
  }
  data.league.forEach((x) => {
    if (!x.total) return;
    const row = el("div", "acc-row");
    const bar = el("div", "acc-bar");
    const fill = el("span", "acc-fill");
    fill.style.width = `${Math.round((x.rate || 0) * 100)}%`;
    bar.append(fill);
    row.append(el("strong", "", x.subject), bar, el("span", "acc-num", `${pct(x.rate)} (${x.correct}/${x.total})`));
    bars.append(row);
  });
  const head = document.getElementById("accuracyHead");
  const body = document.getElementById("accuracyBody");
  head.innerHTML = "";
  body.innerHTML = "";
  const hr = el("tr");
  ["학생", ...data.subjects].forEach((t) => {
    const th = el("th", "", t);
    th.scope = "col";
    hr.append(th);
  });
  head.append(hr);
  data.students.forEach((s) => {
    const tr = el("tr");
    const th = el("th", "", s.nickname);
    th.scope = "row";
    tr.append(th);
    s.subjects.forEach((x) => {
      const td = el("td", x.rate !== null && x.rate < 0.5 ? "low-rate" : "", pct(x.rate));
      if (x.total) td.title = `${x.correct}/${x.total}`;
      tr.append(td);
    });
    body.append(tr);
  });
}

let studentQTarget = null;
document.getElementById("studentRemoveBtn").addEventListener("click", async (e) => {
  if (!studentQTarget) return;
  const removed = await removeStudent({ id: studentQTarget.user_id, nickname: studentQTarget.nickname }, false, e.currentTarget);
  if (removed) goHome();
});
async function openStudentQuestions(userId) {
  let data = null, msg = "";
  try {
    const res = await fetch(`/admin/students/${userId}/questions`);
    data = await res.json();
    if (!res.ok) {
      msg = data.error;
      data = null;
    }
  } catch (err) {
    msg = "서버에 연결하지 못했어요.";
  }
  if (!data) {
    await askConfirm({ icon: "⚠️", title: "학생 문제를 열 수 없어요", text: msg || "", ok: "확인" });
    return;
  }
  document.getElementById("studentQTitle").textContent = `📝 ${data.student.nickname}이(가) 만든 문제`;
  const list = document.getElementById("studentQList");
  list.innerHTML = "";
  let shown = 0, correct = 0, answered = 0;
  data.rounds.forEach((r) => {
    const card = el("div", "card student-round");
    if (r.bye) {
      card.append(el("h3", "", `${r.round}라운드 · 😴 쉬는 라운드`));
      list.append(card);
      return;
    }
    card.append(el("h3", "", `${r.round}라운드 · vs ${r.opponent}`));
    if (r.locked) {
      card.append(el("p", "locked-note", "🔒 경기가 끝나면 볼 수 있어요"));
    } else if (r.note) {
      card.append(el("p", "hint", r.note));
    } else {
      if (r.scopes) renderScopeList(card.appendChild(el("ul", "scope-list")), r.scopes, r.round);
      r.questions.forEach((q, i) => {
        shown++;
        if (q.opponent_correct !== null) {
          answered++;
          if (q.opponent_correct) correct++;
        }
        card.append(buildAdminQuestion(q, i));
      });
    }
    list.append(card);
  });
  // 진행 중인 리그에서만 내보내기 (끝난 리그에서는 서버도 막는다)
  const canRemove = !!(lastLeagueData && lastLeagueData.league.status === "running");
  document.getElementById("studentRemoveBox").classList.toggle("hidden", !canRemove);
  studentQTarget = data.student;
  document.getElementById("studentQSummary").textContent = shown
    ? `볼 수 있는 문제 ${shown}개 · 상대가 맞힌 문제 ${correct}/${answered}개`
    : "아직 볼 수 있는 문제가 없어요. 경기가 끝나면 여기에 보여요.";
  showOnly(studentQView);
}

// 관리자용 문제 카드: 정답·해설·상대가 맞혔는지 (상대가 쓴 답은 없음)
function buildAdminQuestion(q, i) {
  const box = el("div", "admin-q");
  box.append(el("div", "q-title", `${i + 1}. [${q.subject}] ${q.qtype === "mc" ? "객관식" : "주관식"}`));
  box.append(el("p", "result-q", q.content));
  if (q.qtype === "mc") {
    const ul = el("ul", "answer-choices");
    const ans = parseInt(q.correct_answer, 10);
    q.choices.forEach((c, ci) => {
      const li = el("li", ci === ans ? "is-answer" : "", `${ci + 1}. ${c}${ci === ans ? "  ← 정답" : ""}`);
      ul.append(li);
    });
    box.append(ul);
  } else {
    box.append(el("p", "result-line", `정답: ${q.correct_answer}`));
  }
  box.append(el("p", "result-expl", q.explanation ? `해설: ${q.explanation}` : "해설: (없음)"));
  if (q.opponent_correct !== undefined) {
    box.append(el("p", "opp-result",
      q.opponent_correct === null ? "상대 결과: 제출하지 않음" : q.opponent_correct ? "상대 결과: ⭕ 맞힘" : "상대 결과: ❌ 틀림"));
  }
  if (q.void) box.append(el("p", "void-badge", `🚩 무효 · ${q.void_reason || ""}`));
  return box;
}
// ===== 출제 범위 (F4-2) =====
// 학생 화면에 "📖 수학: 이차함수" 목록 그리기
function renderScopeList(ul, scopes, round) {
  ul.innerHTML = "";
  if (!Array.isArray(scopes) || scopes.length === 0) {
    ul.classList.add("hidden");
    return;
  }
  ul.append(el("li", "scope-title", `📖 ${round}라운드 출제 범위`));
  scopes.forEach((s) => {
    const li = el("li");
    li.append(el("strong", "", `${s.subject}`), ` ${s.scope}`);
    ul.append(li);
  });
  ul.classList.remove("hidden");
}

// 관리자: 라운드별 범위 카드
const scopeCard = document.getElementById("scopeCard");
const scopeRound = document.getElementById("scopeRound");
const scopeFields = document.getElementById("scopeFields");
const scopeSaveBtn = document.getElementById("scopeSaveBtn");
const scopeMsg = document.getElementById("scopeMsg");
let scopeData = null;

async function loadScopes() {
  let data = null;
  try {
    const res = await fetch("/leagues/scopes");
    data = res.ok ? await res.json() : null;
  } catch (err) {
    data = null;
  }
  if (!data) {
    scopeCard.classList.add("hidden");
    return;
  }
  scopeData = data;
  // 지금 라운드 범위 (잠김)
  const cur = data.rounds.find((r) => r.round === data.current) || data.rounds[0];
  const now = document.getElementById("scopeNow");
  now.innerHTML = "";
  if (cur) {
    now.append(el("p", "scope-now-title", `🔒 지금 ${cur.round}라운드 범위 (진행 중이라 바꿀 수 없어요)`));
    const ul = el("ul", "scope-list");
    cur.scopes.forEach((s) => {
      const li = el("li");
      li.append(el("strong", "", s.subject), ` ${s.scope}`);
      ul.append(li);
    });
    now.append(ul);
  }
  // 범위를 정할 수 있는 라운드 (아직 시작 안 한 것)
  const prev = scopeRound.value;
  scopeRound.innerHTML = "";
  const open = data.rounds.filter((r) => !r.locked);
  open.forEach((r) => {
    const o = el("option", "", `${r.round}라운드 · ${fmtStart(r.start)} 시작`);
    o.value = String(r.round);
    scopeRound.append(o);
  });
  if (open.length === 0) {
    scopeRound.append(Object.assign(el("option", "", "남은 라운드가 없어요"), { value: "" }));
  }
  if ([...scopeRound.options].some((o) => o.value === prev)) scopeRound.value = prev;
  scopeRound.disabled = open.length === 0;
  scopeSaveBtn.disabled = open.length === 0;
  renderScopeFields();
  renderScopeTable();
}

function renderScopeFields() {
  scopeFields.innerHTML = "";
  const r = scopeData && scopeData.rounds.find((x) => String(x.round) === scopeRound.value);
  if (!r) return;
  r.scopes.forEach((s) => {
    const lab = el("label", "subject-label", `${s.subject} `);
    lab.append(el("small", "", `(기본 범위: ${s.default})`));
    const input = el("input", "scope-input");
    input.type = "text";
    input.maxLength = 100;
    input.dataset.subject = s.subject;
    input.placeholder = `비워 두면 기본 범위 "${s.default}"`;
    input.value = s.custom ? s.scope : "";
    lab.append(input);
    scopeFields.append(lab);
  });
}

function renderScopeTable() {
  const head = document.getElementById("scopeTableHead");
  const body = document.getElementById("scopeTableBody");
  head.innerHTML = "";
  body.innerHTML = "";
  if (!scopeData || !scopeData.rounds.length) return;
  const tr = el("tr");
  ["라운드", ...scopeData.rounds[0].scopes.map((s) => s.subject)].forEach((t) => {
    const th = el("th", "", t);
    th.scope = "col";
    tr.append(th);
  });
  head.append(tr);
  scopeData.rounds.forEach((r) => {
    const row = el("tr");
    const th = el("th", "", `${r.locked ? "🔒 " : ""}${r.round}R`);
    th.scope = "row";
    row.append(th);
    r.scopes.forEach((s) => row.append(el("td", s.custom ? "" : "scope-default", s.scope)));
    body.append(row);
  });
}

scopeRound.addEventListener("change", () => {
  scopeMsg.textContent = "";
  renderScopeFields();
});
scopeSaveBtn.addEventListener("click", async () => {
  scopeMsg.textContent = "";
  const scopes = {};
  scopeFields.querySelectorAll(".scope-input").forEach((i) => (scopes[i.dataset.subject] = i.value));
  const round = parseInt(scopeRound.value, 10);
  const { ok, data } = await postJSON("/leagues/scopes", { round, scopes }, scopeSaveBtn);
  scopeMsg.className = ok ? "msg ok" : "msg err";
  scopeMsg.textContent = ok ? `✅ ${round}라운드 출제 범위를 저장했어요. 라운드가 시작되면 학생들에게 보여요.` : (data.error || "저장하지 못했어요.");
  if (ok) await loadScopes();
});

// ===== 관리자 + 모집 중: 리그 시작까지 할 일 =====
function renderAdminTodo(data) {
  const box = document.getElementById("adminTodo");
  const list = document.getElementById("adminTodoList");
  box.classList.toggle("hidden", !data);
  if (!data) {
    setTodoOpen(false);
    return;
  }
  const n = data.members.length;
  const steps = [
    [true, "리그 만들기", "설정은 시작 전까지 [⚙️ 리그 설정 고치기]로 바꿀 수 있어요"],
    [n >= 2, `학생 들어오기 (지금 ${n}명)`, n >= 2 ? "2명 이상이라 시작할 수 있어요" : "2명 이상 들어와야 시작할 수 있어요"],
    [false, "첫 경기 날짜 고르고 [이 일정으로 시작]", "맨 아래 '🚀 리그 시작'에서 해요"],
  ];
  document.getElementById("todoCount").textContent = `${steps.filter((x) => x[0]).length}/${steps.length}`;
  list.innerHTML = "";
  steps.forEach(([done, title, help]) => {
    const li = el("li", done ? "done" : "");
    li.append(el("span", "todo-mark", done ? "✅" : "⬜"), el("strong", "", title), el("span", "todo-help", help));
    list.append(li);
  });
}

// 할 일 서랍 열고 닫기
const todoToggle = document.getElementById("todoToggle");
const todoDrawer = document.getElementById("todoDrawer");
function setTodoOpen(open) {
  todoDrawer.classList.toggle("open", open);
  todoToggle.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) document.getElementById("todoClose").focus();
}
todoToggle.addEventListener("click", () => setTodoOpen(!todoDrawer.classList.contains("open")));
document.getElementById("todoClose").addEventListener("click", () => {
  setTodoOpen(false);
  todoToggle.focus();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && todoDrawer.classList.contains("open")) setTodoOpen(false);
});

// ===== 리그 시작 (관리자): 첫 경기 날짜 고르기 + 미리 보기 =====
const startPanel = document.getElementById("startPanel");
const firstDate = document.getElementById("firstDate");
const startPreview = document.getElementById("startPreview");
const startPreviewList = document.getElementById("startPreviewList");
const startDaysText = document.getElementById("startDaysText");
let startInfo = { days: [], players: 0 };

function setupStartPanel(data) {
  const days = data.league.match_days || [];
  const makeDays = data.league.make_days || 0;
  const dl = data.league.deadline_time || "23:59";
  const end = data.league.league_mode === "short" ? data.league.end_date : "";
  startInfo = { days, players: data.members.length, makeDays, dl, end };
  startDaysText.textContent = `${settingText(days, dl, makeDays)} · 학생 ${data.members.length}명` +
    (end ? ` · 📝 ${fmtShort(end)}까지 단기 리그` : " · 🏟️ 전체 리그");
  const prev = firstDate.value;
  firstDate.innerHTML = "";
  for (const d of data.first_date_choices || []) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d === data.today ? `오늘 ${fmtDate(d)} · 바로 시작` : fmtDate(d);
    firstDate.appendChild(opt);
  }
  if ([...firstDate.options].some((o) => o.value === prev)) firstDate.value = prev;
  updateStartPreview();
}
function updateStartPreview() {
  if (!firstDate.value) {
    startPreview.innerHTML = "";
    startPreview.append(el("p", "preview-empty", "고를 수 있는 날짜가 없어요."));
    startPreviewList.innerHTML = "";
    return;
  }
  renderPreview(startPreview, startPreviewList, firstDate.value, startInfo.days, startInfo.players,
    startInfo.makeDays, startInfo.dl, true, startInfo.end);
}
firstDate.addEventListener("change", updateStartPreview);

startBtn.addEventListener("click", async () => {
  startMsg.textContent = "";
  if (startInfo.players < 2) {
    startMsg.className = "msg err";
    startMsg.textContent = "학생이 2명 이상 있어야 시작할 수 있어요.";
    return;
  }
  const yes = await askConfirm({
    icon: "🚀",
    title: "이 일정으로 리그를 시작할까요?",
    text: `${startPreview.querySelector(".preview-big").textContent}, ` +
      `${startPreview.querySelector(".preview-period").textContent.replace("→", " → ")}. ` +
      "시작하면 학생이 새로 들어오거나 나갈 수 없어요.",
    ok: "시작하기",
  });
  if (!yes) return;
  const { ok, data } = await postJSON("/leagues/start", { first_date: firstDate.value }, startBtn);
  if (ok) {
    await loadMyLeague();
  } else {
    startMsg.className = "msg err";
    startMsg.textContent = data.error || "리그를 시작하지 못했어요.";
  }
});

// ===== 리그 만들기 =====
createForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  createMsg.textContent = "";
  const name = document.getElementById("leagueName").value;

  // 문제 수가 틀린 칸이 있으면 그 칸으로 데려가서 고치게 한다
  const badCount = [...document.querySelectorAll("#subjectRows .subject-row")]
    .filter((row) => row.querySelector(".subject-name").value.trim())
    .map((row) => row.querySelector(".subject-count"))
    .find((input) => !checkCountInput(input));
  if (badCount) {
    badCount.scrollIntoView({ block: "center", behavior: "smooth" });
    badCount.focus({ preventScroll: true });
    createMsg.className = "msg err";
    createMsg.textContent = "위의 과목 칸에서 문제 수를 고쳐 주세요 (1~10개).";
    return;
  }

  // 과목 모으기
  const subjects = [];
  document.querySelectorAll("#subjectRows .subject-row").forEach((row) => {
    const sname = row.querySelector(".subject-name").value.trim();
    const count = parseInt(row.querySelector(".subject-count").value);
    // 범위를 비워 두면 '자유 출제'
    const scope = row.querySelector(".subject-scope").value.trim() || "자유 출제";
    if (sname) subjects.push({ name: sname, count: count, scope });
  });
  if (subjects.length === 0) {
    createMsg.className = "msg err";
    createMsg.textContent = "과목을 하나 이상 넣어 주세요.";
    return;
  }

  // 상품 모으기 (선택). 등수가 겹치면 바로 안내하고 멈춘다
  const rewards = [];
  const takenRanks = new Set();
  let rewardErr = "";
  document.querySelectorAll("#rewardRows .reward-row").forEach((row) => {
    const fromIn = row.querySelector(".reward-from"), toIn = row.querySelector(".reward-to");
    const textIn = row.querySelector(".reward-text"), errBox = row.querySelector(".field-err");
    const from = parseInt(fromIn.value);
    const to = parseInt(toIn.value);
    const text = textIn.value.trim();
    [fromIn, toIn, textIn].forEach((x) => x.classList.remove("input-err"));
    errBox.classList.add("hidden");
    // 완전히 빈 줄은 그냥 무시 (실수로 추가한 줄)
    if (!fromIn.value.trim() && !toIn.value.trim() && !text) return;
    let msg = "";
    if (!(from >= 1)) { msg = "시작 등수를 1 이상으로 적어 주세요"; fromIn.classList.add("input-err"); }
    else if (!(to >= from)) { msg = "끝 등수는 시작 등수보다 같거나 커야 해요"; toIn.classList.add("input-err"); }
    else if (!text) { msg = "상품 내용을 적어 주세요 (예: 간식)"; textIn.classList.add("input-err"); }
    if (msg) {
      errBox.textContent = msg;
      errBox.classList.remove("hidden");
      if (!rewardErr) rewardErr = "상품 칸을 확인해 주세요. 빨간 칸을 고치면 저장돼요.";
      return;
    }
    for (let r = from; r <= to; r++) {
      if (takenRanks.has(r)) { rewardErr = `${r}등에 상품이 두 번 들어갔어요. 한 등수에는 상품을 하나만 정해 주세요.`; return; }
      takenRanks.add(r);
    }
    rewards.push({ from, to, kind: "reward", text });
  });
  if (rewardErr) {
    document.getElementById("rewardDetails").open = true;
    createMsg.className = "msg err";
    createMsg.textContent = rewardErr;
    return;
  }

  const match_days = [...selectedDays].sort((a, b) => a - b);
  const dayErr = matchDaysError(match_days);
  if (dayErr) {
    createMsg.className = "msg err";
    createMsg.textContent = dayErr;
    dayButtons.querySelector(".day-btn").focus();
    return;
  }
  const deadline_time = deadlineTime.value;
  const make_days = parseInt(makeDaysSel.value, 10) || 0;
  const league_mode = getLeagueMode();
  const end_date = endDate.value;
  if (league_mode === "short" && !end_date) {
    createMsg.className = "msg err";
    createMsg.textContent = "시험 대비 단기 리그는 리그 종료 희망일을 골라 주세요.";
    endDate.focus();
    return;
  }
  const url = editingSettings ? "/leagues/settings" : "/leagues";
  const { ok, data } = await postJSON(url, { name, subjects, rewards, match_days, deadline_time, make_days, league_mode, end_date },
    createForm.querySelector("button[type=submit]"));
  if (ok) {
    if (editingSettings) closeSettingsEdit();
    else await loadMyLeague();
  } else {
    createMsg.className = "msg err";
    createMsg.textContent = data.error || "리그를 만들지 못했어요.";
  }
});

// ===== 리그 설정 고치기 (관리자, 모집 중): 만들기 화면을 다시 쓴다 =====
let editingSettings = false;
let lastLeagueData = null;

function openSettingsEdit() {
  const lg = lastLeagueData && lastLeagueData.league;
  if (!lg) return;
  editingSettings = true;
  document.getElementById("createTitle").textContent = "⚙️ 리그 설정 고치기";
  document.getElementById("createSubmitBtn").textContent = "설정 저장하기";
  document.getElementById("leagueName").value = lg.name;
  subjectRows.innerHTML = "";
  (lg.subjects || []).forEach((sub) => addSubjectRow(sub.name, sub.count, sub.scope === "자유 출제" ? "" : (sub.scope || "")));
  setLeagueMode(lg.league_mode || "full", lg.end_date || "");
  rewardRows.innerHTML = "";
  (lg.rewards || []).filter((r) => r.kind !== "penalty").forEach((r) => {
    addRewardRow();
    const row = rewardRows.lastElementChild;
    row.querySelector(".reward-from").value = r.from;
    row.querySelector(".reward-to").value = r.to;
    row.querySelector(".reward-text").value = r.text;
  });
  document.getElementById("rewardDetails").open = (lg.rewards || []).some((r) => r.kind !== "penalty");
  selectedDays.clear();
  (lg.match_days || []).forEach((d) => selectedDays.add(d));
  dayButtons.querySelectorAll(".day-btn").forEach((b, i) =>
    b.setAttribute("aria-pressed", selectedDays.has(i) ? "true" : "false"));
  deadlineTime.value = lg.deadline_time || "23:59";
  previewCount.value = Math.max(2, (lastLeagueData.members || []).length || 20);
  updateCreatePreview();
  makeDaysSel.value = String(lg.make_days || 0);
  updateCreatePreview();
  createMsg.textContent = "";
  leagueView.classList.add("hidden");
  noLeagueView.classList.remove("hidden");
  showNoLeague("create");
}

function closeSettingsEdit() {
  editingSettings = false;
  document.getElementById("createTitle").textContent = "리그 만들기 📋";
  document.getElementById("createSubmitBtn").textContent = "리그 만들기";
  loadMyLeague();
}
document.getElementById("editSettingsBtn").addEventListener("click", openSettingsEdit);

// ===== 과목 추가 행 =====
const subjectRows = document.getElementById("subjectRows");
const addSubjectBtn = document.getElementById("addSubjectBtn");

// 문제 수 범위 (서버 app.py의 검사와 같다)
const COUNT_MIN = 1, COUNT_MAX = 10;
let subjectRowSeq = 0;
function addSubjectRow(name = "", count = 1, scope = "") {
  const row = document.createElement("div");
  row.className = "subject-row";
  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "subject-name";
  nameInput.placeholder = "과목 (예: 영어)";
  nameInput.maxLength = 20;
  nameInput.value = name;
  const countInput = document.createElement("input");
  countInput.type = "number";
  countInput.className = "subject-count";
  countInput.min = 1;
  countInput.max = 10;
  countInput.value = count;
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "subject-del";
  delBtn.textContent = "✕";
  delBtn.addEventListener("click", () => row.remove());
  delBtn.setAttribute("aria-label", "과목 지우기");
  countInput.setAttribute("aria-label", "문제 수");
  nameInput.setAttribute("aria-label", "과목 이름");
  const scopeInput = document.createElement("input");
  scopeInput.type = "text";
  scopeInput.className = "subject-scope";
  scopeInput.placeholder = "📖 기본 출제 범위 (예: 중간고사 범위)";
  scopeInput.maxLength = 100;
  scopeInput.value = scope;
  scopeInput.setAttribute("aria-label", "기본 출제 범위");
  // 문제 수가 1~10이 아니면 그 칸 바로 아래에 빨간 안내 (입력하는 동안 바로 보여 준다)
  const countErr = document.createElement("p");
  countErr.className = "field-err hidden";
  countErr.id = `countErr${++subjectRowSeq}`;
  countErr.setAttribute("aria-live", "polite");
  countInput.setAttribute("aria-describedby", countErr.id);
  countInput.addEventListener("input", () => checkCountInput(countInput));
  countInput.addEventListener("blur", () => checkCountInput(countInput));
  row.append(nameInput, countInput, delBtn, countErr, scopeInput);
  subjectRows.appendChild(row);
}

// 문제 수 칸 검사: 맞으면 true. 틀리면 칸을 빨갛게 하고 바로 아래에 이유를 보여 준다
function checkCountInput(input) {
  const raw = input.value.trim();
  const n = Number(raw);
  let err = "";
  if (raw === "") err = `문제 수를 적어 주세요 (${COUNT_MIN}~${COUNT_MAX}개)`;
  else if (!Number.isInteger(n)) err = "문제 수는 정수로 적어 주세요";
  else if (n < COUNT_MIN || n > COUNT_MAX) err = `과목마다 문제는 ${COUNT_MIN}~${COUNT_MAX}개까지 만들 수 있어요 (지금 ${raw}개)`;
  const box = document.getElementById(input.getAttribute("aria-describedby"));
  input.classList.toggle("input-err", !!err);
  input.setAttribute("aria-invalid", err ? "true" : "false");
  box.textContent = err;
  box.classList.toggle("hidden", !err);
  return !err;
}

// 과목은 5개까지 (SPEC 5. 문제 만들기). 5개면 [+ 과목 추가]를 흐리게 하고 바로 아래에 안내
const SUBJECT_MAX = 5;
function syncSubjectLimit() {
  const full = subjectRows.querySelectorAll(".subject-row").length >= SUBJECT_MAX;
  addSubjectBtn.disabled = full;
  document.getElementById("subjectLimitNote").classList.toggle("hidden", !full);
}
// 과목 줄이 생기거나 지워질 때마다 (설정 고치기로 다시 채울 때 포함) 버튼 상태를 맞춘다
new MutationObserver(syncSubjectLimit).observe(subjectRows, { childList: true });
addSubjectBtn.addEventListener("click", () => {
  if (subjectRows.querySelectorAll(".subject-row").length >= SUBJECT_MAX) return;
  addSubjectRow();
});
// 처음에 과목 한 줄 기본으로 보여주기
addSubjectRow("", 1);

// ===== 상품 추가 행 =====
const rewardRows = document.getElementById("rewardRows");
const addRewardBtn = document.getElementById("addRewardBtn");

function addRewardRow() {
  const row = document.createElement("div");
  row.className = "reward-row";
  const from = document.createElement("input");
  from.type = "number";
  from.className = "reward-from";
  from.min = 1;
  from.title = "시작 등수";
  from.setAttribute("aria-label", "시작 등수");
  const dash = document.createElement("span");
  dash.textContent = "~";
  const to = document.createElement("input");
  to.type = "number";
  to.className = "reward-to";
  to.min = 1;
  to.title = "끝 등수";
  to.setAttribute("aria-label", "끝 등수");
  const text = document.createElement("input");
  text.type = "text";
  text.className = "reward-text";
  text.placeholder = "내용 (예: 치킨)";
  text.maxLength = 100;
  text.setAttribute("aria-label", "상품 내용");
  // 등수 칸은 예시 글자가 아니라 진짜 숫자로 채워 둔다: 이미 정한 등수 다음부터 (예: 1등 → 2등)
  const used = [...rewardRows.querySelectorAll(".reward-to")].map((x) => parseInt(x.value)).filter((n) => n >= 1);
  const next = used.length ? Math.max(...used) + 1 : 1;
  from.value = next;
  to.value = next;
  const del = document.createElement("button");
  del.type = "button";
  del.className = "subject-del";
  del.textContent = "✕";
  del.addEventListener("click", () => row.remove());
  const err = document.createElement("p");
  err.className = "field-err hidden";
  row.append(from, dash, to, text, del, err);
  rewardRows.appendChild(row);
}

addRewardBtn.addEventListener("click", addRewardRow);

// ===== 지난 경기 기록·상세 다시 보기 (F13) =====
const OUTCOME_TEXT = {
  win: ["승", "o-win"], lose: ["패", "o-lose"], draw: ["무", "o-draw"],
  both_lose: ["둘 다 패", "o-lose"],
};
const reviewView = document.getElementById("reviewView");
const reviewTitle = document.getElementById("reviewTitle");
const reviewSummary = document.getElementById("reviewSummary");
const reviewForfeit = document.getElementById("reviewForfeit");
const reviewScopes = document.getElementById("reviewScopes");
const reviewList = document.getElementById("reviewList");
const reviewEmpty = document.getElementById("reviewEmpty");

async function loadHistory() {
  let data = {};
  try {
    const res = await fetch("/matches/history");
    data = res.ok ? await res.json() : {};
  } catch (err) {
    data = {};
  }
  historyCard.classList.remove("hidden");
  renderHistoryList(historyList, historyEmpty, Array.isArray(data.history) ? data.history : [], goHome);
}

// 지난 경기 목록 그리기 (지금 리그·지난 리그에서 같이 쓴다). back: 상세 화면의 [뒤로가기]
function renderHistoryList(listEl, emptyEl, rows, back) {
  const historyList = listEl;
  listEl.innerHTML = "";
  emptyEl.classList.toggle("hidden", rows.length > 0);
  for (const h of rows) {
    const li = el("li");
    li.append(el("span", "wk", `${h.week}라운드`));
    if (h.bye) {
      li.append(el("span", "bye", "😴 쉬는 라운드"));
    } else {
      li.append(el("span", "h-opp", `vs ${h.opponent}`));
      li.append(el("span", "h-score", h.forfeit ? "몰수 0 : 0" : `${h.my_score} : ${h.opp_score}`));
      const [label, cls] = OUTCOME_TEXT[h.outcome] || ["", ""];
      li.append(el("span", `h-outcome ${cls}`, label));
      if (h.voids) li.append(el("span", "void-chip", `무효 ${h.voids}`));
      if (h.excluded) li.append(el("span", "void-chip", "순위 제외"));
      const btn = el("button", "btn btn-small history-review-btn", "상세 보기 →");
      btn.type = "button";
      btn.addEventListener("click", () => openReview(h.match_id, back));
      li.append(btn);
    }
    historyList.append(li);
  }
}

let reviewBack = null;
async function openReview(matchId, back) {
  if (back) reviewBack = back;
  let data = {};
  try {
    const res = await fetch(`/matches/${matchId}/review`);
    data = await res.json();
    if (!res.ok) throw new Error(data.error || "경기를 불러오지 못했어요.");
  } catch (err) {
    await askConfirm({ icon: "⚠️", title: "지난 경기를 열지 못했어요", text: err.message || "", ok: "확인" });
    return;
  }
  reviewTitle.textContent = `📜 ${data.week}라운드 · vs ${data.opponent}`;
  const label = { win: "승리", lose: "패배", draw: "무승부", both_lose: "둘 다 패" }[data.outcome] || "";
  reviewSummary.textContent = data.forfeit ? `몰수 경기 · 0 : 0 · ${label}` : `나 ${data.my_score} : ${data.opp_score} 상대 · ${label}`;
  reviewForfeit.textContent = data.forfeit_reason || "";
  reviewForfeit.classList.toggle("hidden", !data.forfeit_reason);
  renderScopeList(reviewScopes, data.scopes, data.week);
  reviewList.innerHTML = "";
  if ((data.my_voids || []).length) {
    const box = el("div", "card void-notice");
    box.append(el("strong", "", "🚩 내가 낸 문제 중 무효 처리된 문제"));
    data.my_voids.forEach((v) => box.append(el("p", "", `"${v.content}" · 이유: ${v.reason}`)));
    reviewList.append(box);
  }
  (data.questions || []).forEach((q, i) => {
    const card = buildAnswerCard(q, `${i + 1}. `);
    addQuestionActions(card, q, () => openReview(matchId, reviewBack));
    reviewList.append(card);
  });
  reviewEmpty.classList.toggle("hidden", (data.questions || []).length > 0);
  showOnly(reviewView);
}
document.getElementById("reviewBackBtn").addEventListener("click", () => (reviewBack || goHome)());

// ===== 닉네임 바꾸기 창 =====
const nicknameModal = document.getElementById("nicknameModal");
const nicknameForm = document.getElementById("nicknameForm");
const nicknameHint = document.getElementById("nicknameHint");
const nicknameInput = document.getElementById("nicknameInput");
const nicknameMsg = document.getElementById("nicknameMsg");
const nicknameSave = document.getElementById("nicknameSave");
let afterNicknameSaved = null; // 바꾼 뒤 이어서 할 일 (예: 리그 다시 들어가기)

function openNicknameModal(hint, afterSave) {
  nicknameHint.textContent = hint || "순위표와 대진표에 보이는 이름이에요 (1~10자).";
  nicknameInput.value = navNickname.textContent;
  nicknameMsg.textContent = "";
  afterNicknameSaved = afterSave || null;
  nicknameModal.classList.remove("hidden");
  nicknameInput.focus();
  nicknameInput.select();
}
function closeNicknameModal() {
  nicknameModal.classList.add("hidden");
  afterNicknameSaved = null;
}
document.getElementById("nicknameBtn").addEventListener("click", () => openNicknameModal());
document.getElementById("nicknameCancel").addEventListener("click", closeNicknameModal);
nicknameModal.addEventListener("click", (e) => { if (e.target === nicknameModal) closeNicknameModal(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !nicknameModal.classList.contains("hidden")) closeNicknameModal();
});
nicknameForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  nicknameMsg.textContent = "";
  const { ok, data } = await postJSON("/me/nickname", { nickname: nicknameInput.value }, nicknameSave);
  if (!ok) {
    nicknameMsg.className = "msg err";
    nicknameMsg.textContent = data.error || "닉네임을 바꾸지 못했어요.";
    return;
  }
  navNickname.textContent = data.nickname;
  const next = afterNicknameSaved;
  closeNicknameModal();
  if (next) await next();
  else await loadMyLeague(); // 대기 화면 명단 등에 새 닉네임 반영
});

// ===== 리그 입장 =====
async function joinLeague() {
  joinMsg.textContent = "";
  const code = document.getElementById("joinCode").value;
  const { ok, data } = await postJSON("/leagues/join", { code }, joinForm.querySelector("button[type=submit]"));
  if (ok) {
    await loadMyLeague();
  } else if (data.reason === "dup_nickname") {
    // 같은 리그에 같은 닉네임이 있으면 바로 바꾸고, 바꾸면 자동으로 다시 들어간다
    openNicknameModal(data.error, joinLeague);
  } else {
    joinMsg.className = "msg err";
    joinMsg.textContent = data.error || "입장하지 못했어요.";
  }
}
joinForm.addEventListener("submit", (e) => {
  e.preventDefault();
  joinLeague();
});

// ===== 이번 경기 카드 (F12): 지금 할 일 =====
// phase(서버가 정함)에 따라 안내 글·마감·버튼을 바꾼다
const matchTask = document.getElementById("matchTask");
const matchDeadline = document.getElementById("matchDeadline");
let currentMatch = null;

const PHASE_TEXT = {
  upcoming: "⏳ 곧 시작해요",
  make: "✏️ 상대에게 낼 문제를 만들 차례예요",
  wait_opp: "✅ 완성! 만들기 마감이 지나면 상대 문제를 풀 수 있어요",
  solve: "🎯 상대 문제를 풀 차례예요",
  wait_result: "⏳ 제출했어요. 상대가 풀기를 기다리는 중이에요",
  result: "🏁 경기가 끝났어요",
  closed: "⌛ 마감이 지났어요",
};

async function refreshMatchStatus() {
  let data = {};
  try {
    const res = await fetch("/matches/current");
    data = await res.json();
  } catch (err) {
    data = {};
  }
  currentMatch = data.has_match ? data : null;
  currentMatchId = data.match_id || null;
  setCountdown("matchCountdown", null);
  makeQuestionsBtn.classList.add("hidden");
  solveBtn.classList.add("hidden");
  matchDeadline.textContent = "";
  document.getElementById("matchScopes").classList.add("hidden");
  matchStatus.textContent = "";
  opponentText.innerHTML = "";

  if (!data.has_match) {
    matchCard.classList.add("hidden");
    return;
  }
  matchCard.classList.remove("hidden");
  if (data.bye) {
    opponentText.textContent = `${data.round}라운드는 쉬어 가요 😴`;
    matchTask.textContent = "이번 라운드는 경기가 없어요. 승점·경기수에 영향이 없어요.";
    return;
  }
  opponentText.append(`${data.round}라운드 상대: `, el("strong", "", data.opponent.nickname));
  matchTask.textContent = PHASE_TEXT[data.phase] || "";
  renderScopeList(document.getElementById("matchScopes"), data.scopes, data.round);

  if (data.phase === "upcoming") {
    matchDeadline.textContent = `라운드 시작: ${fmtStart(data.round_start)}`;
    setCountdown("matchCountdown", data.round_start, "시작까지");
  } else if (data.phase === "make" || data.phase === "wait_opp") {
    if (data.make_deadline) {
      matchDeadline.textContent = `✏️ 만들기 마감: ${fmtDeadline(data.make_deadline, true)}`;
      setCountdown("matchCountdown", data.make_deadline);
    }
    if (data.phase === "make") matchStatus.textContent = completeWarning(data);
    makeQuestionsBtn.textContent = data.phase === "make" ? "✏️ 문제 만들기" : "📄 내 문제 보기 / 다시 고치기";
    makeQuestionsBtn.classList.remove("hidden");
    if (data.phase === "wait_opp") {
      matchStatus.textContent = "만들기 마감 전까지는 [다시 고치기]로 언제든 고칠 수 있어요.";
    }
  } else if (data.phase === "solve") {
    if (data.solve_deadline) {
      matchDeadline.textContent = `🎯 풀기 마감: ${fmtDeadline(data.solve_deadline, true)}`;
      setCountdown("matchCountdown", data.solve_deadline);
    }
    solveBtn.classList.remove("hidden");
    makeQuestionsBtn.textContent = "📄 내가 낸 문제 보기";
    makeQuestionsBtn.classList.remove("hidden");
  } else if (data.phase === "wait_result") {
    matchStatus.textContent = `내 점수: ${data.my_score}/${data.need_total}`;
    if (data.solve_deadline) {
      matchDeadline.textContent = `상대 풀기 마감: ${fmtDeadline(data.solve_deadline, true)}`;
      setCountdown("matchCountdown", data.solve_deadline);
    }
  } else if (data.phase === "result") {
    const OUT = { win: "🎉 승리! (승점 +3)", draw: "🤝 무승부 (승점 +1)", lose: "😢 패배 (승점 0)", both_lose: "둘 다 패 (승점 0)" };
    if (data.forfeit) {
      // 마감을 어겨 끝난 경기: 누가 무엇을 안 했는지 알려 준다
      const what = data.forfeit_stage === "make" ? "만들기 마감까지 [완성]을 누르지 않아" : "풀기 마감까지 제출하지 않아";
      const who = data.outcome === "win" ? `상대가 ${what} 몰수승이에요.` :
        data.outcome === "lose" ? `${what} 몰수패예요.` : `두 사람 다 ${what} 둘 다 패예요.`;
      matchStatus.textContent = `${who} → ${OUT[data.outcome] || ""}`;
    } else {
      matchStatus.textContent = `나 ${data.my_score ?? 0} : ${data.opp_score ?? 0} 상대 → ${OUT[data.outcome] || ""}`;
    }
  }
}
// 만들기 마감까지 남은 시간(시간 단위)
function hoursLeft(iso) {
  return iso ? (Date.parse(iso) - Date.now()) / 3600000 : Infinity;
}
// 아직 [완성]을 안 눌렀을 때 경고 (SPEC: 마감까지 완성하지 않으면 몰수패)
function completeWarning(st) {
  const when = st.make_deadline ? fmtDeadline(st.make_deadline) : "만들기 마감";
  const urgent = hoursLeft(st.make_deadline) < 3 ? "🚨 곧 마감! " : "⚠️ ";
  return `${urgent}아직 [완성]을 안 눌렀어요. ${when}까지 [완성 ✅]을 누르지 않으면 칸을 다 채웠어도 몰수패예요.`;
}

// 라운드 시작 시각 (0시 정각이라 날짜만 보여 줌)
function fmtStart(iso) {
  return `${fmtDate(isoToKstDate(iso))} 00:00`;
}

// ===== 문제 만들기 화면 (F7): 임시 저장 / 완성 / 다시 고치기 =====
const qStateBox = document.getElementById("qStateBox");
const qOpponent = document.getElementById("qOpponent");
const qDeadline = document.getElementById("qDeadline");
const qSavedAt = document.getElementById("qSavedAt");
const completeBtn = document.getElementById("completeBtn");
const reopenBtn = document.getElementById("reopenBtn");
let qMatchId = null;
let qDirty = false; // 저장하지 않은 내용이 있는지

function setDirty(v) {
  qDirty = v;
}
// 브라우저 창 닫기·새로고침 때 기본 경고 (SPEC: 나갈 때 물어보기)
window.addEventListener("beforeunload", (e) => {
  if (qDirty && !questionsView.classList.contains("hidden")) {
    e.preventDefault();
    e.returnValue = "";
  }
});
questionForms.addEventListener("input", () => setDirty(true));
questionForms.addEventListener("change", () => setDirty(true));

async function openQuestions() {
  if (!currentMatchId) return;
  let data = {}, ok = false;
  try {
    const res = await fetch(`/matches/${currentMatchId}/my-questions`);
    data = await res.json();
    ok = res.ok;
  } catch (err) {
    data = { error: "서버에 연결하지 못했어요." };
  }
  if (!ok) {
    await askConfirm({ icon: "⚠️", title: "문제 화면을 열 수 없어요", text: data.error || "", ok: "확인" });
    return;
  }
  qMatchId = currentMatchId;

  // 저장된 문제를 과목별로 나눠 두고, 과목·개수만큼 칸을 그린다
  const bySubject = {};
  for (const q of data.questions || []) (bySubject[q.subject] = bySubject[q.subject] || []).push(q);
  questionForms.innerHTML = "";
  let n = 0;
  for (const subj of data.subjects || []) {
    const card = el("div", "card");
    card.append(el("h3", "", `${subj.name} (${subj.count}문제)`));
    const sc = (data.scopes || []).find((x) => x.subject === subj.name);
    if (sc) card.append(el("p", "scope-banner", `📖 ${data.round}라운드 출제 범위: ${sc.scope}`));
    for (let i = 0; i < subj.count; i++) {
      const block = buildQuestionBlock(subj.name, i, (bySubject[subj.name] || [])[i] || null);
      block.dataset.order = String(n++);
      card.appendChild(block);
    }
    questionForms.appendChild(card);
  }
  qOpponent.textContent = `${data.round}라운드 · 상대: ${data.opponent}`;
  qDeadline.textContent = data.make_deadline ? `✏️ 만들기 마감: ${fmtDeadline(data.make_deadline, true)}` : "";
  setCountdown("qCountdown", data.make_deadline);
  applyQuestionState(data);
  setDirty(false);
  saveQMsg.textContent = "";
  showOnly(questionsView);
}

// 상태에 따라 안내·버튼·입력 잠금
function applyQuestionState(st) {
  let text, cls;
  if (st.can_edit) {
    text = st.my_saved_at ? "✏️ 만드는 중 (임시 저장됨)" : "✏️ 만드는 중 (아직 저장 안 함)";
    cls = "state-draft";
  } else if (st.can_reopen) {
    text = "✅ 완성! 만들기 마감 전까지는 [다시 고치기]로 고칠 수 있어요";
    cls = "state-done";
  } else {
    text = "🔒 만들기 마감이 지나서 문제가 잠겼어요";
    cls = "state-locked";
  }
  qStateBox.textContent = text;
  qStateBox.className = "q-state " + cls;
  qSavedAt.textContent = st.my_saved_at ? `마지막 저장: ${fmtTime(st.my_saved_at)}` : "";
  const warn = document.getElementById("qWarn");
  warn.textContent = st.can_edit ? completeWarning(st) : "";
  warn.classList.toggle("urgent", st.can_edit && hoursLeft(st.make_deadline) < 3);
  saveQuestionsBtn.classList.toggle("hidden", !st.can_edit);
  document.getElementById("saveTopBtn").classList.toggle("hidden", !st.can_edit);
  completeBtn.classList.toggle("hidden", !st.can_edit);
  reopenBtn.classList.toggle("hidden", !st.can_reopen);
  // 위쪽에도 [다시 고치기]: 완성한 뒤 아래까지 내리지 않아도 바로 고칠 수 있게
  document.getElementById("reopenTopBtn").classList.toggle("hidden", !st.can_reopen);
  questionForms.querySelectorAll("input, textarea, select, button").forEach((x) => (x.disabled = !st.can_edit));
}

function fmtTime(iso) {
  const hm = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(iso));
  return `${fmtShort(isoToKstDate(iso))} ${hm}`;
}

// 문제 한 개 입력 블록
function buildQuestionBlock(subject, index, existing) {
  const box = el("div", "q-block");
  box.dataset.subject = subject;
  box.append(el("div", "q-title", `${index + 1}번 문제`));

  const content = el("textarea", "q-content");
  content.placeholder = "문제 내용을 적어 주세요";
  content.rows = 2;
  content.maxLength = 1000;
  if (existing) content.value = existing.content;
  box.appendChild(label("문제", content));

  const typeSel = el("select", "q-type");
  [["mc", "객관식"], ["sa", "주관식"]].forEach(([v, t]) => {
    const o = el("option", "", t);
    o.value = v;
    typeSel.append(o);
  });
  if (existing) typeSel.value = existing.qtype;
  box.appendChild(label("유형", typeSel));

  // 객관식: 보기 2~5개, 왼쪽 동그라미로 정답
  const mcArea = el("div", "mc-area");
  const choiceWrap = el("div", "choice-wrap");
  const group = `q-${subject}-${index}-${Math.random().toString(36).slice(2, 7)}`;
  const startChoices = existing && existing.qtype === "mc" && existing.choices.length ? existing.choices : ["", "", "", ""];
  const answerIdx = existing && existing.qtype === "mc" && existing.answer !== "" ? parseInt(existing.answer, 10) : -1;
  startChoices.forEach((c, ci) => choiceWrap.appendChild(makeChoiceRow(group, ci, c, answerIdx === ci)));
  const choiceBtns = el("div", "choice-btns");
  const addBtn = el("button", "btn btn-small", "+ 보기");
  addBtn.type = "button";
  const delBtn = el("button", "btn btn-small", "− 보기");
  delBtn.type = "button";
  function renumber() {
    choiceWrap.querySelectorAll(".choice-row").forEach((r, i) => {
      r.querySelector(".choice-radio").value = i;
      r.querySelector(".choice-text").placeholder = `보기 ${i + 1}`;
      r.querySelector(".choice-text").setAttribute("aria-label", `보기 ${i + 1}`);
      r.querySelector(".choice-radio").setAttribute("aria-label", `보기 ${i + 1}을 정답으로 고르기`);
    });
    const cnt = choiceWrap.children.length;
    addBtn.dataset.max = cnt >= 5 ? "1" : "";
    delBtn.dataset.min = cnt <= 2 ? "1" : "";
  }
  addBtn.addEventListener("click", () => {
    if (choiceWrap.children.length >= 5) return;
    choiceWrap.appendChild(makeChoiceRow(group, choiceWrap.children.length, "", false));
    renumber();
    setDirty(true);
  });
  delBtn.addEventListener("click", () => {
    if (choiceWrap.children.length <= 2) return;
    choiceWrap.lastElementChild.remove();
    renumber();
    setDirty(true);
  });
  choiceBtns.append(addBtn, delBtn);
  mcArea.append(choiceWrap, choiceBtns, el("p", "hint", "왼쪽 동그라미로 정답을 고르세요 (보기 2~5개)"));
  box.appendChild(mcArea);
  renumber();

  const saArea = el("div", "sa-area");
  const saAnswer = el("input", "sa-answer");
  saAnswer.maxLength = 200;
  saAnswer.placeholder = "정답 (띄어쓰기·대소문자는 채점 때 무시돼요)";
  if (existing && existing.qtype === "sa") saAnswer.value = existing.answer;
  saArea.appendChild(label("정답", saAnswer));
  box.appendChild(saArea);

  const expl = el("textarea", "q-expl");
  expl.placeholder = "해설 (안 써도 돼요)";
  expl.rows = 2;
  expl.maxLength = 1000;
  if (existing) expl.value = existing.explanation;
  box.appendChild(label("해설", expl));

  box.appendChild(el("p", "msg err q-error"));

  function sync() {
    mcArea.classList.toggle("hidden", typeSel.value !== "mc");
    saArea.classList.toggle("hidden", typeSel.value === "mc");
  }
  typeSel.addEventListener("change", sync);
  sync();
  return box;
}

// 객관식 보기 한 줄 (라디오 + 입력칸)
function makeChoiceRow(groupName, idx, value, checked) {
  const row = el("div", "choice-row");
  const radio = el("input", "choice-radio");
  radio.type = "radio";
  radio.name = groupName;
  radio.value = idx;
  radio.setAttribute("aria-label", `보기 ${idx + 1}을 정답으로 고르기`);
  if (checked) radio.checked = true;
  const text = el("input", "choice-text");
  text.type = "text";
  text.maxLength = 200;
  text.placeholder = `보기 ${idx + 1}`;
  text.setAttribute("aria-label", `보기 ${idx + 1}`);
  text.value = value || "";
  row.append(radio, text);
  return row;
}

function label(text, child) {
  const l = el("label", "", text);
  l.appendChild(child);
  return l;
}

function collectQuestions() {
  const questions = [];
  questionForms.querySelectorAll(".q-block").forEach((box) => {
    const subject = box.dataset.subject;
    const qtype = box.querySelector(".q-type").value;
    const content = box.querySelector(".q-content").value;
    const explanation = box.querySelector(".q-expl").value;
    if (qtype === "mc") {
      const choices = [];
      let answer = "";
      box.querySelectorAll(".choice-row").forEach((r, i) => {
        choices.push(r.querySelector(".choice-text").value);
        if (r.querySelector(".choice-radio").checked) answer = i;
      });
      questions.push({ subject, qtype, content, choices, answer, explanation });
    } else {
      questions.push({ subject, qtype, content, answer: box.querySelector(".sa-answer").value, explanation });
    }
  });
  return questions;
}

// action: "draft"(임시 저장) / "complete"(완성)
async function saveQuestions(action, btn) {
  saveQMsg.textContent = "";
  questionForms.querySelectorAll(".q-error").forEach((p) => (p.textContent = ""));
  const { ok, data } = await postJSON(`/matches/${qMatchId}/my-questions`,
    { action, questions: collectQuestions() }, btn);
  if (!ok) {
    saveQMsg.className = "msg err";
    saveQMsg.textContent = data.error || "저장하지 못했어요.";
    // 틀린 문제 칸 옆에 알려 주고 그 칸으로 이동
    if (data.index !== undefined && data.index !== null) {
      const box = questionForms.querySelectorAll(".q-block")[data.index];
      if (box) {
        box.querySelector(".q-error").textContent = data.error;
        box.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
    return false;
  }
  setDirty(false);
  applyQuestionState(data);
  saveQMsg.className = "msg ok";
  saveQMsg.textContent = action === "complete"
    ? "✅ 완성했어요! 만들기 마감이 지나면 상대 문제를 풀 수 있어요."
    : (data.notice || "💾 임시 저장했어요.");
  return true;
}

saveQuestionsBtn.addEventListener("click", () => saveQuestions("draft", saveQuestionsBtn));
// 위쪽 [임시 저장]: 아래 버튼과 같은 일. 결과 안내가 아래에 있어서 위에서도 보이게 버튼 글자로 알려 준다
const saveTopBtn = document.getElementById("saveTopBtn");
saveTopBtn.addEventListener("click", async () => {
  const ok = await saveQuestions("draft", saveTopBtn);
  saveTopBtn.textContent = ok ? "✅ 저장됨" : "⚠️ 저장 못 함";
  setTimeout(() => (saveTopBtn.textContent = "💾 임시 저장"), 1500);
});
completeBtn.addEventListener("click", async () => {
  const yes = await askConfirm({
    icon: "✅", title: "문제를 완성할까요?",
    text: "완성해도 만들기 마감 전까지는 [다시 고치기]로 언제든 고칠 수 있어요. 만들기 마감이 지나면 문제가 잠기고 풀기 기간이 시작돼요.",
    ok: "완성하기",
  });
  if (yes) saveQuestions("complete", completeBtn);
});
// [다시 고치기] (위·아래 두 곳)
async function reopenQuestions(btn) {
  const { ok, data } = await postJSON(`/matches/${qMatchId}/reopen`, {}, btn);
  const text = ok ? "다시 고칠 수 있어요. 다 고치면 만들기 마감 전까지 꼭 [완성]을 다시 눌러 주세요." : (data.error || "되돌리지 못했어요.");
  saveQMsg.className = ok ? "msg ok" : "msg err";
  saveQMsg.textContent = text;
  // 결과 안내는 아래에 있어서 위에서 눌렀을 때도 보이게 상태 상자에 같이 보여 준다
  if (ok) applyQuestionState(data);
  else qStateBox.textContent = `⚠️ ${text}`;
}
reopenBtn.addEventListener("click", () => reopenQuestions(reopenBtn));
document.getElementById("reopenTopBtn").addEventListener("click", (e) => reopenQuestions(e.currentTarget));

// [← 뒤로가기] (위·아래 두 곳): 저장하지 않은 내용이 있으면 물어본다
async function leaveQuestions() {
  if (qDirty && !saveQuestionsBtn.classList.contains("hidden")) {
    const choice = await askConfirm({
      icon: "💾", title: "저장하지 않은 내용이 있어요",
      text: "나가면 마지막으로 저장한 뒤에 쓴 내용이 사라져요.",
      ok: "저장하고 나가기", alt: "저장 안 하고 나가기", cancel: "계속 쓰기",
    });
    if (!choice) return;
    if (choice === true && !(await saveQuestions("draft", saveQuestionsBtn))) return;
  }
  setDirty(false);
  goHome();
}
backBtn.addEventListener("click", leaveQuestions);
document.getElementById("backBtn2").addEventListener("click", leaveQuestions);
makeQuestionsBtn.addEventListener("click", openQuestions);

// ===== 상대 문제 풀기 화면 열기 =====
async function openSolve() {
  if (!currentMatchId) return;
  const res = await fetch(`/matches/${currentMatchId}/questions`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    await askConfirm({ icon: "⚠️", title: "문제를 불러올 수 없어요", text: data.error || "", ok: "확인" });
    goHome();
    return;
  }

  document.getElementById("solveDeadline").textContent = data.solve_deadline
    ? `🎯 풀기 마감: ${fmtDeadline(data.solve_deadline, true)}` : "";
  setCountdown("solveCountdown", data.solve_deadline);
  solveForms.innerHTML = "";
  for (const q of data.questions) {
    solveForms.appendChild(buildSolveBlock(q));
  }
  showOnly(solveView);
  submitMsg.textContent = "";
}

// 문제 한 개 푸는 블록
function buildSolveBlock(q) {
  const box = document.createElement("div");
  box.className = "card q-block";
  box.dataset.qid = q.id;
  box.dataset.qtype = q.qtype;

  const subj = document.createElement("div");
  subj.className = "q-title";
  subj.textContent = `[${q.subject}]`;
  box.appendChild(subj);

  const content = document.createElement("p");
  content.className = "solve-content";
  content.textContent = q.content; // textContent라 안전
  box.appendChild(content);

  if (q.qtype === "mc") {
    q.choices.forEach((c, i) => {
      const row = document.createElement("label");
      row.className = "solve-choice";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "solve-" + q.id;
      radio.value = i;
      const span = document.createElement("span");
      span.textContent = c; // 안전
      row.append(radio, span);
      box.appendChild(row);
    });
  } else {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "solve-answer";
    input.placeholder = "정답을 입력하세요";
    box.appendChild(input);
  }
  return box;
}

// ===== 답안 제출 =====
async function submitAnswers() {
  submitMsg.textContent = "";
  const answers = {};
  const blocks = solveForms.querySelectorAll(".q-block");
  blocks.forEach((box) => {
    const qid = box.dataset.qid;
    if (box.dataset.qtype === "mc") {
      const checked = box.querySelector("input[type=radio]:checked");
      answers[qid] = checked ? checked.value : "";
    } else {
      answers[qid] = box.querySelector(".solve-answer").value;
    }
  });

  const { ok, data } = await postJSON(
    `/matches/${currentMatchId}/submit`,
    { answers },
    submitAnswersBtn
  );
  if (ok) {
    showResult(data);
  } else {
    submitMsg.className = "msg err";
    submitMsg.textContent = data.error || "제출하지 못했어요.";
    // 풀기 화면을 열어 둔 채 마감이 지난 경우 (SPEC: 제출되지 않고 안내)
    if (data.error === "마감이 지났어요") {
      await askConfirm({ icon: "⌛", title: "마감이 지났어요",
        text: "풀기 마감이 지나서 제출되지 않았어요. 이번 경기는 제출하지 않은 것으로 처리돼요.", ok: "확인" });
      goHome();
    }
  }
}

// ===== 채점 결과 보여주기 =====
function showResult(data) {
  setCountdown("solveCountdown", null);
  showOnly(resultView);
  resultScore.textContent = `${data.total}문제 중 ${data.score}개 맞았어요!`;
  const wrong = (data.results || []).filter((r) => !r.is_correct).length;
  const hint = document.getElementById("resultWrongNoteHint");
  hint.textContent = wrong ? `📒 틀린 문제 ${wrong}개를 오답 노트에 담았어요. 리그 홈에서 복습할 수 있어요.` : "";
  hint.classList.toggle("hidden", wrong === 0);
  loadWrongNoteCount(); // 홈으로 돌아가기 전에도 숫자 배지를 최신 상태로 준비

  resultList.innerHTML = "";
  data.results.forEach((r, idx) => {
    const card = buildAnswerCard(r, `${idx + 1}. `);
    // 제출 직후 바로 신고할 수 있다
    addQuestionActions(card, { ...r, can_report: true });
    resultList.appendChild(card);
  });
}

// ===== 문제마다 [신고] (F17) =====
function addQuestionActions(card, q, onChange) {
  if (q.void) {
    card.classList.add("void-q");
    card.append(el("p", "void-badge", `🚩 무효 처리된 문제 · ${q.void_reason || ""} · 맞힌 것으로 인정했어요`));
    return;
  }
  const row = el("div", "q-actions-row");
  if (q.report_status) {
    const txt = { pending: "🚩 신고함 · 관리자 판정 기다리는 중", ok: "🚩 신고함 · 문제없음으로 판정",
      auto_ok: "🚩 신고함 · 판정 기한이 지나 문제없음", void: "🚩 무효로 판정" }[q.report_status] || "🚩 신고함";
    row.append(el("span", "report-status", txt));
  } else if (q.can_report) {
    const rep = el("button", "btn btn-small report-btn", "🚩 신고");
    rep.type = "button";
    rep.addEventListener("click", () => openReportModal(q, () => {
      rep.replaceWith(el("span", "report-status", "🚩 신고함 · 관리자 판정 기다리는 중"));
      if (onChange) onChange();
    }));
    row.append(rep);
  }
  if (row.children.length) card.append(row);
}

const reportModal = document.getElementById("reportModal");
const reportForm = document.getElementById("reportForm");
const reportMsg = document.getElementById("reportMsg");
let reportTarget = null;
function openReportModal(q, done) {
  reportTarget = { q, done };
  document.getElementById("reportQText").textContent = `"${q.content.slice(0, 80)}${q.content.length > 80 ? "…" : ""}"`;
  reportForm.querySelectorAll('input[name="reportReason"]').forEach((r) => (r.checked = false));
  document.getElementById("reportDetail").value = "";
  reportMsg.textContent = "";
  reportModal.classList.remove("hidden");
  reportForm.querySelector('input[name="reportReason"]').focus();
}
function closeReportModal() {
  reportModal.classList.add("hidden");
  reportTarget = null;
}
document.getElementById("reportCancel").addEventListener("click", closeReportModal);
reportModal.addEventListener("click", (e) => { if (e.target === reportModal) closeReportModal(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !reportModal.classList.contains("hidden")) closeReportModal();
});
reportForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!reportTarget) return;
  const checked = reportForm.querySelector('input[name="reportReason"]:checked');
  if (!checked) {
    reportMsg.className = "msg err";
    reportMsg.textContent = "신고 이유를 골라 주세요.";
    return;
  }
  const { ok, data } = await postJSON(`/questions/${reportTarget.q.id}/report`,
    { reason: checked.value, detail: document.getElementById("reportDetail").value },
    document.getElementById("reportSubmit"));
  if (!ok) {
    reportMsg.className = "msg err";
    reportMsg.textContent = data.error || "신고하지 못했어요.";
    return;
  }
  const done = reportTarget.done;
  closeReportModal();
  if (done) done();
});

// ===== 관리자: 신고 처리 카드 =====
async function loadReports() {
  const list = document.getElementById("reportList");
  const doneList = document.getElementById("reportDoneList");
  const badge = document.getElementById("reportBadge");
  let data = null;
  try {
    const res = await fetch("/admin/reports");
    data = res.ok ? await res.json() : null;
  } catch (err) {
    data = null;
  }
  list.innerHTML = "";
  doneList.innerHTML = "";
  if (!data) {
    list.append(el("p", "hint", "신고 목록을 불러오지 못했어요."));
    return;
  }
  badge.textContent = String(data.pending);
  badge.classList.toggle("hidden", data.pending === 0);
  const tabBadge = document.getElementById("reportTabBadge");
  tabBadge.textContent = String(data.pending);
  tabBadge.classList.toggle("hidden", data.pending === 0);
  document.getElementById("tab-reports").setAttribute("aria-label",
    data.pending ? `신고, 처리할 신고 ${data.pending}개` : "신고");
  if (data.league_status === "finished" && data.deadline && data.pending > 0) {
    setCountdown("reportDeadline", data.deadline, "판정 마감까지");
  } else {
    setCountdown("reportDeadline", null);
  }
  const pending = data.items.filter((x) => x.status === "pending");
  if (!pending.length) list.append(el("p", "hint", "처리할 신고가 없어요. ✅"));
  else list.append(el("p", "hint", "줄을 누르면 문제·정답·해설이 펼쳐지고, 거기서 판정해요."));
  appendPaged(list, pending, (it) => buildReportItem(it, true));
  const done = data.items.filter((x) => x.status !== "pending");
  document.getElementById("reportDoneCount").textContent = done.length ? `(${done.length}개)` : "";
  if (!done.length) doneList.append(el("p", "hint", "아직 처리한 신고가 없어요."));
  appendPaged(doneList, done, (it) => buildReportItem(it, false));
}

// 목록을 10개씩 보여 주고 [더 보기]로 이어서 보여 준다 (신고가 많이 쌓여도 화면이 끝없이 길어지지 않게)
const PAGE_SIZE = 10;
function appendPaged(box, items, build) {
  let shown = 0;
  const more = el("button", "btn btn-small more-btn", "");
  more.type = "button";
  function showMore() {
    const next = items.slice(shown, shown + PAGE_SIZE);
    next.forEach((it) => box.insertBefore(build(it), more));
    shown += next.length;
    const left = items.length - shown;
    more.textContent = `더 보기 (남은 ${left}개)`;
    more.classList.toggle("hidden", left <= 0);
  }
  more.addEventListener("click", showMore);
  box.append(more);
  showMore();
}

function buildReportItem(it, actionable) {
  // 한 줄 요약 (누르면 펼쳐진다)
  const box = el("details", "report-item");
  const sum = el("summary", "report-summary");
  const result = actionable ? "" : ({ void: "무효", ok: "문제없음", auto_ok: "문제없음(자동)" }[it.status] || "");
  sum.append(
    el("span", "report-sum-round", `${it.round}R · ${it.subject}`),
    el("span", "report-sum-reason", `🚩 ${it.reason_text}`),
    el("span", "report-sum-who", `출제 ${it.author} · 신고 ${it.reporter}`)
  );
  if (result) sum.append(el("span", "report-sum-result", result));
  box.append(sum);
  // 이유는 요약 줄에 있으니, 펼친 곳에는 학생이 쓴 자세한 이유만
  if (it.detail) box.append(el("p", "report-reason", `💬 "${it.detail}"`));
  box.append(el("p", "scope-banner", `📖 출제 범위 (${it.subject}): ${it.scope}`));
  box.append(buildAdminQuestion({ ...it, opponent_correct: undefined }, 0));
  if (actionable) {
    const row = el("div", "q-actions-row");
    const voidBtn = el("button", "btn btn-small btn-danger", "무효");
    const okBtn = el("button", "btn btn-small", "문제없음");
    voidBtn.type = okBtn.type = "button";
    voidBtn.addEventListener("click", () => judgeReport(it, "void", voidBtn));
    okBtn.addEventListener("click", () => judgeReport(it, "ok", okBtn));
    row.append(voidBtn, okBtn);
    box.append(row);
  } else {
    const txt = { void: "판정: 무효", ok: "판정: 문제없음", auto_ok: "판정: 문제없음 (기한이 지나 자동)" }[it.status] || it.status;
    box.append(el("p", "report-status", txt));
  }
  return box;
}

async function judgeReport(it, decision, btn) {
  const yes = await askConfirm(decision === "void"
    ? { icon: "🚩", title: "이 문제를 무효로 할까요?", danger: true, ok: "무효로 하기",
        text: "푼 학생에게 1점을 인정하고 경기 점수·결과·순위를 다시 계산해요. 오답 노트·정답률에서도 빠져요. 되돌릴 수 없어요." }
    : { icon: "✅", title: "문제없음으로 판정할까요?", ok: "문제없음", text: "점수는 그대로예요." });
  if (!yes) return;
  const { ok, data } = await postJSON(`/admin/reports/${it.id}`, { decision }, btn);
  if (!ok) {
    await askConfirm({ icon: "⚠️", title: "판정하지 못했어요", text: data.error || "", ok: "확인" });
  }
  await loadMyLeague();
}

// 채점된 문제 한 개 카드 (리그 결과·오답 노트에서 같이 쓴다)
// r: { content, qtype, choices, given, correct_answer, is_correct, explanation, subject? }
function buildAnswerCard(r, prefix = "", tag = "") {
  const box = document.createElement("div");
  box.className = "card result-block " + (r.is_correct ? "correct" : "wrong");

  if (tag || r.subject) {
    const meta = document.createElement("div");
    meta.className = "q-title";
    meta.textContent = [r.subject ? `[${r.subject}]` : "", tag].filter(Boolean).join(" ");
    box.appendChild(meta);
  }

  const head = document.createElement("div");
  head.className = "result-q";
  head.textContent = prefix + r.content; // textContent라 태그가 실행되지 않음
  box.appendChild(head);

  const mark = document.createElement("p");
  mark.className = "result-mark";
  mark.textContent = r.submitted === false ? "➖ 제출하지 않음" : (r.is_correct ? "⭕ 정답" : "❌ 오답");
  box.appendChild(mark);

  // 객관식이면 보기를 모두 보여 주고 내 답·정답을 표시
  if (r.qtype === "mc" && Array.isArray(r.choices)) {
    const myIdx = r.given === "" ? -1 : parseInt(r.given);
    const ansIdx = parseInt(r.correct_answer);
    const ul = document.createElement("ul");
    ul.className = "answer-choices";
    r.choices.forEach((c, i) => {
      const li = document.createElement("li");
      const marks = [];
      if (i === ansIdx) { li.classList.add("is-answer"); marks.push("정답"); }
      if (i === myIdx && i !== ansIdx) { li.classList.add("is-mine"); marks.push("내 답"); }
      else if (i === myIdx) marks.push("내 답");
      li.textContent = `${i + 1}. ${c}` + (marks.length ? `  ← ${marks.join(" · ")}` : "");
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (myIdx < 0) {
      const none = document.createElement("p");
      none.className = "result-line";
      none.textContent = "내 답: (안 고름)";
      box.appendChild(none);
    }
  } else {
    const my = document.createElement("p");
    my.className = "result-line";
    my.textContent = `내 답: ${r.given || "(빈칸)"} · 정답: ${r.correct_answer}`;
    box.appendChild(my);
  }

  if (r.explanation) {
    const ex = document.createElement("p");
    ex.className = "result-expl";
    ex.textContent = "해설: " + r.explanation;
    box.appendChild(ex);
  }
  return box;
}

solveBtn.addEventListener("click", openSolve);
solveBackBtn.addEventListener("click", goHome);
submitAnswersBtn.addEventListener("click", submitAnswers);
resultBackBtn.addEventListener("click", goHome);

// ===== 오답 노트 (F18) =====
const noteView = document.getElementById("noteView");
const studyCard = document.getElementById("studyCard");
const wrongNoteBadge = document.getElementById("wrongNoteBadge");
const wrongNoteSummary = document.getElementById("wrongNoteSummary");
const noteBtn = document.getElementById("noteBtn");
const noteSubject = document.getElementById("noteSubject");
const noteHideKnown = document.getElementById("noteHideKnown");
const noteList = document.getElementById("noteList");
const noteCount = document.getElementById("noteCount");
const noteEmpty = document.getElementById("noteEmpty");
const noteEmptyText = document.getElementById("noteEmptyText");
let noteItems = [];

function renderWrongNoteCount(total, active) {
  wrongNoteBadge.textContent = active > 99 ? "99+" : String(active);
  wrongNoteBadge.setAttribute("aria-label", `정리하지 않은 오답 ${active}개`);
  wrongNoteBadge.classList.toggle("hidden", active === 0);
  studyCard.classList.toggle("has-wrong", active > 0);
  if (active > 0) {
    wrongNoteSummary.textContent = `아직 정리하지 않은 오답 ${active}개가 있어요. 잊기 전에 다시 확인해 보세요.`;
    noteBtn.textContent = `오답 ${active}개 복습하기`;
  } else if (total > 0) {
    wrongNoteSummary.textContent = `틀린 문제 ${total}개를 모두 정리했어요! 숨긴 문제도 다시 볼 수 있어요.`;
    noteBtn.textContent = "오답 노트 열기";
  } else {
    wrongNoteSummary.textContent = "아직 오답이 없어요. 경기에서 틀린 문제가 생기면 여기에 모여요.";
    noteBtn.textContent = "오답 노트 열기";
  }
}

async function loadWrongNoteCount() {
  try {
    const res = await fetch("/wrong-notes/count");
    const data = await res.json();
    if (res.ok) renderWrongNoteCount(data.total || 0, data.active || 0);
    else throw new Error();
  } catch (err) {
    wrongNoteBadge.classList.add("hidden");
    wrongNoteSummary.textContent = "오답 개수를 불러오지 못했어요. 오답 노트를 열어 확인해 주세요.";
    noteBtn.textContent = "오답 노트 열기";
  }
}

async function openNotes() {
  showOnly(noteView);
  noteList.innerHTML = "";
  noteCount.textContent = "불러오는 중…";
  noteEmpty.classList.add("hidden");
  let data = {};
  try {
    const res = await fetch("/wrong-notes");
    data = await res.json();
  } catch (err) {
    data = {};
  }
  if (!Array.isArray(data.items)) {
    noteCount.textContent = "오답 노트를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.";
    return;
  }
  noteItems = data.items;
  renderWrongNoteCount(noteItems.length, noteItems.filter((it) => !it.known).length);

  // 과목 고르기: 전체 + 틀린 문제가 있는 과목들
  const prev = noteSubject.value;
  const subjects = [...new Set(noteItems.map((it) => it.subject))];
  noteSubject.innerHTML = "";
  ["전체", ...subjects].forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name === "전체" ? "" : name;
    opt.textContent = name; // 과목 이름도 글자 그대로
    noteSubject.appendChild(opt);
  });
  noteSubject.value = subjects.includes(prev) ? prev : "";
  renderNotes();
}

function renderNotes() {
  const subject = noteSubject.value;
  const hideKnown = noteHideKnown.checked;
  const inSubject = noteItems.filter((it) => !subject || it.subject === subject);
  const shown = inSubject.filter((it) => !(hideKnown && it.known));
  const knownCount = inSubject.filter((it) => it.known).length;

  noteList.innerHTML = "";
  shown.forEach((it) => {
    const card = buildAnswerCard(it, "", `· ${it.where}`);
    if (it.known) card.classList.add("known");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-small known-btn";
    btn.textContent = it.known ? "↩️ 다시 볼래요" : "이제 알아요 ✅";
    btn.addEventListener("click", () => toggleKnown(it, btn));
    card.appendChild(btn);
    noteList.appendChild(card);
  });

  noteCount.textContent = noteItems.length
    ? `틀린 문제 ${inSubject.length}개` + (knownCount ? ` (이제 알아요 ${knownCount}개${hideKnown ? " 숨김" : ""})` : "")
    : "";

  // 비어 있을 때 안내
  if (shown.length === 0) {
    noteEmpty.classList.remove("hidden");
    if (noteItems.length === 0) {
      noteEmptyText.textContent = "아직 틀린 문제가 없어요. 경기에서 틀린 문제가 여기에 모여요.";
    } else if (inSubject.length > 0 && hideKnown) {
      noteEmptyText.textContent = "🎉 이 과목은 모두 '이제 알아요'로 정리했어요! 숨긴 문제를 보려면 위 체크를 꺼 주세요.";
    } else {
      noteEmptyText.textContent = "이 과목에는 틀린 문제가 없어요.";
    }
  } else {
    noteEmpty.classList.add("hidden");
  }
}

async function toggleKnown(item, btn) {
  const next = !item.known;
  const { ok, data } = await postJSON("/wrong-notes/known",
    { source: item.source, key: item.key, known: next }, btn);
  if (!ok) {
    btn.textContent = data.error || "바꾸지 못했어요";
    return;
  }
  item.known = next;
  renderNotes();
  renderWrongNoteCount(noteItems.length, noteItems.filter((it) => !it.known).length);
}

noteSubject.addEventListener("change", renderNotes);
noteHideKnown.addEventListener("change", renderNotes);
noteBtn.addEventListener("click", openNotes);

// 오답 노트 화면의 [뒤로가기]
document.querySelectorAll(".back-home").forEach((btn) => btn.addEventListener("click", goHome));

// ===== 로그아웃 =====
logoutBtn.addEventListener("click", async () => {
  await postJSON("/logout", {});
  showLoggedOut();
});

// ===== 페이지 열 때: 지금 로그인 상태인지 확인 =====
async function checkMe() {
  const res = await fetch("/me");
  const data = await res.json().catch(() => ({}));
  if (data.logged_in) {
    showLoggedIn(data.nickname);
  } else {
    showLoggedOut();
  }
}

checkMe();

// ===== PWA: 서비스 워커 등록 (홈 화면에 앱처럼 설치) =====
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // 설치 기능을 못 써도 앱은 그대로 쓸 수 있으니 조용히 넘어간다
    });
  });
}
