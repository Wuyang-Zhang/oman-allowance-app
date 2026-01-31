let backend = null;
let state = null;
let t = (k) => k;

const statusMap = {
  "In-study": "status.in_study",
  "Graduated": "status.graduated",
  "Withdrawn": "status.withdrawn"
};

const degreeMap = {
  "Bachelor": "degree.bachelor",
  "Master": "degree.master",
  "PhD": "degree.phd"
};

const allowanceMap = {
  "Living": "allowance.living",
  "Study": "allowance.study",
  "ExcessBaggage": "allowance.baggage"
};

function labelForStatus(value) {
  return t(statusMap[value] || value);
}

function labelForDegree(value) {
  return t(degreeMap[value] || value);
}

function labelForAllowance(value) {
  return t(allowanceMap[value] || value);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setPlaceholder(id, value) {
  const el = document.getElementById(id);
  if (el) el.placeholder = value;
}

function setDateInputLocked(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.setAttribute("inputmode", "none");
  el.addEventListener("keydown", (e) => e.preventDefault());
  el.addEventListener("keypress", (e) => e.preventDefault());
  el.addEventListener("paste", (e) => e.preventDefault());
  el.addEventListener("drop", (e) => e.preventDefault());
}

function loadTranslations(dict) {
  t = (k) => dict[k] || k;
  document.documentElement.lang = dict["lang.code"] || "zh-CN";
  document.title = t("app.title");

  setText("app-title", t("app.title"));
  setText("settlement-label", t("dashboard.settlement_month"));
  setText("run-settlement", t("dashboard.run"));
  setText("run-id-label", t("dashboard.run_id"));
  setText("run-fx-label", t("dashboard.fx_rate"));
  setText("run-config-label", t("dashboard.config_version"));

  setText("dashboard-counts", t("dashboard.counts"));
  setText("count-total-label", t("dashboard.total"));
  setText("count-in-label", t("dashboard.in_study"));
  setText("count-grad-label", t("dashboard.graduated"));
  setText("count-with-label", t("dashboard.withdrawn"));

  setText("special-title", t("special.title"));
  setText("special-hint", t("special.hint"));
  setText("col-student-id", t("field.student_id"));
  setText("col-name", t("field.name"));
  setText("col-status", t("field.status"));
  setText("col-type", t("special.type"));
  setText("col-action", t("special.action"));

  setText("export-csv", t("reports.export_csv"));
  setText("export-xlsx", t("reports.export_xlsx"));

  setText("student-add", t("students.add"));
  setText("student-edit", t("students.edit"));
  setText("student-delete", t("students.delete"));
  setText("student-import", t("students.import"));
  setText("student-template", t("students.template"));
  setPlaceholder("student-search", t("students.search"));

  setText("cfg-living-b-label", t("degree.bachelor"));
  setText("cfg-living-m-label", t("degree.master"));
  setText("cfg-living-p-label", t("degree.phd"));
  setText("cfg-study-label", t("config.study"));
  setText("cfg-baggage-label", t("config.baggage"));
  setText("cfg-fx-label", t("config.fx_rate"));
  setText("cfg-policy-label", t("config.policy"));
  setText("cfg-withdrawn-label", t("config.withdrawn_default"));
  setText("cfg-save", t("config.save"));

  setText("report-load", t("reports.load"));
  setText("reports-total-title", t("reports.per_student"));
  setText("reports-records-title", t("reports.records"));

  setText("backup-create", t("backup.create"));
  setText("backup-restore", t("backup.restore"));
  setText("backup-replace", t("backup.restore_replace"));
  setText("backup-merge", t("backup.restore_merge"));

  setText("about-version", t("about.version") + ": 1.0.0");

  setText("student-modal-title", t("students.add"));
  setText("form-student-id-label", t("field.student_id"));
  setText("form-name-label", t("field.name"));
  setText("form-degree-label", t("field.degree"));
  setText("form-entry-label", t("field.entry_date"));
  setText("form-status-label", t("field.status"));
  setText("form-graduation-label", t("field.graduation_date"));
  setText("form-withdrawal-label", t("field.withdrawal_date"));
  setText("form-empty-label", t("field.empty_none"));
  setText("form-empty-label-2", t("field.empty_none"));
  setText("grad-hint", t("hint.graduation"));
  setText("withdraw-hint", t("hint.withdrawal"));
  setText("student-save", t("common.save"));
  setText("student-cancel", t("common.cancel"));

  const tabs = document.querySelectorAll("nav .tab");
  const tabLabels = ["tab.dashboard", "tab.students", "tab.config", "tab.reports", "tab.backup", "tab.about"];
  tabs.forEach((tab, idx) => (tab.textContent = t(tabLabels[idx])));

  const degreeSelect = document.getElementById("form-degree");
  degreeSelect.innerHTML = "";
  Object.entries(degreeMap).forEach(([value, key]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = t(key);
    degreeSelect.appendChild(option);
  });

  const statusSelect = document.getElementById("form-status");
  statusSelect.innerHTML = "";
  Object.entries(statusMap).forEach(([value, key]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = t(key);
    statusSelect.appendChild(option);
  });
}

function renderStudents(students) {
  const thead = document.querySelector("#students-table thead tr");
  thead.innerHTML = "";
  ["field.student_id","field.name","field.degree","field.entry_date","field.status","field.graduation_date","field.withdrawal_date"].forEach(k => {
    const th = document.createElement("th");
    th.textContent = t(k);
    thead.appendChild(th);
  });
  const tbody = document.querySelector("#students-table tbody");
  tbody.innerHTML = "";
  students.forEach(s => {
    const tr = document.createElement("tr");
    tr.dataset.studentId = s.student_id;
    [
      s.student_id,
      s.name,
      labelForDegree(s.degree_level),
      s.first_entry_date,
      labelForStatus(s.status),
      s.graduation_date || "",
      s.withdrawal_date || ""
    ].forEach(v => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function renderSpecial(special) {
  const tbody = document.querySelector("#special-table tbody");
  tbody.innerHTML = "";
  if (special.baggage.length === 0 && special.withdrawal.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.textContent = t("special.none");
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  special.baggage.forEach(s => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.student_id}</td>
      <td>${s.name}</td>
      <td><span class="badge">${labelForStatus(s.status)}</span></td>
      <td>${t("special.baggage")}</td>
      <td><label class="checkbox"><input type="checkbox" data-type="baggage" data-id="${s.student_id}" /> ${t("special.baggage_toggle")}</label></td>
    `;
    tbody.appendChild(tr);
  });
  special.withdrawal.forEach(s => {
    const checked = s.default_checked ? "checked" : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.student_id}</td>
      <td>${s.name}</td>
      <td><span class="badge">${labelForStatus(s.status)}</span></td>
      <td>${t("special.withdrawal")}</td>
      <td><label class="checkbox"><input type="checkbox" data-type="withdrawal" data-id="${s.student_id}" ${checked} /> ${t("special.withdrawal_toggle")}</label></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderReports(records, perStudent) {
  const totalHead = document.querySelector("#reports-total-table thead tr");
  totalHead.innerHTML = "";
  ["field.student_id", "field.name", "reports.total_cny"].forEach(k => {
    const th = document.createElement("th");
    th.textContent = t(k);
    totalHead.appendChild(th);
  });
  const totalBody = document.querySelector("#reports-total-table tbody");
  totalBody.innerHTML = "";
  perStudent.forEach(r => {
    const tr = document.createElement("tr");
    [r.student_id, r.name, r.amount_cny].forEach(v => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    totalBody.appendChild(tr);
  });

  const thead = document.querySelector("#reports-table thead tr");
  thead.innerHTML = "";
  const headers = [
    "export.header.run_id",
    "export.header.settlement_month",
    "export.header.student_id",
    "export.header.allowance_type",
    "export.header.period_start",
    "export.header.period_end",
    "export.header.amount_usd",
    "export.header.fx_rate",
    "export.header.amount_cny",
    "export.header.rule_id",
    "export.header.description",
    "export.header.metadata"
  ];
  headers.forEach(k => {
    const th = document.createElement("th");
    th.textContent = t(k);
    thead.appendChild(th);
  });
  const tbody = document.querySelector("#reports-table tbody");
  tbody.innerHTML = "";
  records.forEach(r => {
    const tr = document.createElement("tr");
    [
      r.run_id,
      r.settlement_month,
      r.student_id,
      labelForAllowance(r.allowance_type),
      r.period_start,
      r.period_end,
      r.amount_usd,
      r.fx_rate,
      r.amount_cny,
      r.rule_id,
      r.description,
      r.metadata_json
    ].forEach(v => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function currentSelectedStudentId() {
  const row = document.querySelector("#students-table tbody tr.selected");
  return row ? row.dataset.studentId : null;
}

function updateRunInfo(run) {
  setText("run-id", run ? run.run_id : "-");
  setText("run-fx", run ? run.fx_rate : "-");
  setText("run-config", run ? run.config_version : "-");
}

function updateCounts(counts) {
  setText("count-total", counts.total || 0);
  setText("count-in", counts["In-study"] || 0);
  setText("count-grad", counts["Graduated"] || 0);
  setText("count-with", counts["Withdrawn"] || 0);
}

function showModal(show) {
  const modal = document.getElementById("student-modal");
  modal.classList.toggle("hidden", !show);
}

function syncDateControls() {
  const status = document.getElementById("form-status").value;
  const gradEmpty = document.getElementById("form-graduation-empty");
  const gradInput = document.getElementById("form-graduation");
  const withdrawEmpty = document.getElementById("form-withdrawal-empty");
  const withdrawInput = document.getElementById("form-withdrawal");

  if (status !== "Graduated") {
    gradEmpty.checked = true;
  }
  gradEmpty.disabled = status !== "Graduated";
  gradInput.disabled = gradEmpty.checked || status !== "Graduated";
  if (status !== "Graduated") {
    gradInput.value = "";
  }

  if (status !== "Withdrawn") {
    withdrawEmpty.checked = true;
  }
  withdrawEmpty.disabled = status !== "Withdrawn";
  withdrawInput.disabled = withdrawEmpty.checked || status !== "Withdrawn";
  if (status !== "Withdrawn") {
    withdrawInput.value = "";
  }
}

function openStudentDialog(studentId) {
  const errorBox = document.getElementById("student-form-error");
  errorBox.textContent = "";

  let student = null;
  if (studentId && state) {
    student = state.students.find(s => s.student_id === studentId);
  }
  const isEdit = !!student;
  setText("student-modal-title", isEdit ? t("students.edit") : t("students.add"));

  document.getElementById("form-student-id").value = student ? student.student_id : "";
  document.getElementById("form-student-id").disabled = isEdit;
  document.getElementById("form-name").value = student ? student.name : "";
  document.getElementById("form-degree").value = student ? student.degree_level : "Bachelor";
  document.getElementById("form-entry").value = student ? student.first_entry_date : new Date().toISOString().slice(0, 10);
  document.getElementById("form-status").value = student ? student.status : "In-study";
  document.getElementById("form-graduation").value = student && student.graduation_date ? student.graduation_date : "";
  document.getElementById("form-withdrawal").value = student && student.withdrawal_date ? student.withdrawal_date : "";

  document.getElementById("form-graduation-empty").checked = !(student && student.graduation_date);
  document.getElementById("form-withdrawal-empty").checked = !(student && student.withdrawal_date);
  syncDateControls();

  showModal(true);
}

function bindEvents() {
  document.querySelectorAll("nav .tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("nav .tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
      document.getElementById(btn.dataset.tab).classList.add("active");
    });
  });

  document.getElementById("settlement-month").addEventListener("change", async (e) => {
    const month = e.target.value;
    const res = JSON.parse(await backend.get_special(month));
    if (res.ok) renderSpecial(res.special);
    const runInfo = JSON.parse(await backend.get_run_info(month));
    updateRunInfo(runInfo.run || null);
  });

  document.getElementById("run-settlement").addEventListener("click", async () => {
    const month = document.getElementById("settlement-month").value;
    const baggage = Array.from(document.querySelectorAll('input[data-type="baggage"]:checked')).map(i => i.dataset.id);
    const withdrawal = Array.from(document.querySelectorAll('input[data-type="withdrawal"]:checked')).map(i => i.dataset.id);
    const res = JSON.parse(await backend.run_settlement(month, baggage.join(","), withdrawal.join(",")));
    if (!res.ok) {
      alert(res.error || t("error.no_run"));
      return;
    }
    document.getElementById("run-info").textContent = `${t("dashboard.run_info")}: ${res.run_id}`;
    if (res.warnings && res.warnings.length) {
      alert(res.warnings.join("\n"));
    }
    await loadState();
  });

  document.getElementById("export-csv").addEventListener("click", async () => {
    const month = document.getElementById("settlement-month").value;
    await backend.export_settlement(month, "csv");
  });

  document.getElementById("export-xlsx").addEventListener("click", async () => {
    const month = document.getElementById("settlement-month").value;
    await backend.export_settlement(month, "xlsx");
  });

  document.getElementById("student-import").addEventListener("click", () => {
    document.getElementById("student-import-file").click();
  });

  document.getElementById("student-import-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    const res = JSON.parse(await backend.import_students(text));
    if (!res.ok && res.errors) alert(res.errors.join("\n"));
    if (res.warnings && res.warnings.length) alert(res.warnings.join("\n"));
    await loadState();
  });

  document.getElementById("student-template").addEventListener("click", async () => {
    const header = await backend.get_csv_template();
    const blob = new Blob([header + "\n"], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "students_template.csv";
    a.click();
  });

  document.getElementById("student-add").addEventListener("click", () => openStudentDialog());
  document.getElementById("student-edit").addEventListener("click", () => {
    const id = currentSelectedStudentId();
    if (id) openStudentDialog(id);
  });
  document.getElementById("student-delete").addEventListener("click", async () => {
    const id = currentSelectedStudentId();
    if (!id) return;
    if (!confirm(t("confirm.delete"))) return;
    await backend.delete_student(id);
    await loadState();
  });

  document.getElementById("student-search").addEventListener("input", () => {
    if (!state) return;
    const q = document.getElementById("student-search").value.toLowerCase();
    const filtered = state.students.filter(s => {
      return [s.student_id, s.name, s.degree_level, s.status].join(" ").toLowerCase().includes(q);
    });
    renderStudents(filtered);
  });

  document.getElementById("cfg-save").addEventListener("click", async () => {
    const payload = {
      living_bachelor: document.getElementById("cfg-living-b").value,
      living_master: document.getElementById("cfg-living-m").value,
      living_phd: document.getElementById("cfg-living-p").value,
      study_allowance: document.getElementById("cfg-study").value,
      baggage_allowance: document.getElementById("cfg-baggage").value,
      fx_rate: document.getElementById("cfg-fx").value,
      policy_switch: document.getElementById("cfg-policy").checked,
      withdrawn_default: document.getElementById("cfg-withdrawn-default").checked
    };
    await backend.save_config(JSON.stringify(payload));
    document.getElementById("cfg-status").textContent = `${t("config.saved")} ${new Date().toLocaleString()}`;
  });

  document.getElementById("report-load").addEventListener("click", async () => {
    const month = document.getElementById("report-month").value;
    const res = JSON.parse(await backend.get_reports(month));
    if (res.ok) {
      renderReports(res.records, res.per_student);
      document.getElementById("report-info").textContent = `${t("dashboard.run_id")}: ${res.run.run_id} | ${t("dashboard.fx_rate")}: ${res.run.fx_rate}`;
    } else {
      alert(t("error.no_run"));
    }
  });

  document.getElementById("backup-create").addEventListener("click", async () => {
    const res = JSON.parse(await backend.backup());
    document.getElementById("backup-status").textContent = res.path || "";
  });
  document.getElementById("backup-restore").addEventListener("click", async () => {
    if (!confirm(t("confirm.restore"))) return;
    const res = JSON.parse(await backend.restore("replace"));
    document.getElementById("backup-status").textContent = res.ok ? t("backup.pre_backup") : "";
    await loadState();
  });
  document.getElementById("backup-replace").addEventListener("click", async () => {
    if (!confirm(t("confirm.restore_replace"))) return;
    const res = JSON.parse(await backend.restore("replace"));
    document.getElementById("backup-status").textContent = res.ok ? t("backup.pre_backup") : "";
    await loadState();
  });
  document.getElementById("backup-merge").addEventListener("click", async () => {
    if (!confirm(t("confirm.restore"))) return;
    const res = JSON.parse(await backend.restore("merge"));
    document.getElementById("backup-status").textContent = res.ok ? t("backup.pre_backup") : "";
    await loadState();
  });

  document.getElementById("lang-select").addEventListener("change", async (e) => {
    await backend.set_language(e.target.value);
    await loadState();
  });

  document.querySelector("#students-table tbody").addEventListener("click", (e) => {
    const row = e.target.closest("tr");
    if (!row) return;
    document.querySelectorAll("#students-table tbody tr").forEach(r => r.classList.remove("selected"));
    row.classList.add("selected");
  });

  document.getElementById("form-status").addEventListener("change", syncDateControls);
  document.getElementById("form-graduation-empty").addEventListener("change", syncDateControls);
  document.getElementById("form-withdrawal-empty").addEventListener("change", syncDateControls);

  document.getElementById("student-save").addEventListener("click", async () => {
    const payload = {
      student_id: document.getElementById("form-student-id").value.trim(),
      name: document.getElementById("form-name").value.trim(),
      degree_level: document.getElementById("form-degree").value,
      first_entry_date: document.getElementById("form-entry").value,
      status: document.getElementById("form-status").value,
      graduation_date: document.getElementById("form-graduation-empty").checked ? "" : document.getElementById("form-graduation").value,
      withdrawal_date: document.getElementById("form-withdrawal-empty").checked ? "" : document.getElementById("form-withdrawal").value
    };
    const res = JSON.parse(await backend.save_student(JSON.stringify(payload)));
    const errorBox = document.getElementById("student-form-error");
    if (!res.ok) {
      errorBox.textContent = res.errors ? res.errors.join("\n") : t("error.required");
      return;
    }
    errorBox.textContent = "";
    showModal(false);
    if (res.warnings && res.warnings.length) {
      document.getElementById("student-status").textContent = res.warnings.join(" ");
    } else {
      document.getElementById("student-status").textContent = `${t("students.saved")} ${new Date().toLocaleString()}`;
    }
    await loadState();
  });

  document.getElementById("student-cancel").addEventListener("click", () => {
    showModal(false);
  });

  setDateInputLocked("form-entry");
  setDateInputLocked("form-graduation");
  setDateInputLocked("form-withdrawal");
}

async function loadState() {
  state = JSON.parse(await backend.get_state());
  const dict = JSON.parse(await backend.get_translations());
  loadTranslations(dict);
  document.getElementById("lang-select").value = state.language || "zh_CN";

  document.getElementById("settlement-month").value = state.settlement_month;
  document.getElementById("report-month").value = state.settlement_month;

  document.getElementById("cfg-living-b").value = state.config.living_allowance_bachelor;
  document.getElementById("cfg-living-m").value = state.config.living_allowance_master;
  document.getElementById("cfg-living-p").value = state.config.living_allowance_phd;
  document.getElementById("cfg-study").value = state.config.study_allowance_usd;
  document.getElementById("cfg-baggage").value = state.config.baggage_allowance_usd;
  document.getElementById("cfg-fx").value = state.config.fx_rate_usd_to_cny;
  document.getElementById("cfg-policy").checked = !!state.config.issue_study_if_exit_before_oct_entry_year;
  document.getElementById("cfg-withdrawn-default").checked = !!state.config.withdrawn_living_default;

  updateCounts(state.counts || {});
  updateRunInfo(state.run || null);
  renderStudents(state.students || []);
  renderSpecial(state.special || {baggage: [], withdrawal: []});
  renderReports(state.records || [], state.per_student || []);
}

new QWebChannel(qt.webChannelTransport, function(channel) {
  backend = channel.objects.backend;
  bindEvents();
  loadState();
});
