"use strict";

/* ============ 全局状态 ============ */
const State = {
  user: null,          // {user_id, username, role}
  view: "dashboard",
  page: {},            // 各列表分页状态
  filter: {},          // 各列表筛选状态
};

const PAGE_SIZE = 20;

/* ============ 工具函数 ============ */
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  let data = null;
  try {
    data = await resp.json();
  } catch (_) {
    /* 无 JSON */
  }
  if (!resp.ok) {
    const msg = (data && (data.error || data.detail)) || `请求失败 (${resp.status})`;
    throw new Error(msg);
  }
  return data;
}

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return n;
}

function fmtTime(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleString("zh-CN", { hour12: false });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function toast(msg, type = "info") {
  const wrap = document.getElementById("toastWrap");
  const t = el("div", { class: `toast ${type}` }, msg);
  wrap.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transition = "opacity .3s";
    setTimeout(() => t.remove(), 300);
  }, 2600);
}

function confirmModal(title, message) {
  return new Promise((resolve) => {
    const mask = el("div", { class: "modal-mask" });
    const m = el("div", { class: "modal" }, [
      el("h3", {}, title),
      el("p", {}, message),
      el("div", { class: "actions" }, [
        el("button", {
          class: "btn btn-ghost",
          onclick: () => {
            mask.remove();
            resolve(false);
          },
        }, "取消"),
        el("button", {
          class: "btn btn-danger",
          onclick: () => {
            mask.remove();
            resolve(true);
          },
        }, "确认"),
      ]),
    ]);
    mask.appendChild(m);
    document.getElementById("overlay").appendChild(mask);
  });
}

/* ============ 鉴权流程 ============ */
async function bootstrap() {
  try {
    const me = await api("GET", "/admin/api/me");
    State.user = me.data;
    enterApp();
  } catch (_) {
    // 未登录：判断是否需要初始化管理员
    showLogin();
  }
}

async function showLogin() {
  document.getElementById("loginScreen").classList.remove("hidden");
  const btn = document.getElementById("loginBtn");
  btn.onclick = doLogin;
  document.getElementById("loginPass").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doLogin();
  });
}

async function doLogin() {
  const username = document.getElementById("loginUser").value.trim();
  const password = document.getElementById("loginPass").value;
  if (!username || !password) {
    toast("用户名与密码必填", "error");
    return;
  }
  try {
    const r = await api("POST", "/admin/api/login", { username, password });
    State.user = r.data;
    document.getElementById("loginScreen").classList.add("hidden");
    enterApp();
    toast(`欢迎，${State.user.username}`, "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function doLogout() {
  try {
    await api("POST", "/admin/api/logout");
  } catch (_) {}
  State.user = null;
  location.reload();
}

function enterApp() {
  // 角色控制导航显隐
  document.querySelectorAll(".nav-item.hidden-role").forEach((n) => {
    const role = n.getAttribute("data-role");
    n.classList.toggle("hidden-role", State.user.role !== role);
  });
  document.getElementById("userName").textContent = State.user.username;
  document.getElementById("avatar").textContent = State.user.username[0]?.toUpperCase() || "U";
  const rt = document.getElementById("roleTag");
  rt.textContent = State.user.role === "admin" ? "管理员" : "用户";
  rt.className = `role-tag ${State.user.role}`;
  document.getElementById("logoutBtn").onclick = doLogout;
  // 导航绑定
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.onclick = () => switchView(n.getAttribute("data-view"));
  });
  document.getElementById("menuToggle").onclick = () =>
    document.getElementById("sidebar").classList.toggle("open");
  switchView("dashboard");
}

/* ============ 视图切换 ============ */
const TITLES = {
  dashboard: "概览",
  docs: "知识库",
  users: "用户管理",
  errors: "调用异常",
  ops: "系统运维",
  me: "个人中心",
};

function switchView(view) {
  State.view = view;
  document.querySelectorAll(".nav-item").forEach((n) =>
    n.classList.toggle("active", n.getAttribute("data-view") === view)
  );
  document.getElementById("pageTitle").textContent = TITLES[view] || view;
  document.getElementById("sidebar").classList.remove("open");
  const c = document.getElementById("content");
  c.innerHTML = "";
  const spin = el("div", { class: "empty" }, [el("span", { class: "spinner" }), " 加载中…"]);
  c.appendChild(spin);
  RENDERERS[view](c);
}

/* ============ 各视图渲染器 ============ */
const RENDERERS = {
  dashboard: renderDashboard,
  docs: renderDocs,
  users: renderUsers,
  errors: renderErrors,
  ops: renderOps,
  me: renderMe,
};

/* ---- Dashboard ---- */
async function renderDashboard(c) {
  let cfg = {}, tools = { data: { tools: [] } };
  try {
    if (State.user.role === "admin") {
      [cfg, tools] = await Promise.all([
        api("GET", "/admin/api/system/config"),
        api("GET", "/admin/api/system/tools"),
      ]);
    }
  } catch (e) {
    toast(e.message, "error");
  }

  // 统计卡片：知识库/文档/异常数量
  let docsTotal = 0, kbTotal = 0, errOpen = 0;
  try {
    const d = await api("GET", "/admin/api/documents?size=1");
    docsTotal = d.data.total;
    const k = await api("GET", "/admin/api/kb?size=1");
    kbTotal = k.data.total;
    const e = await api("GET", "/admin/api/errors?size=1&status=open");
    errOpen = e.data.total;
  } catch (_) {}

  const stats = el("div", { class: "grid cols-4" }, [
    statCard("文档总数", docsTotal, "blue"),
    statCard("知识库条目", kbTotal, "blue"),
    statCard("未处理异常", errOpen, errOpen ? "" : "blue"),
    statCard("当前角色", State.user.role === "admin" ? "管理员" : "用户", "blue"),
  ]);
  c.appendChild(stats);

  if (State.user.role === "admin") {
    // 配置诊断
    const rows = Object.entries(cfg.data || {}).map(([k, v]) =>
      el("tr", {}, [
        el("td", {}, k),
        el("td", {}, String(v.ok !== undefined ? (v.ok ? "✓ 正常" : "✗ 异常") : v)),
        el("td", {}, v.detail || ""),
      ])
    );
    c.appendChild(
      card("配置就绪诊断", [
        el("div", { class: "table-wrap" }, [
          el("table", {}, [el("thead", {}, el("tr", {}, [
            el("th", {}, "项目"), el("th", {}, "状态"), el("th", {}, "说明"),
          ])), el("tbody", {}, rows)]),
        ]),
      ])
    );
    // 工具清单
    const toolRows = (tools.data.tools || []).map((t) =>
      el("tr", {}, [el("td", {}, t.name || ""), el("td", {}, t.description || "")])
    );
    c.appendChild(
      card("已注册工具", [
        el("div", { class: "table-wrap" }, [
          el("table", {}, [el("thead", {}, el("tr", {}, [
            el("th", {}, "名称"), el("th", {}, "描述"),
          ])), el("tbody", {}, toolRows)]),
        ]),
      ])
    );
  } else {
    c.appendChild(
      card("快速入口", [
        el("p", { class: "empty" }, "你是普通用户，可查看本人知识库与调用异常，并在个人中心修改密码。"),
      ])
    );
  }
}

function statCard(label, value, cls) {
  return el("div", { class: "stat" }, [
    el("div", { class: "label" }, label),
    el("div", { class: `value ${cls}` }, String(value)),
  ]);
}

function card(title, children) {
  return el("div", { class: "card" }, [el("h3", {}, title), ...[].concat(children)]);
}

/* ---- 知识库（documents + kb_documents） ---- */
async function renderDocs(c) {
  const isAdmin = State.user.role === "admin";
  c.appendChild(
    card("文档 (documents)", [el("div", { id: "docTable" }), paginationBar("docs")])
  );
  c.appendChild(
    card("知识库条目 (kb_documents)", [el("div", { id: "kbTable" }), paginationBar("kb")])
  );
  await loadDocs(c);
}

async function loadDocs(c) {
  const isAdmin = State.user.role === "admin";
  const pg = State.page.docs || 1;
  const ownerParam = isAdmin ? "" : "";
  let d, k;
  try {
    d = await api("GET", `/admin/api/documents?page=${pg}&size=${PAGE_SIZE}`);
    k = await api("GET", `/admin/api/kb?page=${State.page.kb || 1}&size=${PAGE_SIZE}`);
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  const dt = document.getElementById("docTable");
  dt.innerHTML = "";
  dt.appendChild(
    buildTable(
      ["ID", "Owner", "名称", "来源", "大小", "时间", "操作"],
      d.data.items,
      (it) => [
        el("td", {}, it.id.slice(0, 8)),
        el("td", {}, it.owner_id.slice(0, 8)),
        el("td", {}, it.name),
        el("td", {}, it.provider),
        el("td", {}, String(it.size)),
        el("td", {}, fmtTime(it.created_at)),
        el("td", {}, deleteBtn(`/admin/api/documents/${it.id}`, "docs", c)),
      ]
    )
  );
  setTotal("docs", d.data.total);

  const kt = document.getElementById("kbTable");
  kt.innerHTML = "";
  kt.appendChild(
    buildTable(
      ["ID", "Owner", "标题", "类型", "块数", "状态", "时间", "操作"],
      k.data.items,
      (it) => [
        el("td", {}, it.id.slice(0, 8)),
        el("td", {}, it.owner_id.slice(0, 8)),
        el("td", {}, it.title),
        el("td", {}, it.source_type),
        el("td", {}, String(it.chunk_count)),
        el("td", {}, el("span", { class: `badge ${it.status === "ready" ? "ready" : "warn"}` }, it.status)),
        el("td", {}, fmtTime(it.created_at)),
        el("td", {}, deleteBtn(`/admin/api/kb/${it.id}`, "kb", c)),
      ]
    )
  );
  setTotal("kb", k.data.total);
}

function deleteBtn(url, view, c) {
  return el("button", {
    class: "btn-link danger",
    onclick: async () => {
      if (!(await confirmModal("删除确认", "确定要删除该项吗？此操作不可撤销。"))) return;
      try {
        await api("DELETE", url);
        toast("已删除", "success");
        if (view === "docs") loadDocs(c);
        else if (view === "kb") loadDocs(c);
        else if (view === "errors") loadErrors(c);
        else if (view === "users") loadUsers(c);
      } catch (e) {
        toast(e.message, "error");
      }
    },
  }, "删除");
}

/* ---- 用户管理（admin） ---- */
async function renderUsers(c) {
  if (State.user.role !== "admin") {
    c.appendChild(el("div", { class: "empty" }, "无权限"));
    return;
  }
  const toolbar = el("div", { class: "toolbar" }, [
    el("button", { class: "btn btn-primary btn-sm", onclick: () => showUserModal(c) }, "新建用户"),
  ]);
  c.appendChild(card("用户列表", [toolbar, el("div", { id: "userTable" }), paginationBar("users")]));
  await loadUsers(c);
}

async function loadUsers(c) {
  let r;
  try {
    r = await api("GET", `/admin/api/users?page=${State.page.users || 1}&size=${PAGE_SIZE}`);
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  const t = document.getElementById("userTable");
  t.innerHTML = "";
  t.appendChild(
    buildTable(
      ["用户名", "显示名", "角色", "状态", "创建时间", "操作"],
      r.data.items,
      (it) => [
        el("td", {}, it.username),
        el("td", {}, it.display_name || "—"),
        el("td", {}, el("span", { class: `role-tag ${it.role}` }, it.role)),
        el("td", {}, el("span", { class: `badge ${it.is_active ? "ready" : "warn"}` }, it.is_active ? "启用" : "停用")),
        el("td", {}, fmtTime(it.created_at)),
        el("td", {}, [
          el("button", { class: "btn-link", onclick: () => toggleUser(c, it) }, it.is_active ? "停用" : "启用"),
          " ",
          el("button", { class: "btn-link", onclick: () => showUserModal(c, it) }, "改角色"),
          " ",
          el("button", { class: "btn-link danger", onclick: () => deleteBtn(`/admin/api/users/${it.id}`, "users", c).onclick() }, "删除"),
        ]),
      ]
    )
  );
  setTotal("users", r.data.total);
}

async function toggleUser(c, it) {
  try {
    await api("PATCH", `/admin/api/users/${it.id}`, { is_active: !it.is_active });
    toast("已更新", "success");
    loadUsers(c);
  } catch (e) {
    toast(e.message, "error");
  }
}

function showUserModal(c, existing) {
  const mask = el("div", { class: "modal-mask" });
  const isEdit = !!existing;
  const nameInput = el("input", { class: "input", value: isEdit ? existing.username : "", placeholder: "username" });
  const pwInput = el("input", { class: "input", type: "password", placeholder: isEdit ? "留空不改" : "password" });
  const roleSel = el("select", { class: "select" },
    ["user", "admin"].map((r) => el("option", { value: r, selected: isEdit && existing.role === r ? "selected" : null }, r))
  );
  const m = el("div", { class: "modal" }, [
    el("h3", {}, isEdit ? "编辑用户" : "新建用户"),
    el("div", { class: "field" }, [el("label", {}, "用户名"), nameInput]),
    el("div", { class: "field" }, [el("label", {}, "密码"), pwInput]),
    el("div", { class: "field" }, [el("label", {}, "角色"), roleSel]),
    el("div", { class: "actions" }, [
      el("button", { class: "btn btn-ghost", onclick: () => mask.remove() }, "取消"),
      el("button", {
        class: "btn btn-primary",
        onclick: async () => {
          const payload = { username: nameInput.value.trim(), role: roleSel.value };
          if (pwInput.value) payload.password = pwInput.value;
          try {
            if (isEdit) {
              await api("PATCH", `/admin/api/users/${existing.id}`, payload);
            } else {
              await api("POST", "/admin/api/users", payload);
            }
            mask.remove();
            toast("已保存", "success");
            loadUsers(c);
          } catch (e) {
            toast(e.message, "error");
          }
        },
      }, "保存"),
    ]),
  ]);
  mask.appendChild(m);
  document.getElementById("overlay").appendChild(mask);
}

/* ---- 调用异常 ---- */
async function renderErrors(c) {
  const isAdmin = State.user.role === "admin";
  const toolbar = el("div", { class: "toolbar" }, [
    el("select", { class: "select", style: "width:auto", id: "errStatus", onchange: () => loadErrors(c) }, [
      el("option", { value: "" }, "全部状态"),
      el("option", { value: "open" }, "未处理"),
      el("option", { value: "closed" }, "已处理"),
    ]),
  ]);
  c.appendChild(card("调用异常", [toolbar, el("div", { id: "errTable" }), paginationBar("errors")]));
  await loadErrors(c);
}

async function loadErrors(c) {
  const status = document.getElementById("errStatus")?.value || "";
  let r;
  try {
    r = await api("GET", `/admin/api/errors?page=${State.page.errors || 1}&size=${PAGE_SIZE}&status=${status}`);
  } catch (e) {
    toast(e.message, "error");
    return;
  }
  const t = document.getElementById("errTable");
  t.innerHTML = "";
  t.appendChild(
    buildTable(
      ["工具", "错误类型", "状态", "次数", "Owner", "时间", "操作"],
      r.data.items,
      (it) => [
        el("td", {}, it.tool_name),
        el("td", {}, it.error_type),
        el("td", {}, el("span", { class: `badge ${it.status}` }, it.status === "open" ? "未处理" : "已处理")),
        el("td", {}, String(it.occurrences)),
        el("td", {}, (it.owner_id || "").slice(0, 8)),
        el("td", {}, fmtTime(it.created_at)),
        el("td", {}, [
          el("button", { class: "btn-link", onclick: () => showErrDetail(it) }, "详情"),
          " ",
          it.status === "open"
            ? el("button", { class: "btn-link", onclick: () => closeErr(c, it) }, "标记处理")
            : null,
          " ",
          deleteBtn(`/admin/api/errors/${it.id}`, "errors", c),
        ]),
      ]
    )
  );
  setTotal("errors", r.data.total);
}

async function closeErr(c, it) {
  try {
    await api("PATCH", `/admin/api/errors/${it.id}/close`);
    toast("已标记处理", "success");
    loadErrors(c);
  } catch (e) {
    toast(e.message, "error");
  }
}

function showErrDetail(it) {
  const mask = el("div", { class: "drawer-mask", onclick: (e) => { if (e.target === mask) mask.remove(); } });
  const d = el("div", { class: "drawer" }, [
    el("h3", {}, "异常详情"),
    el("div", { class: "kv" }, [
      el("div", { class: "k" }, "工具名"), el("div", { class: "v" }, it.tool_name),
      el("div", { class: "k" }, "错误类型"), el("div", { class: "v" }, it.error_type),
      el("div", { class: "k" }, "状态"), el("div", { class: "v" }, it.status),
      el("div", { class: "k" }, "出现次数"), el("div", { class: "v" }, String(it.occurrences)),
      el("div", { class: "k" }, "Owner"), el("div", { class: "v" }, it.owner_id),
      el("div", { class: "k" }, "时间"), el("div", { class: "v" }, fmtTime(it.created_at)),
    ]),
    el("div", { class: "field" }, [
      el("label", {}, "错误信息"),
      el("div", { class: "code-block" }, it.error_msg || "—"),
    ]),
    el("button", { class: "btn btn-ghost", onclick: () => mask.remove() }, "关闭"),
  ]);
  mask.appendChild(d);
  document.getElementById("overlay").appendChild(mask);
}

/* ---- 系统运维（admin） ---- */
async function renderOps(c) {
  if (State.user.role !== "admin") {
    c.appendChild(el("div", { class: "empty" }, "无权限"));
    return;
  }
  let cfg = {}, tools = { data: { tools: [] } };
  try {
    [cfg, tools] = await Promise.all([
      api("GET", "/admin/api/system/config"),
      api("GET", "/admin/api/system/tools"),
    ]);
  } catch (e) {
    toast(e.message, "error");
  }
  const cfgRows = Object.entries(cfg.data || {}).map(([k, v]) =>
    el("tr", {}, [el("td", {}, k), el("td", {}, String(v.ok !== undefined ? (v.ok ? "✓" : "✗") : v)), el("td", {}, v.detail || "")])
  );
  const toolRows = (tools.data.tools || []).map((t) => el("tr", {}, [el("td", {}, t.name || ""), el("td", {}, t.description || "")]));
  c.appendChild(card("配置诊断", [el("div", { class: "table-wrap" }, [
    el("table", {}, [el("thead", {}, el("tr", {}, [el("th", {}, "项目"), el("th", {}, "状态"), el("th", {}, "说明")])), el("tbody", {}, cfgRows)]),
  ])]));
  c.appendChild(card("工具清单", [el("div", { class: "table-wrap" }, [
    el("table", {}, [el("thead", {}, el("tr", {}, [el("th", {}, "名称"), el("th", {}, "描述")])), el("tbody", {}, toolRows)]),
  ])]));
  c.appendChild(
    card("危险操作", [
      el("p", { class: "empty", style: "padding:12px 0" }, "一键重置将清空所有业务数据（保留用户），请谨慎。"),
      el("button", {
        class: "btn btn-danger",
        onclick: async () => {
          if (!(await confirmModal("重置确认", "确定清空所有文档/知识库/异常数据？此操作不可撤销。"))) return;
          try {
            await api("POST", "/admin/api/system/reset");
            toast("已重置", "success");
            switchView("dashboard");
          } catch (e) {
            toast(e.message, "error");
          }
        },
      }, "一键重置数据"),
    ])
  );
}

/* ---- 个人中心 ---- */
async function renderMe(c) {
  const oldI = el("input", { class: "input", type: "password", placeholder: "旧密码" });
  const newI = el("input", { class: "input", type: "password", placeholder: "新密码" });
  c.appendChild(
    card(`个人中心 · ${State.user.username}`, [
      el("div", { class: "field" }, [el("label", {}, "角色"), el("div", {}, State.user.role === "admin" ? "管理员" : "普通用户")]),
      el("div", { class: "field" }, [el("label", {}, "旧密码"), oldI]),
      el("div", { class: "field" }, [el("label", {}, "新密码"), newI]),
      el("button", {
        class: "btn btn-primary",
        onclick: async () => {
          try {
            await api("PATCH", "/admin/api/me/password", { old_password: oldI.value, new_password: newI.value });
            toast("密码已更新", "success");
            oldI.value = ""; newI.value = "";
          } catch (e) {
            toast(e.message, "error");
          }
        },
      }, "修改密码"),
    ])
  );
}

/* ============ 表格/分页辅助 ============ */
function buildTable(headers, rows, rowFn) {
  const thead = el("thead", {}, el("tr", {}, headers.map((h) => el("th", {}, h))));
  const tbody = el("tbody", {});
  if (!rows || !rows.length) {
    tbody.appendChild(el("tr", {}, el("td", { colspan: String(headers.length), class: "empty" }, "暂无数据")));
  } else {
    rows.forEach((r) => tbody.appendChild(el("tr", {}, rowFn(r))));
  }
  return el("div", { class: "table-wrap" }, el("table", {}, [thead, tbody]));
}

function paginationBar(key) {
  const wrap = el("div", { class: "pagination", id: `pg-${key}` }, [
    el("button", { class: "btn btn-ghost btn-sm", onclick: () => changePage(key, -1) }, "上一页"),
    el("span", { id: `pg-info-${key}` }, "第 1 页"),
    el("button", { class: "btn btn-ghost btn-sm", onclick: () => changePage(key, 1) }, "下一页"),
  ]);
  return wrap;
}

function setTotal(key, total) {
  const info = document.getElementById(`pg-info-${key}`);
  if (!info) return;
  const pg = State.page[key] || 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  info.textContent = `第 ${pg}/${pages} 页 · 共 ${total} 条`;
}

function changePage(key, delta) {
  State.page[key] = Math.max(1, (State.page[key] || 1) + delta);
  const c = document.getElementById("content");
  if (key === "docs" || key === "kb") loadDocs(c);
  else if (key === "users") loadUsers(c);
  else if (key === "errors") loadErrors(c);
}

/* ============ 启动 ============ */
bootstrap();
