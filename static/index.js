// ===== 화면 요소 =====
const authView = document.getElementById("authView");
const homeView = document.getElementById("homeView");
const userArea = document.getElementById("userArea");
const navNickname = document.getElementById("navNickname");

// 랜딩 화면 요소
const landingView = document.getElementById("landingView");
const authBackBtn = document.getElementById("authBackBtn");
const authRoleHint = document.getElementById("authRoleHint");

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
const standingsBody = document.getElementById("standingsBody");
const rewardLegend = document.getElementById("rewardLegend");
const historyCard = document.getElementById("historyCard");
const historyList = document.getElementById("historyList");
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
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

// ===== 화면 전환 =====
function showLoggedIn(nickname) {
  landingView.classList.add("hidden");
  authView.classList.add("hidden");
  homeView.classList.remove("hidden");
  guestArea.classList.add("hidden");
  userArea.classList.remove("hidden");
  navNickname.textContent = nickname;
  loadMyLeague();
}

// 로그인 안 된 상태: 처음엔 랜딩을 보여준다
function showLoggedOut() {
  landingView.classList.remove("hidden");
  authView.classList.add("hidden");
  homeView.classList.add("hidden");
  guestArea.classList.remove("hidden");
  userArea.classList.add("hidden");
}

// 랜딩에서 역할을 고르거나 상단 버튼을 누르면 로그인/회원가입 화면으로
function showAuth(role) {
  landingView.classList.add("hidden");
  authView.classList.remove("hidden");
  homeView.classList.add("hidden");
  guestArea.classList.remove("hidden");
  userArea.classList.add("hidden");
  if (role === "admin") {
    authRoleHint.textContent = "🧑‍🏫 선생님 관리실 — 로그인하거나 가입해 리그를 만들어요.";
    authRoleHint.classList.remove("hidden");
  } else if (role === "student") {
    authRoleHint.textContent = "🎟️ 학생 입장 포털 — 로그인하거나 가입한 뒤 코드로 입장해요.";
    authRoleHint.classList.remove("hidden");
  } else {
    authRoleHint.textContent = ""; // 상단 버튼으로 바로 온 경우
    authRoleHint.classList.add("hidden");
  }
}

// 랜딩 포털 버튼
document.querySelectorAll(".portal").forEach((btn) => {
  btn.addEventListener("click", () => showAuth(btn.dataset.role));
});
// 로그인 화면에서 처음으로 돌아가기
authBackBtn.addEventListener("click", showLoggedOut);

// 상단바: 로그인 버튼 → 로그인 탭, 회원가입 버튼 → 회원가입 탭
navLoginBtn.addEventListener("click", () => {
  showAuth(null);
  tabLogin.click();
});
navRegisterBtn.addEventListener("click", () => {
  showAuth(null);
  tabRegister.click();
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
  const { ok, data } = await postJSON("/register", body);
  if (ok) {
    registerMsg.className = "msg ok";
    registerMsg.textContent = "가입 완료! 이제 로그인해 주세요.";
    registerForm.reset();
    // 로그인 탭으로 자동 전환
    tabLogin.click();
    loginMsg.className = "msg ok";
    loginMsg.textContent = "가입이 끝났어요. 로그인해 보세요!";
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
  const { ok, data } = await postJSON("/login", body);
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

  if (!data.in_league) {
    // 리그 없음 → 만들기/입장 화면
    noLeagueView.classList.remove("hidden");
    leagueView.classList.add("hidden");
    return;
  }

  // 리그 있음 → 리그 정보 화면
  noLeagueView.classList.add("hidden");
  leagueView.classList.remove("hidden");

  leagueName2.textContent = data.league.name;
  leagueStatus.textContent = STATUS_TEXT[data.league.status] || data.league.status;

  const isRecruiting = data.league.status === "recruiting";
  const isRunning = data.league.status === "running" || data.league.status === "finished";

  // 관리자에게만 코드 보여주기
  if (data.is_admin) {
    adminCodeBox.classList.remove("hidden");
    leagueCode.textContent = data.league.code;
  } else {
    adminCodeBox.classList.add("hidden");
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
      li.textContent = m.nickname; // textContent라 HTML 태그가 실행되지 않음
      memberList.appendChild(li);
    }
  }

  // ---- 주차 안내 ----
  if (isRunning && data.week) {
    weekInfo.classList.remove("hidden");
    weekInfo.textContent = `${data.week}주차 / 전체 ${data.total_weeks}주차`;
  } else {
    weekInfo.classList.add("hidden");
  }

  // ---- 이번 주 경기 (학생, 진행 중) ----
  if (isRunning && data.my_opponent !== undefined && data.my_opponent !== null) {
    matchCard.classList.remove("hidden");
    if (data.my_opponent.bye) {
      opponentText.textContent = "이번 주는 쉬어가는 주예요 😴 (승점 변화 없음)";
      makeQuestionsBtn.classList.add("hidden");
      solveBtn.classList.add("hidden");
      matchStatus.textContent = "";
    } else {
      opponentText.innerHTML = "";
      opponentText.append("이번 주 상대: ");
      const strong = document.createElement("strong");
      strong.textContent = data.my_opponent.nickname;
      opponentText.append(strong);
      makeQuestionsBtn.classList.remove("hidden");
      // 경기 상태(상대 준비됨/내가 풀었는지)를 따로 불러와 풀기 버튼 처리
      refreshMatchStatus();
    }
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
      wk.textContent = `${row.week}주차`;
      const opp = document.createElement("span");
      if (row.bye) {
        opp.textContent = "😴 쉬는 주";
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

  // ---- 순위표 (진행 중) ----
  if (isRunning && Array.isArray(data.standings)) {
    standingsCard.classList.remove("hidden");
    standingsBody.innerHTML = "";
    const rewards = (data.league && data.league.rewards) || [];
    for (const s of data.standings) {
      const tr = document.createElement("tr");
      if (s.user_id === data.my_user_id) tr.classList.add("me");
      // 상품·벌칙 구간이면 색칠
      const rw = rewards.find((r) => s.rank >= r.from && s.rank <= r.to);
      if (rw) tr.classList.add(rw.kind === "penalty" ? "zone-penalty" : "zone-reward");
      const cells = [s.rank, s.nickname, s.played, s.win, s.draw, s.lose, s.points];
      cells.forEach((val, i) => {
        const td = document.createElement("td");
        td.textContent = val; // textContent로 안전하게
        if (i === 6) td.className = "pts"; // 승점 강조
        tr.appendChild(td);
      });
      standingsBody.appendChild(tr);
    }
    // 상품·벌칙 범례
    if (rewards.length > 0) {
      rewardLegend.classList.remove("hidden");
      rewardLegend.innerHTML = "";
      for (const r of rewards) {
        const chip = document.createElement("div");
        chip.className =
          "legend-chip " + (r.kind === "penalty" ? "zone-penalty" : "zone-reward");
        const range = r.from === r.to ? `${r.from}등` : `${r.from}~${r.to}등`;
        chip.textContent = `${range}: ${r.text}`;
        rewardLegend.appendChild(chip);
      }
    } else {
      rewardLegend.classList.add("hidden");
    }
    // 지난 경기 기록 불러오기 (학생만)
    if (data.my_opponent !== undefined) loadHistory();
  } else {
    standingsCard.classList.add("hidden");
    historyCard.classList.add("hidden");
  }

  // ---- 리그 시작 버튼 (관리자 + 모집 중) ----
  if (data.is_admin && isRecruiting) {
    startBtn.classList.remove("hidden");
  } else {
    startBtn.classList.add("hidden");
  }
  startMsg.textContent = "";
}

// ===== 리그 시작 (관리자) =====
startBtn.addEventListener("click", async () => {
  startMsg.textContent = "";
  const { ok, data } = await postJSON("/leagues/start", {});
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

  // 과목 모으기
  const subjects = [];
  document.querySelectorAll("#subjectRows .subject-row").forEach((row) => {
    const sname = row.querySelector(".subject-name").value.trim();
    const count = parseInt(row.querySelector(".subject-count").value);
    if (sname) subjects.push({ name: sname, count: count });
  });
  if (subjects.length === 0) {
    createMsg.className = "msg err";
    createMsg.textContent = "과목을 하나 이상 넣어 주세요.";
    return;
  }

  // 상품·벌칙 모으기 (선택)
  const rewards = [];
  document.querySelectorAll("#rewardRows .reward-row").forEach((row) => {
    const from = parseInt(row.querySelector(".reward-from").value);
    const to = parseInt(row.querySelector(".reward-to").value);
    const kind = row.querySelector(".reward-kind").value;
    const text = row.querySelector(".reward-text").value.trim();
    if (from >= 1 && to >= from && text) {
      rewards.push({ from, to, kind, text });
    }
  });

  const { ok, data } = await postJSON("/leagues", { name, subjects, rewards });
  if (ok) {
    await loadMyLeague();
  } else {
    createMsg.className = "msg err";
    createMsg.textContent = data.error || "리그를 만들지 못했어요.";
  }
});

// ===== 과목 추가 행 =====
const subjectRows = document.getElementById("subjectRows");
const addSubjectBtn = document.getElementById("addSubjectBtn");

function addSubjectRow(name = "", count = 3) {
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
  countInput.max = 20;
  countInput.value = count;
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "subject-del";
  delBtn.textContent = "✕";
  delBtn.addEventListener("click", () => row.remove());
  row.append(nameInput, countInput, delBtn);
  subjectRows.appendChild(row);
}

addSubjectBtn.addEventListener("click", () => addSubjectRow());
// 처음에 과목 한 줄 기본으로 보여주기
addSubjectRow("", 3);

// ===== 상품·벌칙 추가 행 =====
const rewardRows = document.getElementById("rewardRows");
const addRewardBtn = document.getElementById("addRewardBtn");

function addRewardRow() {
  const row = document.createElement("div");
  row.className = "reward-row";
  const from = document.createElement("input");
  from.type = "number";
  from.className = "reward-from";
  from.min = 1;
  from.placeholder = "1";
  from.title = "시작 등수";
  const dash = document.createElement("span");
  dash.textContent = "~";
  const to = document.createElement("input");
  to.type = "number";
  to.className = "reward-to";
  to.min = 1;
  to.placeholder = "3";
  to.title = "끝 등수";
  const kind = document.createElement("select");
  kind.className = "reward-kind";
  kind.innerHTML = '<option value="reward">상품</option><option value="penalty">벌칙</option>';
  const text = document.createElement("input");
  text.type = "text";
  text.className = "reward-text";
  text.placeholder = "내용 (예: 치킨)";
  text.maxLength = 100;
  const del = document.createElement("button");
  del.type = "button";
  del.className = "subject-del";
  del.textContent = "✕";
  del.addEventListener("click", () => row.remove());
  row.append(from, dash, to, kind, text, del);
  rewardRows.appendChild(row);
}

addRewardBtn.addEventListener("click", addRewardRow);

// ===== 지난 경기 기록 불러오기 =====
const OUTCOME_TEXT = {
  win: ["승", "o-win"],
  lose: ["패", "o-lose"],
  draw: ["무", "o-draw"],
  pending: ["진행 중", "o-pending"],
};

async function loadHistory() {
  const res = await fetch("/matches/history");
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !Array.isArray(data.history)) {
    historyCard.classList.add("hidden");
    return;
  }
  // 결과가 있거나 쉬는 주 하나라도 있으면 보여줌
  const shown = data.history.filter((h) => h.bye || h.outcome !== undefined);
  if (shown.length === 0) {
    historyCard.classList.add("hidden");
    return;
  }
  historyCard.classList.remove("hidden");
  historyList.innerHTML = "";
  for (const h of data.history) {
    const li = document.createElement("li");
    const wk = document.createElement("span");
    wk.className = "wk";
    wk.textContent = `${h.week}주차`;
    li.appendChild(wk);
    if (h.bye) {
      const b = document.createElement("span");
      b.className = "bye";
      b.textContent = "😴 쉬는 주";
      li.appendChild(b);
    } else {
      const opp = document.createElement("span");
      opp.className = "h-opp";
      opp.textContent = `vs ${h.opponent}`;
      const score = document.createElement("span");
      score.className = "h-score";
      score.textContent = `${h.my_score} : ${h.opp_score}`;
      const [label, cls] = OUTCOME_TEXT[h.outcome] || ["", ""];
      const badge = document.createElement("span");
      badge.className = "h-outcome " + cls;
      badge.textContent = label;
      li.append(opp, score, badge);
    }
    historyList.appendChild(li);
  }
}

// ===== 리그 입장 =====
joinForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  joinMsg.textContent = "";
  const code = document.getElementById("joinCode").value;
  const { ok, data } = await postJSON("/leagues/join", { code });
  if (ok) {
    await loadMyLeague();
  } else {
    joinMsg.className = "msg err";
    joinMsg.textContent = data.error || "입장하지 못했어요.";
  }
});

// ===== 문제 만들기 화면 =====
// 과목 설정과 기존 문제를 불러와 입력 폼을 그린다
async function openQuestions() {
  const res = await fetch("/questions/mine");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || "문제 화면을 열 수 없어요.");
    return;
  }

  // 기존 문제를 과목+순서별로 꺼내 쓸 수 있게 정리
  const bySubject = {};
  for (const q of data.questions || []) {
    (bySubject[q.subject] = bySubject[q.subject] || []).push(q);
  }

  questionForms.innerHTML = "";
  for (const subj of data.subjects || []) {
    const card = document.createElement("div");
    card.className = "card";
    const h = document.createElement("h3");
    h.textContent = `${subj.name} (${subj.count}문제)`;
    card.appendChild(h);

    for (let i = 0; i < subj.count; i++) {
      const existing = (bySubject[subj.name] || [])[i] || null;
      card.appendChild(buildQuestionBlock(subj.name, i, existing));
    }
    questionForms.appendChild(card);
  }

  homeView.classList.add("hidden");
  questionsView.classList.remove("hidden");
  saveQMsg.textContent = "";
}

// 문제 한 개 입력 블록을 만든다
function buildQuestionBlock(subject, index, existing) {
  const box = document.createElement("div");
  box.className = "q-block";
  box.dataset.subject = subject;

  const title = document.createElement("div");
  title.className = "q-title";
  title.textContent = `${index + 1}번 문제`;
  box.appendChild(title);

  // 문제 내용
  const content = document.createElement("textarea");
  content.className = "q-content";
  content.placeholder = "문제 내용을 적어 주세요";
  content.rows = 2;
  if (existing) content.value = existing.content;
  box.appendChild(label("문제", content));

  // 유형 선택
  const typeSel = document.createElement("select");
  typeSel.className = "q-type";
  typeSel.innerHTML =
    '<option value="mc">객관식</option><option value="sa">주관식</option>';
  if (existing) typeSel.value = existing.qtype;
  box.appendChild(label("유형", typeSel));

  // 객관식 영역
  const mcArea = document.createElement("div");
  mcArea.className = "mc-area";
  // 보기 4개 기본
  const choiceWrap = document.createElement("div");
  choiceWrap.className = "choice-wrap";
  const existingChoices =
    existing && existing.qtype === "mc" ? existing.choices : ["", "", "", ""];
  const answerIdx =
    existing && existing.qtype === "mc" ? parseInt(existing.answer) : 0;
  existingChoices.forEach((c, ci) => {
    choiceWrap.appendChild(makeChoiceRow(subject + "-" + index, ci, c, answerIdx === ci));
  });
  mcArea.appendChild(choiceWrap);
  const hintMc = document.createElement("p");
  hintMc.className = "hint";
  hintMc.textContent = "왼쪽 동그라미로 정답을 고르세요 (보기 2~5개)";
  mcArea.appendChild(hintMc);
  box.appendChild(mcArea);

  // 주관식 영역
  const saArea = document.createElement("div");
  saArea.className = "sa-area";
  const saAnswer = document.createElement("input");
  saAnswer.className = "sa-answer";
  saAnswer.placeholder = "정답 (띄어쓰기·대소문자는 채점 때 무시돼요)";
  if (existing && existing.qtype === "sa") saAnswer.value = existing.answer;
  saArea.appendChild(label("정답", saAnswer));
  box.appendChild(saArea);

  // 해설
  const expl = document.createElement("textarea");
  expl.className = "q-expl";
  expl.placeholder = "해설 (안 써도 돼요)";
  expl.rows = 2;
  if (existing) expl.value = existing.explanation;
  box.appendChild(label("해설", expl));

  // 유형에 따라 보이기/숨기기
  function sync() {
    if (typeSel.value === "mc") {
      mcArea.classList.remove("hidden");
      saArea.classList.add("hidden");
    } else {
      mcArea.classList.add("hidden");
      saArea.classList.remove("hidden");
    }
  }
  typeSel.addEventListener("change", sync);
  sync();

  return box;
}

// 객관식 보기 한 줄 (라디오 + 입력칸)
function makeChoiceRow(groupName, idx, value, checked) {
  const row = document.createElement("div");
  row.className = "choice-row";
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.className = "choice-radio";
  radio.name = groupName; // 같은 블록 안에서만 하나 선택되게
  radio.value = idx;
  if (checked) radio.checked = true;
  const text = document.createElement("input");
  text.type = "text";
  text.className = "choice-text";
  text.placeholder = `보기 ${idx + 1}`;
  text.value = value || "";
  row.append(radio, text);
  return row;
}

// 라벨로 감싸기
function label(text, el) {
  const l = document.createElement("label");
  l.textContent = text;
  l.appendChild(el);
  return l;
}

// 입력한 문제들을 모아서 저장
async function saveQuestions() {
  saveQMsg.textContent = "";
  const questions = [];
  // 라디오 그룹을 블록별로 묶기 위해 블록마다 처리
  const blocks = questionForms.querySelectorAll(".q-block");
  blocks.forEach((box) => {
    const subject = box.dataset.subject;
    const qtype = box.querySelector(".q-type").value;
    const content = box.querySelector(".q-content").value;
    const explanation = box.querySelector(".q-expl").value;
    if (qtype === "mc") {
      const rows = box.querySelectorAll(".choice-row");
      const choices = [];
      let answer = 0;
      rows.forEach((r, i) => {
        choices.push(r.querySelector(".choice-text").value);
        if (r.querySelector(".choice-radio").checked) answer = i;
      });
      questions.push({ subject, qtype, content, choices, answer, explanation });
    } else {
      const answer = box.querySelector(".sa-answer").value;
      questions.push({ subject, qtype, content, answer, explanation });
    }
  });

  const { ok, data } = await postJSON("/questions", { questions });
  if (ok) {
    saveQMsg.className = "msg ok";
    saveQMsg.textContent = "저장했어요! 👍";
  } else {
    saveQMsg.className = "msg err";
    saveQMsg.textContent = data.error || "저장하지 못했어요.";
  }
}

makeQuestionsBtn.addEventListener("click", openQuestions);
backBtn.addEventListener("click", () => {
  questionsView.classList.add("hidden");
  homeView.classList.remove("hidden");
  loadMyLeague();
});
saveQuestionsBtn.addEventListener("click", saveQuestions);

// ===== 이번 주 경기 상태 (풀기 버튼 처리) =====
async function refreshMatchStatus() {
  const res = await fetch("/matches/current");
  const data = await res.json().catch(() => ({}));
  if (!data.has_match || data.bye) {
    solveBtn.classList.add("hidden");
    matchStatus.textContent = "";
    return;
  }
  currentMatchId = data.match_id;

  if (data.i_solved) {
    // 이미 풀었음
    solveBtn.classList.add("hidden");
    let msg = `✅ 이미 풀었어요. 내 점수: ${data.my_score}/${data.total}`;
    if (data.result) {
      msg += " · 경기 결과가 순위표에 반영됐어요!";
    } else {
      msg += " · 상대가 아직 안 풀어서 결과를 기다리는 중이에요.";
    }
    matchStatus.textContent = msg;
  } else if (!data.opponent_ready) {
    // 상대가 아직 문제를 안 만듦
    solveBtn.classList.add("hidden");
    matchStatus.textContent = "⏳ 상대가 아직 문제를 다 만들지 않았어요. 조금 기다려 주세요.";
  } else {
    // 풀 수 있음
    solveBtn.classList.remove("hidden");
    matchStatus.textContent = "상대가 문제를 다 만들었어요! 풀어 보세요.";
  }
}

// ===== 상대 문제 풀기 화면 열기 =====
async function openSolve() {
  if (!currentMatchId) return;
  const res = await fetch(`/matches/${currentMatchId}/questions`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || "문제를 불러올 수 없어요.");
    return;
  }

  solveForms.innerHTML = "";
  for (const q of data.questions) {
    solveForms.appendChild(buildSolveBlock(q));
  }
  homeView.classList.add("hidden");
  solveView.classList.remove("hidden");
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
    { answers }
  );
  if (ok) {
    showResult(data);
  } else {
    submitMsg.className = "msg err";
    submitMsg.textContent = data.error || "제출하지 못했어요.";
  }
}

// ===== 채점 결과 보여주기 =====
function showResult(data) {
  solveView.classList.add("hidden");
  resultView.classList.remove("hidden");
  resultScore.textContent = `${data.total}문제 중 ${data.score}개 맞았어요!`;

  resultList.innerHTML = "";
  data.results.forEach((r, idx) => {
    const box = document.createElement("div");
    box.className = "card result-block " + (r.is_correct ? "correct" : "wrong");

    const head = document.createElement("div");
    head.className = "result-q";
    head.textContent = `${idx + 1}. ${r.content}`;
    box.appendChild(head);

    const mark = document.createElement("p");
    mark.className = "result-mark";
    mark.textContent = r.is_correct ? "⭕ 정답" : "❌ 오답";
    box.appendChild(mark);

    // 내가 쓴 답 / 정답
    const my = document.createElement("p");
    my.className = "result-line";
    if (r.qtype === "mc") {
      const myIdx = parseInt(r.given);
      const ansIdx = parseInt(r.correct_answer);
      my.textContent =
        `내 답: ${r.choices[myIdx] !== undefined ? r.choices[myIdx] : "(안 고름)"}` +
        ` · 정답: ${r.choices[ansIdx]}`;
    } else {
      my.textContent = `내 답: ${r.given || "(빈칸)"} · 정답: ${r.correct_answer}`;
    }
    box.appendChild(my);

    if (r.explanation) {
      const ex = document.createElement("p");
      ex.className = "result-expl";
      ex.textContent = "해설: " + r.explanation;
      box.appendChild(ex);
    }
    resultList.appendChild(box);
  });
}

solveBtn.addEventListener("click", openSolve);
solveBackBtn.addEventListener("click", () => {
  solveView.classList.add("hidden");
  homeView.classList.remove("hidden");
  loadMyLeague();
});
submitAnswersBtn.addEventListener("click", submitAnswers);
resultBackBtn.addEventListener("click", () => {
  resultView.classList.add("hidden");
  homeView.classList.remove("hidden");
  loadMyLeague();
});

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
