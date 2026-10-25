// 11-notes.js · 오답 노트, 로그아웃, 페이지 열 때 로그인 확인, 서비스 워커 등록

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
