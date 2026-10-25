// 01-core.js · 화면 요소, 서버 요청 도우미, 화면 전환, 학생/관리자 고르기

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

