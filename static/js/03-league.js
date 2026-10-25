// 03-league.js · 내 리그 불러오기(리그 홈), 관리자 메뉴 탭

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

