// 08-history.js · 지난 경기 기록·상세, 닉네임 바꾸기, 리그 입장

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

