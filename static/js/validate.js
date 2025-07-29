document.addEventListener("DOMContentLoaded", function () {
  const form = document.querySelector("form");
  const name = document.getElementById("name");
  const email = document.getElementById("email");
  const password = document.getElementById("password");
  const confirmPassword = document.getElementById("confirm_password");

  form.addEventListener("submit", function (e) {
    // Trim whitespace
    const nameVal = name.value.trim();
    const emailVal = email.value.trim();
    const passVal = password.value;
    const confirmVal = confirmPassword.value;

    // Basic checks
    if (!nameVal || !emailVal || !passVal || !confirmVal) {
      alert("All fields are required.");
      e.preventDefault();
      return;
    }

    // Email format check
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(emailVal)) {
      alert("Enter a valid email address.");
      e.preventDefault();
      return;
    }

    // Password length
    if (passVal.length < 6) {
      alert("Password must be at least 6 characters.");
      e.preventDefault();
      return;
    }
s
    // Password match
    if (passVal !== confirmVal) {
      alert("Passwords do not match.");
      e.preventDefault();
      return;
    }

    // You can add more validations (like symbols, numbers etc.) here if needed
  });
});
