// Mobile navigation
function toggleMenu() {
    const nav = document.getElementById("navLinks");

    if (nav) {
        nav.classList.toggle("active");
    }
}


// Automatically hide flash messages
setTimeout(() => {

    const messages = document.querySelectorAll(".flash-message");

    messages.forEach(message => {

        message.style.opacity = "0";

        setTimeout(() => {
            message.remove();
        }, 300);

    });

}, 5000);
// Show / hide password
function togglePassword(inputId, button) {

    const input = document.getElementById(inputId);

    if (!input) {
        return;
    }

    if (input.type === "password") {

        input.type = "text";

        button.innerHTML =
            '<i class="fa-regular fa-eye-slash"></i>';

    } else {

        input.type = "password";

        button.innerHTML =
            '<i class="fa-regular fa-eye"></i>';
    }
}