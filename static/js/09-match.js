// 09-match.js · 이번 경기 카드, 문제 만들기, 문제 풀기, 답안 제출, 채점 결과

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

