let chart;
let refreshTimer;
let speedAnimationTimer;
let currentSpeed = 0;
let targetSpeed = 0;
let speedInitialized = false;

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 1) =>
  value === null || value === undefined ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2400);
}

function renderMaintenance(tasks, mileage) {
  const list = $("maintenanceList");
  $("maintenanceCount").textContent = `${tasks.length} tasks`;
  list.replaceChildren();

  if (!tasks.length) {
    list.innerHTML = '<p class="muted">No maintenance tasks found.</p>';
    return;
  }

  tasks.forEach(task => {
    const distance = Number(task.due_mileage) - Number(mileage);
    const dueText = distance < 0
      ? `${Math.abs(distance).toLocaleString()} km overdue`
      : `${distance.toLocaleString()} km remaining`;
    const item = document.createElement("div");
    item.className = "maintenance-item";

    const icon = document.createElement("div");
    icon.className = "item-icon";
    icon.textContent = "▣";

    const body = document.createElement("div");
    body.className = "item-body";
    const title = document.createElement("b");
    title.textContent = task.task;
    const detail = document.createElement("small");
    detail.textContent = `Due at ${Number(task.due_mileage).toLocaleString()} km · ${task.status === "Completed" ? "Completed" : dueText}`;
    body.append(title, detail);

    const side = document.createElement("div");
    const status = document.createElement("span");
    status.className = "task-status" + (task.status === "Completed" ? " completed" : "");
    status.textContent = task.status === "Completed" ? "DONE" : (distance < 0 ? "OVERDUE" : "UPCOMING");
    side.appendChild(status);

    const btn = document.createElement("button");
    btn.className = "complete-btn";
    btn.textContent = task.status === "Completed" ? "Undo" : "Mark done";
    btn.title = task.status === "Completed"
      ? "Mark this task as not completed"
      : "Mark this task as completed";
    btn.addEventListener("click", async () => {
      try {
        const action = task.status === "Completed" ? "undo" : "complete";
        const response = await fetch(`/api/maintenance/${task.id}/${action}`, {
          method: "POST"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Could not update task");
        showToast(result.status === "Completed"
          ? "Maintenance task marked complete"
          : "Task marked as upcoming");
        // Reload dashboard data (read-only) to reflect status without changing telemetry.
        await loadDashboard();
      } catch (error) {
        showToast(error.message);
      }
    });
    side.appendChild(btn);

    item.append(icon, body, side);
    list.appendChild(item);
  });

  const upcoming = tasks.filter(t => t.status !== "Completed")
    .map(t => Number(t.due_mileage) - Number(mileage))
    .filter(d => d >= 0);
  $("nextService").textContent = upcoming.length
    ? `${Math.min(...upcoming).toLocaleString()} km left`
    : "Check schedule";
}

function renderAlerts(alerts) {
  const list = $("alertList");
  $("alertCount").textContent = alerts.length;
  list.replaceChildren();

  alerts.forEach(alert => {
    const item = document.createElement("div");
    item.className = "alert-item";
    const dot = document.createElement("span");
    dot.className = `severity ${alert.severity || "info"}`;
    const body = document.createElement("div");
    body.className = "item-body";
    const title = document.createElement("b");
    title.textContent = alert.title;
    const detail = document.createElement("small");
    detail.textContent = alert.detail;
    body.append(title, detail);
    item.append(dot, body);
    list.appendChild(item);
  });
}

function renderChart(history) {
  const labels = history.map((row, index) => {
    const date = new Date(row.timestamp);
    return Number.isNaN(date.getTime()) ? `#${index + 1}` :
      date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  });

  const data = {
    labels,
    datasets: [
      {
        label: "Coolant °C",
        data: history.map(r => r.coolant_temperature_c),
        borderColor: "#38bdf8",
        backgroundColor: "rgba(56,189,248,.12)",
        tension: .35,
        pointRadius: 2,
        yAxisID: "y"
      },
      {
        label: "Battery V",
        data: history.map(r => r.battery_voltage_v),
        borderColor: "#a78bfa",
        backgroundColor: "rgba(167,139,250,.1)",
        tension: .35,
        pointRadius: 2,
        yAxisID: "y1"
      }
    ]
  };

  if (chart) {
    chart.data = data;
    chart.update();
    return;
  }

  chart = new Chart($("trendChart"), {
    type: "line",
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#a9b8cc", boxWidth: 10, font: { size: 10 } } }
      },
      scales: {
        x: { ticks: { color: "#71839b", maxTicksLimit: 5 }, grid: { color: "rgba(120,145,170,.08)" } },
        y: { position: "left", ticks: { color: "#38bdf8" }, grid: { color: "rgba(120,145,170,.1)" } },
        y1: { position: "right", ticks: { color: "#a78bfa" }, grid: { drawOnChartArea: false } }
      }
    }
  });
}

async function loadDashboard() {
  const btn = $("refreshBtn");
  btn.disabled = true;
  try {
    const response = await fetch("/api/dashboard", { cache: "no-store" });
    if (!response.ok) throw new Error("Dashboard request failed");
    const data = await response.json();
    const r = data.reading;

    $("vehicleName").textContent = `${data.vehicle.make} · ${data.vehicle.model}`;
    $("vehicleMeta").textContent = `${data.vehicle.year} · ${data.vehicle.fuel_type} · ${Number(data.vehicle.mileage_km).toLocaleString()} km`;
    $("updatedAt").textContent = `Updated ${new Date(data.timestamp).toLocaleTimeString()}`;
    $("healthScore").textContent = data.health_score;
    $("healthBar").style.width = `${data.health_score}%`;
    $("mileage").textContent = Number(data.vehicle.mileage_km).toLocaleString();

    const engine = data.engine_condition;
    $("engineCondition").textContent = engine.label;
    $("engineNote").textContent = engine.available
      ? "Saved engine-condition model"
      : "Model unavailable: check model.pkl and Scaler.pkl";
    $("engineCondition").style.color =
      engine.class_id === 0 ? "#34d399" :
      engine.class_id === 2 ? "#fb7185" :
      engine.class_id === 1 ? "#fbbf24" : "#dce7f5";

    $("rpm").textContent = fmt(r.engine_rpm, 0);
    $("coolant").textContent = fmt(r.coolant_temperature_c);
    $("battery").textContent = fmt(r.battery_voltage_v, 2);
    // Speed is animated smoothly in the browser; other sensor values update
    // only when the dashboard snapshot refreshes.
    targetSpeed = Number(r.vehicle_speed_kmh) || 0;
    if (!speedInitialized) {
      currentSpeed = targetSpeed;
      speedInitialized = true;
      $("speed").textContent = fmt(currentSpeed, 0);
    }
    $("vibration").textContent = fmt(r.RMS_Vibration, 2);
    $("exhaust").textContent = fmt(r.Exhaust_Temperature);

    renderMaintenance(data.maintenance, data.vehicle.mileage_km);
    renderAlerts(data.alerts);
    renderChart(data.history);
  } catch (error) {
    showToast(`Could not load dashboard: ${error.message}`);
  } finally {
    btn.disabled = false;
  }
}


$("addMaintenanceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const task = $("newTaskName").value.trim();
  const due_mileage = Number($("newTaskMileage").value);

  try {
    const response = await fetch("/api/maintenance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, due_mileage })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not add task");
    $("addMaintenanceForm").reset();
    showToast("Maintenance task added");
    await loadDashboard();
  } catch (error) {
    showToast(error.message);
  }
});

async function updateReadingsManually() {
  const btn = $("refreshBtn");
  btn.disabled = true;
  try {
    const response = await fetch("/api/simulate", { method: "POST" });
    if (!response.ok) throw new Error("Could not generate new simulated readings");
    await loadDashboard();
    showToast("New simulated readings generated");
  } catch (error) {
    showToast(error.message);
  } finally {
    btn.disabled = false;
  }
}

$("refreshBtn").addEventListener("click", updateReadingsManually);
loadDashboard();

// No automatic refresh: readings change only when the user taps "Update readings".

// Animate only the speed display smoothly between the last and new snapshots.
speedAnimationTimer = setInterval(() => {
  if (!speedInitialized) return;
  const difference = targetSpeed - currentSpeed;
  if (Math.abs(difference) < 0.15) {
    currentSpeed = targetSpeed;
  } else {
    currentSpeed += difference * 0.12;
  }
  $("speed").textContent = fmt(currentSpeed, 0);
}, 250);
