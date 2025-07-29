window.addEventListener("DOMContentLoaded", () => {
  const popup = document.getElementById("errorPopup");
  if (popup) {
    popup.classList.remove("hidden");
    setTimeout(() => {
      popup.classList.add("hidden");
    }, 3000);
  }
});
