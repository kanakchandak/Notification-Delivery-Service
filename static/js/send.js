
const channelInput = document.getElementById("channel");
const recipientInput = document.getElementById("recipient");
const subjectArea = document.getElementById("subject-area");
const subjectInput = document.getElementById("subject");
const bodyInput = document.getElementById("body");
const sendForm = document.getElementById("send-form");

// Change form when channel changes
channelInput.addEventListener("change", function () {
    if (channelInput.value === "sms") {
        subjectArea.style.display = "none";
        recipientInput.placeholder = "+919812345678";
        document.getElementById("recipient-label").textContent =
            "Phone number";
        document.getElementById("recipient-help").textContent =
            "Use international format, for example +919812345678.";
        bodyInput.maxLength = 480;
    } else {
        subjectArea.style.display = "block";
        recipientInput.placeholder = "name@shop.example";
        document.getElementById("recipient-label").textContent =
            "Email address";
        document.getElementById("recipient-help").textContent =
            "Enter a valid email address.";
        bodyInput.maxLength = 2000;
    }

    updateCount();
});

// Character counter
function updateCount() {
    document.getElementById("character-count").textContent =
        bodyInput.value.length;
}

bodyInput.addEventListener("input", updateCount);

// Quick fill good example
document.getElementById("good-example").addEventListener("click", function () {
    channelInput.value = "email";
    channelInput.dispatchEvent(new Event("change"));

    recipientInput.value = "ritu@shop.example";
    subjectInput.value = "Your order is confirmed";
    bodyInput.value = "Hello! Your order has been confirmed.";
    updateCount();
});

// Quick fill bounce example
document.getElementById("bounce-example").addEventListener("click", function () {
    channelInput.value = "email";
    channelInput.dispatchEvent(new Event("change"));

    recipientInput.value = "asha@bounce.example";
    subjectInput.value = "Bounce test";
    bodyInput.value = "This message is used to test a bounced email.";
    updateCount();
});

// Submit message
sendForm.addEventListener("submit", async function (event) {
    event.preventDefault();

    const channel = channelInput.value;
    const recipient = recipientInput.value.trim();
    const subject = subjectInput.value.trim();
    const body = bodyInput.value.trim();

    if (!recipient || !body) {
        showMessage("Please fill in all required fields.", "danger");
        return;
    }

    if (channel === "email" && !subject) {
        showMessage("Email subject is required.", "danger");
        return;
    }

    const message = {
        channel: channel,
        category: document.getElementById("category").value,
        to: recipient,
        subject: channel === "email" ? subject : null,
        body: body
    };

    const button = document.getElementById("send-button");
    button.disabled = true;
    button.textContent = "Sending...";

    try {
        const result = await sendData("/api/messages", "POST", message);

        showMessage(
            "Accepted as #" + result.id + ", pending.",
            "success"
        );

        sendForm.reset();
        channelInput.dispatchEvent(new Event("change"));
        updateCount();

    } catch (error) {
        showMessage(error.message, "danger");
    }

    button.disabled = false;
    button.textContent = "Send message";
});
