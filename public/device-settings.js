const form = document.getElementById("key-form");
const input = document.getElementById("key");
const message = document.getElementById("message");
const edit = document.getElementById("edit");

function showSaved() {
  form.hidden = true;
  input.value = "";
  edit.hidden = false;
  message.textContent = "Đã lưu key trên thiết bị này.";
}

try {
  if (localStorage.getItem("gemini-api-key")) showSaved();
} catch {
  message.textContent = "Trình duyệt đang chặn lưu dữ liệu. Hãy cho phép để lưu key.";
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const key = input.value.trim();
  if (!key) {
    message.textContent = "Hãy nhập API key.";
    return;
  }
  try {
    localStorage.setItem("gemini-api-key", key);
    showSaved();
  } catch {
    message.textContent = "Không lưu được key. Hãy cho phép trình duyệt lưu dữ liệu rồi thử lại.";
  }
});

edit.addEventListener("click", () => {
  form.hidden = false;
  edit.hidden = true;
  message.textContent = "";
  input.focus();
});
