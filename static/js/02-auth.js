// 02-auth.js · 로그인·회원가입

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
  const { ok, data } = await postJSON("/register", body, registerForm.querySelector("button[type=submit]"));
  if (ok) {
    // 서버가 가입과 동시에 로그인해 준다 → 바로 다음 화면으로
    registerForm.reset();
    showLoggedIn(data.nickname);
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
  const { ok, data } = await postJSON("/login", body, loginForm.querySelector("button[type=submit]"));
  if (ok) {
    loginForm.reset();
    showLoggedIn(data.nickname);
  } else {
    loginMsg.className = "msg err";
    loginMsg.textContent = data.error || "로그인에 실패했어요.";
  }
});

