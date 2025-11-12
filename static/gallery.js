// gallery.js — buat preview gambar fullscreen

const modal = document.getElementById("imgModal");
const modalImg = document.getElementById("modalImg");

document.querySelectorAll(".g-card img").forEach(img => {
  img.addEventListener("click", () => {
    modal.classList.remove("hidden");
    modalImg.src = img.src;
  });
});

// klik di mana aja di luar gambar untuk nutup
modal.addEventListener("click", (e) => {
  if (e.target === modal || e.target === modalImg) {
    modal.classList.add("hidden");
    modalImg.src = "";
  }
});

// tombol ESC juga bisa nutup
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    modal.classList.add("hidden");
    modalImg.src = "";
  }
});
