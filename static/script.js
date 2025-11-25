// static/script.js — DASHBOARD UTAMA (dengan lamp virtual)

// helper
const el = (id) => document.getElementById(id);
let pollingActive = true;
document.addEventListener("visibilitychange", () => (pollingActive = !document.hidden));

// controllers untuk AbortController
let ctl = { stats: null, lamp: null };

// util: set text safely
function setText(id, v) {
  const n = el(id);
  if (n) n.textContent = v;
}

// minimal toast (fungsi sederhana, pakai kalau mau notifikasi)
function showToast(msg, type = "info") {
  const rootId = "__toast_root__";
  let root = document.getElementById(rootId);
  if (!root) {
    root = document.createElement("div");
    root.id = rootId;
    root.style.position = "fixed";
    root.style.right = "18px";
    root.style.bottom = "18px";
    root.style.zIndex = 99999;
    document.body.appendChild(root);
  }
  const t = document.createElement("div");
  t.textContent = msg;
  t.style.marginTop = "8px";
  t.style.padding = "10px 14px";
  t.style.borderRadius = "8px";
  t.style.boxShadow = "0 6px 18px rgba(0,0,0,0.4)";
  t.style.color = "#fff";
  t.style.fontSize = "13px";
  t.style.opacity = "0";
  t.style.transition = "opacity .18s ease, transform .18s ease";
  if (type === "success") { t.style.background = "#2e7d32"; }
  else if (type === "error") { t.style.background = "#c62828"; }
  else { t.style.background = "#333"; }

  root.appendChild(t);
  // show
  requestAnimationFrame(() => {
    t.style.opacity = "1";
    t.style.transform = "translateY(-4px)";
  });
  // auto-remove
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateY(0)";
    setTimeout(() => root.removeChild(t), 220);
  }, 2200);
}

// -------------------------------
// STATS (GOOD / DEFECT)
// -------------------------------
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

    setText("good", good);
    setText("defect", defect);
  } catch (err) {
    // silent fail-ish — jangan spam console
    // console.warn("updateStats error:", err);
  } finally {
    ctl.stats = null;
  }
}

// -------------------------------
// LAMP POLLING (virtual lamp)
// -------------------------------
async function pollLampState() {
  if (!pollingActive) return;
  try {
    if (ctl.lamp) ctl.lamp.abort();
    ctl.lamp = new AbortController();

    const res = await fetch(`/lamp_state?t=${Date.now()}`, { signal: ctl.lamp.signal });
    if (!res.ok) return;
    const d = await res.json();
    const lampOn = Boolean(d.lamp);
    const bulb = el("lampBulb");
    if (bulb) {
      bulb.classList.toggle("on", lampOn);
      // optional: update aria/state text
      bulb.setAttribute("aria-pressed", lampOn ? "true" : "false");
    }
  } catch (err) {
    // ignore transient errors
  } finally {
    ctl.lamp = null;
  }
}

// -------------------------------
// CAMERA SWITCH + STATUS
// -------------------------------
const camButtons = document.querySelectorAll(".cam-btn");
const camLabel = el("camLabel");
const streamStatus = el("streamStatus");
const video = el("video");

// ubah kamera aktif
async function switchCamera(index) {
  try {
    const res = await fetch(`/set_cam?i=${index}`, { method: "POST" });
    const data = await res.json();

    if (!res.ok || !data.ok) {
      if (streamStatus) {
        streamStatus.textContent = data.msg || "Disconnected";
        streamStatus.style.color = "#ff4444";
      }
      return;
    }

    if (camLabel) camLabel.textContent = `CAM ${index + 1}`;
    if (streamStatus) {
      streamStatus.textContent = data.msg || "Connected";
      streamStatus.style.color = "#7CFC00"; // hijau terang
    }
    if (video) video.src = "/video_feed?t=" + Date.now(); // refresh stream
  } catch (err) {
    if (streamStatus) {
      streamStatus.textContent = "Server unreachable";
      streamStatus.style.color = "#ff4444";
    }
  }
}

function setActiveButton(index) {
  if (!camButtons || camButtons.length === 0) return;
  camButtons.forEach(btn => btn.classList.remove("active"));
  const btn = camButtons[index];
  if (btn) btn.classList.add("active");
}

if (camButtons && camButtons.length) {
  camButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const index = parseInt(btn.dataset.cam);
      setActiveButton(index);
      switchCamera(index);
    });
  });
}

// -------------------------------
// STATUS MONITORING
// -------------------------------
async function checkCameraStatus() {
  try {
    const res = await fetch("/camera_status?t=" + Date.now());
    const data = await res.json();
    if (data.ok) {
      if (streamStatus) {
        streamStatus.textContent = data.msg;
        streamStatus.style.color = "#7CFC00";
      }
    } else {
      if (streamStatus) {
        streamStatus.textContent = data.msg || "Disconnected";
        streamStatus.style.color = "#ff4444";
      }
    }
  } catch {
    if (streamStatus) {
      streamStatus.textContent = "Koneksi server gagal";
      streamStatus.style.color = "#ff4444";
    }
  }
}

// -------------------------------
// MODAL RESET HANDLER (2 STEP)
// -------------------------------
document.addEventListener("DOMContentLoaded", () => {
  const resetBtn = el("resetDb");
  const resetModal = el("resetModal");
  const confirmModal = el("confirmModal");

  const cancelResetBtn = el("cancelReset");
  const confirmResetBtn = el("confirmReset");
  const resetPass = el("resetPass");
  const modalMsg = el("modalMsg");

  const cancelConfirmBtn = el("cancelConfirm");
  const confirmDeleteBtn = el("confirmDelete");

  let validPass = "";

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      if (resetModal) {
        resetModal.classList.remove("hidden");
        if (resetPass) resetPass.value = "";
        if (modalMsg) modalMsg.textContent = "";
        if (resetPass) resetPass.focus();
      }
    });
  }

  if (cancelResetBtn) {
    cancelResetBtn.addEventListener("click", () => {
      if (resetModal) resetModal.classList.add("hidden");
    });
  }

  if (resetPass) {
    resetPass.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (confirmResetBtn) confirmResetBtn.click();
      }
    });
  }

  if (confirmResetBtn) {
    confirmResetBtn.addEventListener("click", async () => {
      const pass = (resetPass && resetPass.value.trim()) || "";
      if (!pass) {
        if (modalMsg) {
          modalMsg.textContent = "Password tidak boleh kosong.";
          modalMsg.style.color = "#ff5555";
        }
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
          validPass = pass;
          if (resetModal) resetModal.classList.add("hidden");
          if (confirmModal) confirmModal.classList.remove("hidden");
        } else {
          if (modalMsg) {
            modalMsg.textContent = "Password salah.";
            modalMsg.style.color = "#ff5555";
          }
        }
      } catch (err) {
        if (modalMsg) {
          modalMsg.textContent = "Server tidak merespons.";
          modalMsg.style.color = "#ff5555";
        }
      }
    });
  }

  if (cancelConfirmBtn) {
    cancelConfirmBtn.addEventListener("click", () => {
      if (confirmModal) confirmModal.classList.add("hidden");
    });
  }

  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", async () => {
      try {
        const res = await fetch("/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: validPass, checkOnly: false })
        });
        const data = await res.json();

        if (data.ok) {
          if (confirmModal) confirmModal.classList.add("hidden");
          showToast("✅ Semua data berhasil dihapus!", "success");
          setTimeout(() => location.reload(), 900);
        } else {
          showToast("❌ Gagal menghapus data", "error");
        }
      } catch (err) {
        showToast("⚠️ Server error", "error");
      }
    });
  }

  // initial UI setup
  setActiveButton(0);
  // start polling (safe after DOMContentLoaded)
  updateStats();
  pollLampState();
  checkCameraStatus();

  // intervals
  setInterval(updateStats, 2000);   // stats every 2s
  setInterval(pollLampState, 500);  // lamp check every 0.5s (fast visual feedback)
  setInterval(checkCameraStatus, 2000);
});
