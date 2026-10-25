// 04-standings.js · 확인 창, 순위표·최종 결과, 리그 보관·닫기·삭제·내보내기, 지난 리그, 나가기, 코드 복사

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

