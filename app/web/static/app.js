"use strict";

// ---- helpers -------------------------------------------------------------

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? null : res.json();
}

function jsonPost(body) {
  return { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2600);
}

const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Verdict -> stamp label + class.
const STAMP = {
  PASS: { label: "PASS", sub: "compliant", cls: "pass" },
  FAIL: { label: "BLOCKED", sub: "do not ship", cls: "fail" },
  REQUIRES_REVIEW: { label: "REVIEW", sub: "needs a human", cls: "review" },
};

// Rule metadata (citation + description), loaded once from the active ruleset.
let RULES = {};
async function loadRuleMeta() {
  try {
    const rs = await api("/ruleset/active");
    RULES = Object.fromEntries(rs.rules.map((r) => [r.rule_key, r]));
  } catch (_) {
    RULES = {};
  }
}

// Claim keys worth surfacing, in order.
const CLAIM_KEYS = [
  "advertised_price", "price_type", "lease_monthly_payment", "finance_monthly_payment",
  "apr", "lease_term_months", "finance_term_months", "due_at_signing", "down_payment",
  "trim_claimed", "stock_number_claimed", "expiration_date", "extraction_confidence",
];

function stampNode(verdict) {
  const s = STAMP[verdict] || STAMP.REQUIRES_REVIEW;
  return el("div", `stamp ${s.cls} animate`, `${s.label}<span class="sub">${s.sub}</span>`);
}

function docketNode(violations) {
  if (!violations || violations.length === 0) {
    return el("div", "docket-empty", "&#10003; No violations — clean against the active ruleset.");
  }
  const wrap = el("div", "docket");
  for (const v of violations) {
    const meta = RULES[v.rule_key] || {};
    const row = el("div", "violation");
    if (meta.source_citation) row.appendChild(el("div", "citation", esc(meta.source_citation)));
    const head = el("div", "v-head");
    head.appendChild(el("span", `sev ${v.severity}`, v.severity));
    head.appendChild(el("span", "rule-key", esc(v.rule_key)));
    row.appendChild(head);
    row.appendChild(el("div", "message", esc(v.message || meta.description || "")));
    wrap.appendChild(row);
  }
  return wrap;
}

function claimsNode(claims) {
  const grid = el("div", "claims");
  for (const k of CLAIM_KEYS) {
    if (!(k in claims)) continue;
    const val = claims[k];
    const cell = el("div", "claim");
    cell.appendChild(el("div", "k", k));
    const isNull = val === null || val === undefined || val === "";
    cell.appendChild(el("div", `val${isNull ? " null" : ""}`, isNull ? "&mdash;" : esc(val)));
    grid.appendChild(cell);
  }
  return grid;
}

function renderVerdict(target, { verdict, violations, claims, ctxHtml, copyText }) {
  target.innerHTML = "";
  const head = el("div", "result-head");
  head.appendChild(el("div", "ctx", ctxHtml || ""));
  head.appendChild(stampNode(verdict));
  target.appendChild(head);

  if (copyText) {
    target.appendChild(el("div", "section-label", "Generated copy"));
    target.appendChild(el("div", "copy-out", esc(copyText)));
  }

  target.appendChild(el("div", "section-label", "Findings"));
  target.appendChild(docketNode(violations));

  if (claims && Object.keys(claims).length) {
    target.appendChild(el("div", "section-label", "Extracted claims"));
    target.appendChild(claimsNode(claims));
  }
}

function withBusy(btn, fn) {
  return async (...args) => {
    const others = document.querySelectorAll("button.btn");
    others.forEach((b) => (b.disabled = true));
    const label = btn.textContent;
    btn.textContent = "Working…";
    try {
      await fn(...args);
    } catch (e) {
      toast(e.message);
    } finally {
      others.forEach((b) => (b.disabled = false));
      btn.textContent = label;
    }
  };
}

// ---- validate / generate page -------------------------------------------

async function initValidatePage() {
  await loadRuleMeta();
  const vehicleSel = document.getElementById("vehicle");
  const vehicles = await api("/vehicles");
  for (const v of vehicles) {
    const opt = el("option");
    opt.value = v.id;
    opt.textContent = `#${v.id} — ${v.year} ${v.make} ${v.model} ${v.trim} ($${Number(v.dealer_price).toLocaleString()})`;
    vehicleSel.appendChild(opt);
  }

  const result = document.getElementById("result");
  const vid = () => Number(vehicleSel.value);
  const channel = () => document.getElementById("channel").value;
  const ctx = () => {
    const o = vehicleSel.selectedOptions[0];
    return `vehicle <strong>${esc(o ? o.textContent : "")}</strong>`;
  };

  const validateBtn = document.getElementById("validateBtn");
  validateBtn.onclick = withBusy(validateBtn, async () => {
    const copy = document.getElementById("copy").value.trim();
    if (!copy) return toast("Paste some ad copy to validate.");
    const data = await api("/validate", jsonPost({ vehicle_id: vid(), copy_text: copy, channel: channel() }));
    renderVerdict(result, { verdict: data.verdict, violations: data.violations, claims: data.extracted_claims, ctxHtml: ctx() });
  });

  const generateBtn = document.getElementById("generateBtn");
  generateBtn.onclick = withBusy(generateBtn, async () => {
    const gen = await api("/generate", jsonPost({ vehicle_id: vid(), channel: channel() }));
    const run = await api(`/runs/${gen.run_id}`);
    document.getElementById("copy").value = gen.copy_text;
    renderVerdict(result, {
      verdict: gen.verdict, violations: run.violations, claims: run.extracted_claims,
      ctxHtml: `${ctx()} &middot; ${gen.attempts} attempt(s)`, copyText: gen.copy_text,
    });
  });
}

// ---- review queue page ---------------------------------------------------

async function initReviewPage() {
  await loadRuleMeta();
  const queue = document.getElementById("queue");
  const detail = document.getElementById("detail");
  const filter = document.getElementById("statusFilter");
  let activeRow = null;

  async function loadQueue() {
    queue.innerHTML = "";
    const runs = await api(`/reviews?status=${filter.value}`);
    if (!runs.length) {
      queue.appendChild(el("div", "empty", "Nothing here. The queue is clear."));
      return;
    }
    for (const r of runs) {
      const row = el("button", "run-row");
      row.appendChild(el("span", "rid", `#${r.run_id}`));
      const mid = el("span", "rv", `vehicle ${r.vehicle_id ?? "—"} &middot; ${r.violation_count} finding(s)`);
      row.appendChild(mid);
      row.appendChild(el("span", `chip ${r.status}`, r.status.replace("REQUIRES_REVIEW", "REVIEW")));
      row.onclick = () => {
        if (activeRow) activeRow.classList.remove("active");
        row.classList.add("active");
        activeRow = row;
        showRun(r.run_id);
      };
      queue.appendChild(row);
    }
  }

  async function showRun(runId) {
    const run = await api(`/runs/${runId}`);
    renderVerdict(detail, {
      verdict: run.status, violations: run.violations, claims: run.extracted_claims,
      ctxHtml: `run <strong>#${run.run_id}</strong> &middot; ruleset ${run.ruleset_version_id ?? "—"}`,
    });
    detail.appendChild(decisionForm(runId, run.review_decisions));
  }

  function decisionForm(runId, decisions) {
    const box = el("div", "decision");
    box.appendChild(el("div", "section-label", "Reviewer decision"));
    if (decisions && decisions.length) {
      for (const d of decisions) {
        box.appendChild(el("div", "message", `${esc(d.decision)} by ${esc(d.reviewer)}${d.notes ? " — " + esc(d.notes) : ""}`));
      }
    }
    const who = el("input", null);
    who.type = "text";
    who.placeholder = "your email";
    box.appendChild(el("label", null, "Reviewer"));
    box.appendChild(who);

    const radios = el("div", "radios");
    for (const opt of ["approve", "reject", "override"]) {
      const lab = el("label");
      lab.innerHTML = `<input type="radio" name="decision" value="${opt}"${opt === "approve" ? " checked" : ""}> ${opt}`;
      radios.appendChild(lab);
    }
    box.appendChild(el("label", null, "Decision"));
    box.appendChild(radios);

    const notes = el("textarea", null);
    notes.placeholder = "Notes (optional)";
    notes.style.minHeight = "70px";
    box.appendChild(notes);

    const submit = el("button", "btn btn-primary", "Log decision");
    submit.style.marginTop = "12px";
    submit.onclick = withBusy(submit, async () => {
      if (!who.value.trim()) return toast("Enter a reviewer.");
      const decision = box.querySelector("input[name=decision]:checked").value;
      await api(`/runs/${runId}/decisions`, jsonPost({ reviewer: who.value.trim(), decision, notes: notes.value.trim() || null }));
      toast("Decision logged.");
      showRun(runId);
    });
    box.appendChild(submit);
    return box;
  }

  filter.onchange = () => loadQueue().catch((e) => toast(e.message));
  loadQueue().catch((e) => toast(e.message));
}

// ---- boot ----------------------------------------------------------------

const PAGE = document.body.dataset.page;
const boot = PAGE === "review" ? initReviewPage : initValidatePage;
boot().catch((e) => toast(e.message));
