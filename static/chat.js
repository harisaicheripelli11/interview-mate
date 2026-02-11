/*************************************************
 * INTERVIEW MATE – CHAT + VOICE (FINAL – MODE LOCKED & CLEAN)
 *************************************************/

const input = document.getElementById("userInput");
const chatBox = document.getElementById("chat-box");
const micBtn = document.getElementById("micBtn");
const sendBtn = document.getElementById("sendBtn");

/* ========= MODE (FROM URL) ========= */
const params = new URLSearchParams(window.location.search);
const MODE = params.get("mode"); // "chat" | "voice"
const isVoiceMode = MODE === "voice";

/* ========= STATE ========= */
let recognition = null;
let listening = false;
let lastQuestionSpoken = "";
let userInteracted = false;
let voicesLoaded = false;

/* ========= MODE LOCK ========= */
if (isVoiceMode) {
  input.disabled = true;
  input.placeholder = "🎤 Voice input only";
  sendBtn.disabled = true;
} else {
  micBtn.style.display = "none";
}

/* ========= USER INTERACTION UNLOCK ========= */
document.addEventListener(
  "click",
  () => (userInteracted = true),
  { once: true }
);

/* ========= VOICE LOADER ========= */
speechSynthesis.onvoiceschanged = () => {
  voicesLoaded = true;
};

/* ========= FEMALE VOICE ========= */
function getFemaleVoice() {
  return (
    speechSynthesis
      .getVoices()
      .find(v =>
        /samantha|zira|female|woman|english india|google uk/i.test(v.name)
      ) || speechSynthesis.getVoices()[0]
  );
}

/* ========= SPEAK ========= */
function speak(text) {
  if (!isVoiceMode || !userInteracted || !window.speechSynthesis) return;

  if (!voicesLoaded) {
    setTimeout(() => speak(text), 300);
    return;
  }

  if (recognition && listening) recognition.stop();
  speechSynthesis.cancel();

  const utter = new SpeechSynthesisUtterance(text);
  utter.voice = getFemaleVoice();
  utter.lang = "en-IN";
  utter.rate = 1;
  utter.pitch = 1.1;

  utter.onend = () => {
    setTimeout(() => {
      if (recognition && !listening) recognition.start();
    }, 400);
  };

  speechSynthesis.speak(utter);
}

/* ========= SPEECH RECOGNITION ========= */
if (
  isVoiceMode &&
  ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)
) {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  recognition = new SpeechRecognition();
  recognition.lang = "en-IN";
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
  listening = true;

  micBtn.innerText = "🎙️ Listening...";
  micBtn.classList.add("active");
  micBtn.classList.add("listening");   // ✅ ADD THIS

  input.disabled = true;               // ✅ ADD THIS
  input.placeholder = "🎤 Listening…"; // ✅ ADD THIS
};


  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript.trim();
    input.value = transcript;

    if (transcript.toLowerCase().includes("repeat") && lastQuestionSpoken) {
      speak("Repeating the question. " + lastQuestionSpoken);
      return;
    }

    sendMessage();
  };

  recognition.onend = () => {
  listening = false;

  micBtn.innerText = "🎤";
  micBtn.classList.remove("active");
  micBtn.classList.remove("listening"); // ✅ ADD THIS

  input.disabled = false;              // ✅ ADD THIS
  input.placeholder = "Type your answer…"; // ✅ ADD THIS
};

}

/* ========= MIC BUTTON ========= */
if (isVoiceMode) {
  micBtn.addEventListener("click", () => {
    if (!recognition || speechSynthesis.speaking) return;
    userInteracted = true;
    listening ? recognition.stop() : recognition.start();
  });
}

/* ========= SEND BUTTON (CHAT ONLY) ========= */
sendBtn.addEventListener("click", () => {
  if (!isVoiceMode) sendMessage();
});

/* ========= KEYBOARD (CHAT ONLY) ========= */
input.addEventListener("keydown", (e) => {
  if (isVoiceMode) {
    e.preventDefault();
    return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    sendMessage();
  }
});

/* ========= SINGLE AI RENDER ========= */

function renderAI(aiBubble, data) {
  // FIRST QUESTION (no feedback)
  if (data.confidence === null) {
    aiBubble.innerHTML = `
      <div class="next-question">
        <b>Interview Question</b>
        <p>${data.next_question}</p>
      </div>
    `;
    return;
  }

  // NORMAL FLOW
  const { confidence, clarity, answer_review, next_question } = data;

  aiBubble.innerHTML = `
    <div class="feedback-box">

      <div class="score">
        <div class="score-label">
          <span>Confidence</span>
          <span>${confidence}/10</span>
        </div>
        <div class="score-bar">
          <div class="score-fill confidence" style="width:${confidence * 10}%"></div>
        </div>
      </div>

      <div class="score">
        <div class="score-label">
          <span>Clarity</span>
          <span>${clarity}/10</span>
        </div>
        <div class="score-bar">
          <div class="score-fill clarity" style="width:${clarity * 10}%"></div>
        </div>
      </div>

      <p class="review">📝 ${answer_review}</p>
    </div>

    <div class="next-question">
      <b>Next Question</b>
      <p>${next_question}</p>
    </div>
  `;
}



/* ========= SEND MESSAGE ========= */
async function sendMessage() {
  const message = input.value.trim();
  if (!message) return;

  const userBubble = document.createElement("div");
  userBubble.className = "chat-bubble user";
  userBubble.innerText = message;
  chatBox.appendChild(userBubble);

  input.value = "";

  const aiBubble = document.createElement("div");
  aiBubble.className = "chat-bubble ai";
  aiBubble.innerText = "🤖 Thinking...";
  chatBox.appendChild(aiBubble);

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });

    const data = await res.json();

    if (data.redirect) {
      speechSynthesis.cancel();
      recognition && recognition.stop();
      window.location.href = data.redirect;
      return;
    }

    lastQuestionSpoken = data.next_question || "";
    renderAI(aiBubble, data);

    if (isVoiceMode && data.next_question) {
      speak(
        `Feedback. Confidence ${data.confidence}. Clarity ${data.clarity}. ${data.answer_review}. Next question. ${data.next_question}`
      );
    }
  } catch (err) {
    console.error(err);
    aiBubble.innerText = "⚠️ AI error. Try again.";
  }
}
/* ========= AUTO START INTERVIEW ========= */
window.addEventListener("load", async () => {
  const aiBubble = document.createElement("div");
  aiBubble.className = "chat-bubble ai";
  aiBubble.innerText = "🤖 Preparing interview...";
  chatBox.appendChild(aiBubble);

  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "START" })
  });

  const data = await res.json();
  lastQuestionSpoken = data.next_question || "";

  renderAI(aiBubble, data);

  if (isVoiceMode && data.next_question) {
    speak("Let us begin. " + data.next_question);
  }
});
