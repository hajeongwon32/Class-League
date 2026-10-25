// 07-create.js · 리그 만들기·설정 고치기, 과목·상품 입력 행

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

