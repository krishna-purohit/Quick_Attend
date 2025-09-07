// Login function
async function loginUser(event) {
  event.preventDefault(); // prevent page reload
  const uid = document.getElementById("uid").value.trim();
  const pass = document.getElementById("upass").value.trim();

  if (!uid || !pass) {
    alert("Please enter both ID and Password!");
    return;
  }

  try {
    let url = "";
    let body = {};

    if (uid.startsWith("T")) {
      // Teacher login
      url = "http://127.0.0.1:5000/api/teacher/login";
      body = { username: uid, password: pass };
    } else {
      // Student login
      url = "http://127.0.0.1:5000/api/student/login";
      body = { roll_number: uid, password: pass };
    }

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    
   const data = await res.json();
console.log("Login response mila:", data);   // ✅ yaha check karo

    if (res.ok && data.ok) {
      // Save session info
      sessionStorage.setItem("user", JSON.stringify(data));

      if (uid.startsWith("T")) {
        window.location.href = "teacher.html";
      } else {
        window.location.href = "student.html";
      }
    } else {
      alert(data.message || "Invalid login. Try again!");
    }
  } catch (error) {
    console.error("Error:", error);
    alert("Server not reachable. Start Flask backend!");
  }

}
//animation code
  window.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    const splash = document.getElementById("splashScreen");
    const login = document.getElementById("loginScreen");

    splash.style.display = "none";
    login.classList.add("show");
  }, 3000); 
});