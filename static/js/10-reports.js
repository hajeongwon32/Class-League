// 10-reports.js · 문제 신고, 관리자 신고 처리

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

