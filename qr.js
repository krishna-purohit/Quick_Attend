
window.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    const splash = document.getElementById("splashScreen");
    const login = document.getElementById("loginScreen");

    splash.style.display = "none";
    login.classList.add("show");
  }, 3000); // Waits until animations complete
});

  const form = document.querySelector(".generate-form");
  const qrPreview = document.getElementById("qrPreview");
  const qrImage = document.getElementById("qrImage");
  const downloadBtn = document.getElementById("downloadBtn");

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    // Simulate QR generation — replace with real backend URL later
    const dummyQR = "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=QuickAttend";

    // Show QR
    qrImage.src = dummyQR;
    downloadBtn.href = dummyQR;
    qrPreview.style.display = "block";

    // Optionally hide form
    form.style.display = "none";
  });

