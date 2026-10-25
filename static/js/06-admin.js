// 06-admin.js · 관리자 화면, 출제 범위, 리그 시작까지 할 일, 리그 시작

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

