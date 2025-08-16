
window.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    const splash = document.getElementById("splashScreen");
    const login = document.getElementById("loginScreen");

    splash.style.display = "none";
    login.classList.add("show");
  }, 3000); 
});
