// Class League 서비스 워커 (PWA 설치·오프라인 안내용)
// - 화면 파일(HTML·CSS·JS·아이콘)만 저장한다.
// - 로그인·경기·문제 같은 API 응답은 절대 저장하지 않는다 (같은 기기의 다른 사람에게 남지 않게).
const CACHE = "class-league-v4";
const SHELL = [
  "/",
  "/static/css/01-base.css",
  "/static/css/02-league.css",
  "/static/css/03-questions.css",
  "/static/css/04-landing.css",
  "/static/css/05-match.css",
  "/static/css/06-modal-notes.css",
  "/static/css/07-schedule.css",
  "/static/css/08-admin.css",
  "/static/css/09-layout.css",
  "/static/css/10-screens.css",
  "/static/css/11-extras.css",
  "/static/js/01-core.js",
  "/static/js/02-auth.js",
  "/static/js/03-league.js",
  "/static/js/04-standings.js",
  "/static/js/05-schedule.js",
  "/static/js/06-admin.js",
  "/static/js/07-create.js",
  "/static/js/08-history.js",
  "/static/js/09-match.js",
  "/static/js/10-reports.js",
  "/static/js/11-notes.js",
  "/static/manifest.webmanifest",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/icon-maskable-512.png",
  "/static/apple-touch-icon.png",
  "/static/offline.html",
  "/static/offline.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  // 예전 버전 캐시 지우기
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  // 다른 사이트 요청, GET이 아닌 요청(저장·제출 등)은 건드리지 않는다
  if (url.origin !== self.location.origin || req.method !== "GET") return;

  // 화면(HTML): 항상 새로 받고, 인터넷이 끊겼을 때만 저장한 화면/오프라인 안내
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("/", copy));
          return res;
        })
        .catch(() => caches.match("/static/offline.html"))
    );
    return;
  }

  // 정적 파일: 새로 받아 보고, 실패하면 저장한 것
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
  }
  // 그 밖(API)은 서비스 워커가 관여하지 않는다 → 항상 서버에서 최신 데이터
});
