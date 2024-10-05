document.addEventListener("DOMContentLoaded", function () {
  // Smooth scrolling for navigation links
  const navLinks = document.querySelectorAll("nav a");
  navLinks.forEach((link) => {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      const targetId = this.getAttribute("href").substring(1);
      const targetElement = document.getElementById(targetId);
      targetElement.scrollIntoView({ behavior: "smooth" });
    });
  });

  // Mobile navigation toggle
  const navToggle = document.querySelector(".nav-toggle");
  const navMenu = document.querySelector("nav ul");

  navToggle.addEventListener("click", function () {
    navMenu.classList.toggle("open");
  });

  // Appointment form submission
  const appointmentForm = document.getElementById("appointment-form");
  if (appointmentForm) {
    appointmentForm.addEventListener("submit", function (e) {
      e.preventDefault();
      // Handle form submission logic
      const formData = new FormData(this);
      const data = {};
      formData.forEach((value, key) => (data[key] = value));

      // Replace with actual form submission logic
      console.log("Form submitted:", data);

      // Display success message or redirect
      alert("Appointment request submitted successfully!");
      this.reset();
    });
  }
});
