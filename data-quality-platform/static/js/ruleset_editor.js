// 规则集可视化编辑器：把 YAML 解析为表格 → 用户编辑 → 序列化为 YAML 提交。
// 设计目标：尽量薄，不引外部依赖。

(function () {
  "use strict";

  const TYPES = window.RULESET_TYPES || [];
  const DIMENSIONS = [
    { key: "completeness", label: "完整性" },
    { key: "uniqueness", label: "唯一性" },
    { key: "conformity", label: "规范性" },
    { key: "accuracy", label: "准确性" },
    { key: "consistency", label: "一致性" },
    { key: "timeliness", label: "时效性" },
  ];
  const SEVERITIES = [
    { key: "blocker", label: "blocker" },
    { key: "major", label: "major" },
    { key: "minor", label: "minor" },
  ];

  const state = {
    dataset: "",
    description: "",
    defaults: { severity: "major" },
    rules: [],
  };

  // ----------------- 解析/序列化 -----------------
  function parseInitial() {
    const rawText = document.getElementById("yaml-source").value || "";
    try {
      const parsed = window.jsyaml ? window.jsyaml.load(rawText) : null;
      if (!parsed) throw new Error("无法解析");
      state.dataset = parsed.dataset || "";
      state.description = parsed.description || "";
      state.defaults = parsed.defaults || { severity: "major" };
      state.rules = Array.isArray(parsed.rules) ? parsed.rules : [];
    } catch (e) {
      // YAML 解析失败 → 当成空表 + 在提示中说明
      state.rules = [];
      const hint = document.getElementById("parse-hint");
      if (hint) {
        hint.textContent = "YAML 解析失败，进入空白表格模式：" + e.message;
        hint.style.display = "block";
      }
    }
  }

  function serialize() {
    const out = {
      dataset: state.dataset,
      description: state.description,
      defaults: state.defaults,
      rules: state.rules.map((r) => normalizeRule(r)),
    };
    document.getElementById("yaml-source").value = window.jsyaml
      ? window.jsyaml.dump(out, { forceQuotes: false, lineWidth: 120 })
      : JSON.stringify(out, null, 2);
  }

  function normalizeRule(r) {
    const out = {};
    out.id = r.id || "";
    out.type = r.type || (TYPES[0] || "not_null");
    out.dimension = r.dimension || "completeness";
    out.severity = r.severity || state.defaults.severity || "major";
    if (r.name) out.name = r.name;
    if (r.column) out.column = r.column;
    if (r.columns && Array.isArray(r.columns) && r.columns.length) {
      out.columns = r.columns;
    }
    if (r.params && Object.keys(r.params).length) {
      out.params = r.params;
    }
    return out;
  }

  // ----------------- 表格渲染 -----------------
  function renderTable() {
    const tbody = document.getElementById("rules-tbody");
    tbody.innerHTML = "";
    if (state.rules.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="8" class="empty" style="padding:24px;color:var(--text-dim);">点 "+ 新增规则" 开始编辑</td>`;
      tbody.appendChild(tr);
      return;
    }
    state.rules.forEach((rule, idx) => tbody.appendChild(buildRow(rule, idx)));
  }

  function buildRow(rule, idx) {
    const tr = document.createElement("tr");
    tr.dataset.index = idx;

    tr.innerHTML = `
      <td><input type="text" data-field="id" value="${escapeAttr(rule.id || "")}" placeholder="ord_001"></td>
      <td><input type="text" data-field="name" value="${escapeAttr(rule.name || "")}" placeholder="规则名称"></td>
      <td>
        <select data-field="type">
          ${TYPES.map((t) => `<option value="${t}" ${rule.type === t ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </td>
      <td>
        <select data-field="dimension">
          ${DIMENSIONS.map((d) => `<option value="${d.key}" ${rule.dimension === d.key ? "selected" : ""}>${d.label}</option>`).join("")}
        </select>
      </td>
      <td>
        <select data-field="severity">
          ${SEVERITIES.map((s) => `<option value="${s.key}" ${rule.severity === s.key ? "selected" : ""}>${s.label}</option>`).join("")}
        </select>
      </td>
      <td><input type="text" data-field="columns" value="${escapeAttr(columnsDisplay(rule))}" placeholder="order_id 或 a,b,c"></td>
      <td><input type="text" data-field="params" value="${escapeAttr(paramsDisplay(rule.params))}" placeholder="k=v 用半角逗号分隔"></td>
      <td><button type="button" class="row-del" title="删除">✕</button></td>
    `;

    tr.querySelectorAll("input[data-field], select[data-field]").forEach((el) => {
      el.addEventListener("change", () => onCellChange(idx, el));
    });
    tr.querySelector(".row-del").addEventListener("click", () => {
      state.rules.splice(idx, 1);
      renderTable();
    });

    return tr;
  }

  function onCellChange(idx, el) {
    const r = state.rules[idx] || {};
    const field = el.dataset.field;
    if (field === "columns") {
      const parts = el.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (parts.length === 0) {
        delete r.column;
        delete r.columns;
      } else if (parts.length === 1) {
        r.column = parts[0];
        delete r.columns;
      } else {
        r.columns = parts;
        delete r.column;
      }
    } else if (field === "params") {
      r.params = parseParams(el.value);
    } else if (field === "name" && !el.value) {
      delete r.name;
    } else {
      r[field] = el.value;
    }
    state.rules[idx] = r;
  }

  function columnsDisplay(rule) {
    if (Array.isArray(rule.columns) && rule.columns.length) {
      return rule.columns.join(", ");
    }
    if (rule.column) return rule.column;
    return "";
  }

  function paramsDisplay(params) {
    if (!params || typeof params !== "object") return "";
    return Object.entries(params)
      .map(([k, v]) => {
        if (Array.isArray(v)) return `${k}=${v.join("|")}`;
        if (typeof v === "object" && v !== null) return `${k}=${JSON.stringify(v)}`;
        return `${k}=${v}`;
      })
      .join(", ");
  }

  function parseParams(text) {
    if (!text || !text.trim()) return undefined;
    const out = {};
    // 支持 key=value1|value2|value3 → 列表；纯 value → 字符串
    text.split(",").forEach((kv) => {
      const idx = kv.indexOf("=");
      if (idx < 0) return;
      const k = kv.slice(0, idx).trim();
      const vRaw = kv.slice(idx + 1).trim();
      if (!k) return;
      if (vRaw.includes("|")) {
        out[k] = vRaw.split("|").map((s) => s.trim());
      } else {
        out[k] = vRaw;
      }
    });
    return Object.keys(out).length ? out : undefined;
  }

  // ----------------- 工具 -----------------
  function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  function newRule() {
    const max = state.rules
      .map((r) => (r.id || "").match(/^(\D*)(\d+)$/))
      .filter(Boolean)
      .map((m) => parseInt(m[2], 10))
      .reduce((a, b) => Math.max(a, b), 0);
    return {
      id: `ord_${String(max + 1).padStart(3, "0")}`,
      type: TYPES[0] || "not_null",
      dimension: "completeness",
      severity: state.defaults.severity || "major",
      columns: "",
      params: undefined,
    };
  }

  // ----------------- 启动 -----------------
  document.addEventListener("DOMContentLoaded", () => {
    parseInitial();

    document.getElementById("dataset").value = state.dataset;
    document.getElementById("description").value = state.description;
    document.getElementById("default-severity").value =
      (state.defaults && state.defaults.severity) || "major";

    document.getElementById("dataset").addEventListener("input", (e) => {
      state.dataset = e.target.value;
    });
    document.getElementById("description").addEventListener("input", (e) => {
      state.description = e.target.value;
    });
    document.getElementById("default-severity").addEventListener("change", (e) => {
      state.defaults = state.defaults || {};
      state.defaults.severity = e.target.value;
    });

    document.getElementById("add-row").addEventListener("click", () => {
      state.rules.push(newRule());
      renderTable();
    });

    const form = document.getElementById("edit-form");
    form.addEventListener("submit", () => serialize());

    // YAML 高级编辑模式：双向同步
    const yamlTa = document.getElementById("yaml-source");
    document.getElementById("sync-from-yaml").addEventListener("click", () => {
      try {
        parseInitial();
        renderTable();
        const hint = document.getElementById("parse-hint");
        if (hint) hint.style.display = "none";
      } catch (e) {
        alert("YAML 解析失败: " + e.message);
      }
    });

    renderTable();
  });
})();