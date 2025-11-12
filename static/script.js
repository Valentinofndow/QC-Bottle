// static/script.js — DASHBOARD UTAMA
// update data GOOD/DEFECT di main.html

const el = (id) => document.getElementById(id);
let pollingActive = true;
document.addEventListener("visibilitychange", () => (pollingActive = !document.hidden));
let ctl = { stats: null };  

// fungsi bantu
function setText(id, v) {
  const n = el(id);
  if (n) n.textContent = v;
}

// fungsi ambil data /stats
async function updateStats() {
  if (!pollingActive) return;
  try {
    if (ctl.stats) ctl.stats.abort();
    ctl.stats = new AbortController();

    // Use fast in-memory live counts for UI responsiveness
    const res = await fetch(`/live_counts?t=${Date.now()}`, { signal: ctl.stats.signal });
    if (!res.ok) return;

    const d = await res.json();
    const good = d.good ?? 0;
    const defect = d.defect ?? 0;

    // update angka ke elemen di main.html
    setText("good", good);
    setText("defect", defect);

  } catch (err) {
    console.warn("updateStats error:", err);
  } finally {
    ctl.stats = null;
  }
}

// refresh otomatis tiap 2 detik
updateStats();
setInterval(updateStats, 2000);

// tombol manual refresh (opsional)
const refreshBtn = el("refreshStats");
if (refreshBtn) refreshBtn.addEventListener("click", updateStats);


// === CAMERA SWITCH + STATUS HANDLER ===
const camButtons = document.querySelectorAll(".cam-btn");
const camLabel = document.getElementById("camLabel");
const streamStatus = document.getElementById("streamStatus");
const video = document.getElementById("video");

// ubah kamera aktif
async function switchCamera(index) {
  try {
    const res = await fetch(`/set_cam?i=${index}`, { method: "POST" });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      streamStatus.textContent = data.msg || "Disconnected";
      streamStatus.style.color = "#ff4444";
      return;
    }

    camLabel.textContent = `CAM ${index + 1}`;
    streamStatus.textContent = data.msg || "Connected";
    streamStatus.style.color = "#7CFC00"; // hijau terang
    video.src = "/video_feed?t=" + Date.now(); // refresh stream
  } catch (err) {
    streamStatus.textContent = "Server unreachable";
    streamStatus.style.color = "#ff4444";
  }
}

// update tombol aktif
function setActiveButton(index) {
  camButtons.forEach(btn => btn.classList.remove("active"));
  camButtons[index].classList.add("active");
}

// event listener tombol kamera
camButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    const index = parseInt(btn.dataset.cam);
    setActiveButton(index);
    switchCamera(index);
  });
});

// === STATUS MONITORING ===
async function checkCameraStatus() {
  try {
    const res = await fetch("/camera_status?t=" + Date.now());
    const data = await res.json();
    if (data.ok) {
      streamStatus.textContent = data.msg;
      streamStatus.style.color = "#7CFC00";
    } else {
      streamStatus.textContent = data.msg || "Disconnected";
      streamStatus.style.color = "#ff4444";
    }
  } catch {
    streamStatus.textContent = "Koneksi server gagal";
    streamStatus.style.color = "#ff4444";
  }
}


// === MODAL RESET HANDLER (2 STEP: PASSWORD + KONFIRMASI) ===
document.addEventListener("DOMContentLoaded", () => {
  const resetBtn = document.getElementById("resetDb");
  const resetModal = document.getElementById("resetModal");
  const confirmModal = document.getElementById("confirmModal");

  const cancelResetBtn = document.getElementById("cancelReset");
  const confirmResetBtn = document.getElementById("confirmReset");
  const resetPass = document.getElementById("resetPass");
  const modalMsg = document.getElementById("modalMsg");

  const cancelConfirmBtn = document.getElementById("cancelConfirm");
  const confirmDeleteBtn = document.getElementById("confirmDelete");

  // variabel global buat simpen password yang udah divalidasi
  let validPass = "";

  // buka modal password pertama
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      resetModal.classList.remove("hidden");
      resetPass.value = "";
      modalMsg.textContent = "";
      resetPass.focus();
    });
  }

  // tutup modal password
  if (cancelResetBtn) {
    cancelResetBtn.addEventListener("click", () => {
      resetModal.classList.add("hidden");
    });
  }

  // enter = klik tombol konfirmasi
  if (resetPass) {
    resetPass.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        confirmResetBtn.click();
      }
    });
  }

  // tahap 1: cek password admin
  if (confirmResetBtn) {
    confirmResetBtn.addEventListener("click", async () => {
      const pass = resetPass.value.trim();
      if (!pass) {
        modalMsg.textContent = "Password tidak boleh kosong.";
        modalMsg.style.color = "#ff5555";
        return;
      }

      try {
        const res = await fetch("/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: pass, checkOnly: true })
        });

        const data = await res.json();

        if (data.ok) {
          // simpan password yang valid
          validPass = pass;
          resetModal.classList.add("hidden");
          confirmModal.classList.remove("hidden");
        } else {
          modalMsg.textContent = "Password salah.";
          modalMsg.style.color = "#ff5555";
        }
      } catch (err) {
        modalMsg.textContent = "Server tidak merespons.";
        modalMsg.style.color = "#ff5555";
      }
    });
  }

  // batal konfirmasi tahap 2
  if (cancelConfirmBtn) {
    cancelConfirmBtn.addEventListener("click", () => {
      confirmModal.classList.add("hidden");
    });
  }

  // tahap 2: eksekusi penghapusan final
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", async () => {
      console.log("🟡 Tombol Yakin ditekan — kirim request reset...");
      try {
        const res = await fetch("/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: validPass, checkOnly: false })
        });

        const data = await res.json();

        if (data.ok) {
          console.log("✅ Reset berhasil");
          confirmModal.classList.add("hidden");
          showToast("✅ Semua data berhasil dihapus!", "success");
          setTimeout(() => location.reload(), 1500);
        } else {
          console.warn("❌ Reset gagal:", data);
          showToast("❌ Gagal menghapus data", "error");
        }
      } catch (err) {
        console.error("⚠️ Error saat reset:", err);
        showToast("⚠️ Server error", "error");
      }
    });
  }

  // cek status kamera tiap 2 detik
  setInterval(checkCameraStatus, 2000);
  checkCameraStatus();
});
