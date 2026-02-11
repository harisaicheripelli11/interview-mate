window.onload = async () => {
  const res = await fetch("/performance-data");
  const data = await res.json();

  document.getElementById("totalInterviews").innerText =
    data.stats.total || 0;

  document.getElementById("avgConfidence").innerText =
    data.stats.avg_confidence || 0;

  document.getElementById("avgClarity").innerText =
    data.stats.avg_clarity || 0;

  const list = document.getElementById("recentFeedback");
  list.innerHTML = "";

  data.recent.forEach(item => {
    const li = document.createElement("li");
    li.innerHTML = `
      <b>Confidence:</b> ${item.confidence}/10 |
      <b>Clarity:</b> ${item.clarity}/10
      <br>
      <i>${item.comment}</i>
    `;
    list.appendChild(li);
  });
};
