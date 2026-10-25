// 05-schedule.js · 경기 일정 계산, 남은 시간, 경기 요일·리그 기간 방식

// ===== 경기 일정 계산 (서버 app.py의 build_schedule과 같은 규칙) =====
// 날짜는 "YYYY-MM-DD"(한국 날짜) 글자로 다룬다. 요일은 월=0 … 일=6
const DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"];


function todayKST() {
  // 브라우저 시간대와 상관없이 한국 날짜
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
}
// 서버가 준 UTC 시각(ISO 글자)을 한국 날짜 "YYYY-MM-DD"로
function isoToKstDate(iso) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date(iso));
}
// 서버가 준 마감 시각(UTC)을 한국 시간 "10/21(수) 22:00"으로. 0시 정각은 전날 23:59로 보여 준다
function fmtDeadline(iso, long = false) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(iso));
  let ymd = isoToKstDate(iso);
  let hm = parts;
  if (hm === "00:00") {
    ymd = addDays(ymd, -1);
    hm = "23:59";
  }
  return `${long ? fmtDate(ymd) : fmtShort(ymd)} ${hm}`;
}
// ===== 마감·시작까지 남은 시간 =====
function remainingText(ms, label) {
  if (ms <= 0) return "⌛ 마감됐어요";
  const total = Math.floor(ms / 1000);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (days > 0) return `${label} ${days}일 ${hours}시간 ${mins}분`;
  if (hours > 0) return `${label} ${hours}시간 ${mins}분`;
  return `${label} ${mins}분 ${String(secs).padStart(2, "0")}초`;
}

function setCountdown(id, target, label = "마감까지") {
  const node = document.getElementById(id);
  if (!node) return;
  if (!target) {
    delete node.dataset.target;
    node.classList.add("hidden");
    node.textContent = "";
    return;
  }
  node.dataset.target = target;
  node.dataset.label = label;
  node.classList.remove("hidden");
  updateCountdownNode(node);
}
const countdownReloaded = new Set();
function updateCountdownNode(node) {
  const ms = Date.parse(node.dataset.target) - Date.now();
  node.textContent = remainingText(ms, node.dataset.label || "마감까지");
  node.classList.toggle("urgent", ms > 0 && ms <= 3 * 3600000);
  // 홈을 열어 둔 사이 시작·마감되면 서버에서 다음 상태를 다시 받아 온다.
  // 문제 작성/풀기 화면은 작성 중인 내용을 잃지 않도록 자동으로 나가지 않는다.
  const key = `${node.id}:${node.dataset.target}`;
  if (ms <= 0 && node.id === "matchCountdown" && !homeView.classList.contains("hidden") && !countdownReloaded.has(key)) {
    countdownReloaded.add(key);
    setTimeout(loadMyLeague, 500);
  }
}
function updateCountdowns() {
  document.querySelectorAll(".countdown[data-target]").forEach(updateCountdownNode);
}
setInterval(updateCountdowns, 1000);

function addDays(ymd, n) {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
function weekdayOf(ymd) {
  const [y, m, d] = ymd.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // 일요일=0 → 월요일=0으로
}
function daysBetween(a, b) {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}
function fmtDate(ymd) {
  const [, m, d] = ymd.split("-").map(Number);
  return `${m}월 ${d}일(${DAY_NAMES[weekdayOf(ymd)]})`;
}
function fmtShort(ymd) {
  const [, m, d] = ymd.split("-").map(Number);
  return `${m}/${d}(${DAY_NAMES[weekdayOf(ymd)]})`;
}
function roundCount(n) {
  if (n < 2) return 0;
  return n % 2 === 0 ? n - 1 : n;
}
// 경기 요일 검사: 맞으면 "" , 틀리면 안내 글
function matchDaysError(days) {
  if (days.length === 0) return "경기 요일을 하나 이상 골라 주세요.";
  if (days.length > 3) return "경기 요일은 1주일에 3번까지 고를 수 있어요.";
  if (days.length > 1) {
    const s = [...days].sort((a, b) => a - b);
    const gaps = s.slice(1).map((v, i) => v - s[i]).concat(s[0] + 7 - s[s.length - 1]);
    if (Math.min(...gaps) < 2) return "경기 요일끼리는 하루 이상 띄워 주세요 (예: 월·화는 안 돼요).";
  }
  return "";
}
function matchDatesFrom(first, days, count) {
  const out = [];
  let d = first;
  while (out.length < count) {
    if (days.includes(weekdayOf(d))) out.push(d);
    d = addDays(d, 1);
  }
  return out;
}
// 가장 짧은 라운드의 날 수 (요일 하나면 7일)
function shortestRoundDays(days) {
  const s = [...days].sort((a, b) => a - b);
  if (s.length === 1) return 7;
  return Math.min(...s.slice(1).map((v, i) => v - s[i]).concat(s[0] + 7 - s[s.length - 1]));
}
// 라운드별 날짜: start(시작일), makeLast(만들기 마지막 날), last(라운드 마지막 날)
// makeDays: 0이면 자동(라운드의 절반), 아니면 그 날 수
function buildSchedule(first, days, nRounds, makeDays = 0) {
  if (nRounds <= 0) return [];
  let starts = matchDatesFrom(first, days, nRounds + 1);
  // 첫날이 경기 요일이 아니면(오늘 바로 시작) 그날이 1라운드 시작 (서버와 같은 규칙)
  if (!days.includes(weekdayOf(first))) starts = [first, ...starts.slice(0, nRounds)];
  const rounds = [];
  for (let i = 0; i < nRounds; i++) {
    const len = daysBetween(starts[i], starts[i + 1]);
    let make = makeDays > 0 ? makeDays : Math.max(1, Math.floor(len / 2));
    make = Math.min(make, len - 1); // 풀기 기간이 하루는 남게
    rounds.push({
      round: i + 1,
      start: starts[i],
      makeLast: addDays(starts[i], make - 1),
      solveFirst: addDays(starts[i], make),
      last: addDays(starts[i + 1], -1),
    });
  }
  return rounds;
}
function rangeText(a, b) {
  return a === b ? fmtShort(a) : `${fmtShort(a)}~${fmtShort(b)}`;
}
// 미리 보기 글과 라운드 목록 그리기
// 작은 요소 만들기 도우미 (글자는 항상 textContent로)
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// 미리 보기 그리기
// summaryEl: ① 요약(몇 라운드, 언제 시작·끝) ② 한 라운드 진행 방식(요일·시각)
// tbodyEl: 라운드별 표 (만들기 기간·마감, 풀기 기간·마감)
// 마감 시각 글자 ("23:59", "22:00" …)를 받아 "수 22:00"처럼 쓴다
// compact: 리그 시작 화면처럼 요약만 크게 보이고 '한 라운드 진행 방식'은 접어 둘 때
// endDate(YYYY-MM-DD)를 주면 시험 대비 단기 리그: 그날 마감까지 끝나는 라운드만 (서버 rounds_until과 같은 규칙)
function shortRoundCount(first, days, makeDays, endDate, nMax) {
  if (!endDate || first > endDate) return 0;
  return buildSchedule(first, days, nMax, makeDays).filter((r) => r.last <= endDate).length;
}

function renderPreview(summaryEl, tbodyEl, first, days, nPlayers, makeDays = 0, dl = "23:59", compact = false, endDate = "") {
  summaryEl.innerHTML = "";
  tbodyEl.innerHTML = "";
  const nFull = roundCount(nPlayers);
  if (nFull === 0) {
    summaryEl.append(el("p", "preview-empty", "학생이 2명 이상이어야 일정이 생겨요."));
    return;
  }
  let n = nFull;
  if (endDate) {
    n = shortRoundCount(first, days, makeDays, endDate, nFull);
    if (n === 0) {
      summaryEl.append(el("p", "preview-empty",
        `⚠️ ${fmtDate(endDate)}까지 끝낼 수 있는 라운드가 없어요. 종료 희망일을 늦추거나 경기 요일을 늘려 주세요.`));
      return;
    }
  }
  const rounds = buildSchedule(first, days, n, makeDays);
  const end = rounds[rounds.length - 1].last;
  const weeks = Math.ceil((daysBetween(first, end) + 1) / 7);

  // ① 요약
  const big = el("div", "preview-big");
  big.append(el("strong", "", `총 ${n}라운드`), el("span", "", ` · 약 ${weeks}주`));
  const period = el("div", "preview-period");
  period.append(
    el("span", "", `🏁 ${fmtDate(first)} 00:00 시작`),
    el("span", "arrow", "→"),
    el("span", "", `🏆 ${fmtDate(end)} ${dl} 끝`)
  );
  summaryEl.append(big, period);
  if (endDate) {
    summaryEl.append(el("p", "hint",
      `📝 시험 대비 단기 리그: ${fmtDate(endDate)}까지 ${n}라운드 (모두와 다 붙으려면 ${nFull}라운드). 학생마다 서로 다른 상대와 경기해요.`));
    if (n < 2 && nPlayers > 2) {
      summaryEl.append(el("p", "msg err", "⚠️ 라운드가 너무 적어요. 종료 희망일을 늦추거나 경기 요일을 늘리면 더 많이 경기할 수 있어요."));
    }
    if (nPlayers % 2 === 1 && n < nFull) {
      summaryEl.append(el("p", "hint", `학생이 ${nPlayers}명(홀수)이라 쉬는 횟수가 학생마다 다를 수 있어서, 순위는 경기당 평균 승점으로 정해요.`));
    }
  } else if (rounds.length >= 6) {
    // 전체 리그는 길어질 수 있어서 시험 전에 끝내야 하면 단기 리그를 알려 준다
    summaryEl.append(el("p", "hint", "💡 시험 전까지 끝내야 하면 ② 리그 기간에서 '시험 대비 단기 리그'를 골라 보세요."))
  }
  if (nPlayers % 2 === 1 && !endDate) {
    summaryEl.append(el("p", "hint", `학생이 ${nPlayers}명(홀수)이라 라운드마다 한 명씩 돌아가며 쉬어요.`));
  }

  // ② 한 라운드는 이렇게 (경기 요일마다 같은 모양이 매주 반복)
  let howParent = summaryEl;
  if (compact) {
    howParent = el("details", "preview-details");
    howParent.append(el("summary", "", "한 라운드 진행 방식 보기"));
    summaryEl.append(howParent);
  } else {
    summaryEl.append(el("p", "preview-sub", "한 라운드는 이렇게 진행돼요 (매주 반복)"));
  }
  const howWrap = el("div", "table-wrap");
  const how = el("table", "round-table how-table");
  const hh = el("thead");
  const hr = el("tr");
  ["라운드 시작", "✏️ 문제 만들기 마감", "🎯 문제 풀기 마감"].forEach((t) => {
    const th = el("th", "", t);
    th.scope = "col";
    hr.append(th);
  });
  hh.append(hr);
  const hb = el("tbody");
  // 첫 주에 나오는 경기 요일마다 한 줄 (요일 순서대로)
  const seen = new Set();
  for (const r of rounds) {
    const wd = weekdayOf(r.start);
    if (seen.has(wd)) break;
    seen.add(wd);
    const tr = el("tr");
    tr.append(
      el("td", "", `${DAY_NAMES[wd]} 00:00`),
      el("td", "", `${DAY_NAMES[weekdayOf(r.makeLast)]} ${dl}`),
      el("td", "", `${DAY_NAMES[weekdayOf(r.last)]} ${dl}`)
    );
    hb.append(tr);
  }
  how.append(hh, hb);
  howWrap.append(how);
  howParent.append(howWrap);
  howParent.append(el("p", "hint",
    "만들기 마감 전까지 상대에게 낼 문제를 만들고(몇 번이든 고칠 수 있어요), 만들기 마감 바로 뒤부터 풀기 마감까지 상대 문제를 풀어요. [완성]을 눌러도 만들기 마감 전까지는 [다시 고치기]로 고칠 수 있어요."));

  // ③ 라운드별 표
  for (const r of rounds) {
    const tr = el("tr");
    const th = el("th", "", `${r.round}R`);
    th.scope = "row";
    const make = el("td");
    make.append(el("span", "range", rangeText(r.start, r.makeLast)), el("span", "deadline", `마감 ${fmtShort(r.makeLast)} ${dl}`));
    const solve = el("td");
    solve.append(el("span", "range", rangeText(r.solveFirst, r.last)), el("span", "deadline", `마감 ${fmtShort(r.last)} ${dl}`));
    tr.append(th, make, solve);
    tbodyEl.append(tr);
  }
}

// ===== 리그 만들기: 경기 요일 고르기 + 미리 보기 =====
const dayButtons = document.getElementById("dayButtons");
const dayMsg = document.getElementById("dayMsg");
const previewCount = document.getElementById("previewCount");
const createPreview = document.getElementById("createPreview");
const createPreviewList = document.getElementById("createPreviewList");
const selectedDays = new Set([0, 3]); // 기본값: 월·목

DAY_NAMES.forEach((name, i) => {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "day-btn";
  b.textContent = name;
  b.setAttribute("aria-pressed", selectedDays.has(i) ? "true" : "false");
  b.addEventListener("click", () => {
    if (selectedDays.has(i)) selectedDays.delete(i);
    else selectedDays.add(i);
    b.setAttribute("aria-pressed", selectedDays.has(i) ? "true" : "false");
    updateCreatePreview();
  });
  dayButtons.appendChild(b);
});

const deadlineTime = document.getElementById("deadlineTime");
const makeDaysSel = document.getElementById("makeDays");

// 문제 만들기 기간 고르기: 자동 + 1일 ~ (가장 짧은 라운드 - 1)일
function fillMakeDays(days) {
  const prev = makeDaysSel.value || "0";
  const max = days.length && !matchDaysError(days) ? shortestRoundDays(days) - 1 : 1;
  makeDaysSel.innerHTML = "";
  const auto = el("option", "", "자동 (라운드의 절반)");
  auto.value = "0";
  makeDaysSel.append(auto);
  for (let i = 1; i <= max; i++) {
    const o = el("option", "", `${i}일 (나머지는 풀기)`);
    o.value = String(i);
    makeDaysSel.append(o);
  }
  makeDaysSel.value = [...makeDaysSel.options].some((o) => o.value === prev) ? prev : "0";
}

function settingText(days, dl, makeDays) {
  const dayText = [...days].sort((a, b) => a - b).map((d) => DAY_NAMES[d]).join("·") || "요일 없음";
  return `📌 ${dayText} 경기 · 마감 ${dl} · 문제 만들기 ${makeDays ? makeDays + "일" : "자동(라운드의 절반)"}`;
}

function updateCreatePreview() {
  const days = [...selectedDays];
  const err = matchDaysError(days);
  dayMsg.textContent = err;
  fillMakeDays(days);
  document.getElementById("settingSummary").textContent =
    settingText(days, deadlineTime.value, parseInt(makeDaysSel.value, 10) || 0) +
    (getLeagueMode() === "short" && endDate.value ? ` · ${fmtShort(endDate.value)}까지 단기 리그` : "");
  if (err) {
    createPreview.innerHTML = "";
    createPreview.append(el("p", "preview-empty", "경기 요일을 바르게 고르면 일정이 보여요."));
    createPreviewList.innerHTML = "";
    return;
  }
  let n = parseInt(previewCount.value, 10);
  if (!(n >= 2)) n = 2;
  if (n > 30) n = 30;
  // 미리 보기: 내일 이후 가장 가까운 경기 요일부터 시작한다고 보고 계산
  // (실제 첫 경기 날짜는 [리그 시작] 때 오늘 또는 경기 요일 중에서 고른다)
  const first = matchDatesFrom(addDays(todayKST(), 1), days, 1)[0];
  renderPreview(createPreview, createPreviewList, first, days, n,
    parseInt(makeDaysSel.value, 10) || 0, deadlineTime.value, false,
    getLeagueMode() === "short" ? endDate.value : "");
}

// ===== 리그 기간 방식 (전체 / 시험 대비 단기) =====
const endDate = document.getElementById("endDate");
const endDateWrap = document.getElementById("endDateWrap");
function getLeagueMode() {
  const checked = document.querySelector('input[name="leagueMode"]:checked');
  return checked ? checked.value : "full";
}
function setLeagueMode(mode, end) {
  document.querySelectorAll('input[name="leagueMode"]').forEach((r) => (r.checked = r.value === mode));
  if (end !== undefined) endDate.value = end;
  syncLeagueMode();
}
function syncLeagueMode() {
  const short = getLeagueMode() === "short";
  endDateWrap.classList.toggle("hidden", !short);
  endDate.min = addDays(todayKST(), 1);
  if (short && !endDate.value) endDate.value = addDays(todayKST(), 21); // 기본: 3주 뒤
  showEndDateText();
  updateCreatePreview();
}
// 고른 날짜를 읽기 쉽게: "11월 14일(토) · 오늘부터 21일 뒤 (3주)"
function showEndDateText() {
  const box = document.getElementById("endDateText");
  const v = endDate.value;
  if (!v) {
    box.textContent = "📅 칸을 눌러 달력에서 날짜를 골라 주세요";
    box.className = "date-text";
    return;
  }
  const d = daysBetween(todayKST(), v);
  const weeks = d % 7 === 0 ? ` (${d / 7}주)` : "";
  const bad = v < endDate.min;
  box.textContent = bad ? "⚠️ 내일 이후 날짜로 골라 주세요" : `${fmtDate(v)} · 오늘부터 ${d}일 뒤${weeks}`;
  box.className = bad ? "date-text bad" : "date-text";
  document.querySelectorAll(".date-quick [data-weeks]").forEach((b) => {
    b.setAttribute("aria-pressed", v === addDays(todayKST(), b.dataset.weeks * 7) ? "true" : "false");
  });
}
// 칸 어디를 눌러도 달력 열기 (지원하지 않는 브라우저는 원래대로 동작)
function openEndDatePicker() {
  try {
    if (typeof endDate.showPicker === "function") endDate.showPicker();
  } catch (err) {
    /* 이미 열려 있거나 지원하지 않으면 무시 */
  }
}
document.querySelector(".date-field").addEventListener("click", openEndDatePicker);
endDate.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openEndDatePicker();
  }
});
document.querySelectorAll(".date-quick [data-weeks]").forEach((b) => b.addEventListener("click", () => {
  endDate.value = addDays(todayKST(), b.dataset.weeks * 7);
  showEndDateText();
  updateCreatePreview();
}));
document.querySelectorAll('input[name="leagueMode"]').forEach((r) => r.addEventListener("change", syncLeagueMode));
endDate.addEventListener("change", () => {
  showEndDateText();
  updateCreatePreview();
});
deadlineTime.addEventListener("change", updateCreatePreview);
makeDaysSel.addEventListener("change", updateCreatePreview);
previewCount.addEventListener("input", updateCreatePreview);
updateCreatePreview();

