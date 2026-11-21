/* KidLens AI 前端交互
 * 设计：默认用内置演示数据（双击即可看），若 FastAPI 后端在线则自动拉取真实数据。
 * API 地址：默认同源相对路径 ""（前后端由同一个 uvicorn 服务时最稳）；
 *          双击本地 html 文件时相对路径会失败，自动降级到演示数据；
 *          也可用 window.KIDLENS_API 显式指定，如 "http://localhost:8000"。
 */
(function () {
  "use strict";

  var API = window.KIDLENS_API || "";
  var isReview = window.location.pathname.indexOf("review") !== -1;
  var isLogin = window.location.pathname.indexOf("login") !== -1;
  var isEnroll = window.location.pathname.indexOf("enroll") !== -1;
  var isUsers = window.location.pathname.indexOf("users") !== -1;

  /* ---------- 登录态 / 角色 ---------- */
  var AUTH = { user: null, ready: false };
  var TEACHER_PAGES = ["import.html", "enroll.html", "users.html", "review.html"];

  function fetchAuthJSON(path, fallback) {
    return fetch(API + path, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .catch(function () { return fallback; });
  }

  function postJSON(path, body) {
    return fetch(API + path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || ("HTTP " + r.status)); });
      return r.json();
    });
  }

  /* 页面启动前先拿当前用户；未登录且非公开页则跳登录。
     教师/家长角色决定导航与写操作是否可见。 */
  function bootstrap(done) {
    fetchAuthJSON("/api/auth/me", { user: null }).then(function (data) {
      AUTH.user = data && data.user ? data.user : null;
      AUTH.ready = true;
      var path = window.location.pathname;
      var onPublic = isLogin || path.indexOf("index.html") !== -1 || /\/$/.test(path);
      if (!AUTH.user && !onPublic) {
        window.location.href = "login.html?next=" + encodeURIComponent(path.split("/").pop());
        return;
      }
      if (AUTH.user && AUTH.user.role !== "teacher") {
        var page = path.split("/").pop().split("?")[0];
        if (TEACHER_PAGES.indexOf(page) !== -1) {
          window.location.href = "gallery.html";
          return;
        }
      }
      renderNavRole();
      done();
    });
  }

  function renderNavRole() {
    var box = document.getElementById("navUser");
    if (!box) return;
    if (!AUTH.user) { box.innerHTML = '<a class="btn btn-sm btn-ghost" href="login.html">登录</a>'; return; }
    var teacher = AUTH.user.role === "teacher";

    // 家长隐藏所有教师专属入口：导航链接 + 相册页/首页的导入按钮。
    // 否则家长点"导入素材/审核台"会被 bootstrap 弹回相册，看起来像"不跳转"。
    var teacherHrefs = ["import.html", "enroll.html", "users.html", "review.html"];
    Array.prototype.forEach.call(document.querySelectorAll(".nav-links a"), function (a) {
      var href = a.getAttribute("href") || "";
      for (var i = 0; i < teacherHrefs.length; i++) {
        if (href.indexOf(teacherHrefs[i]) !== -1) { a.hidden = !teacher; break; }
      }
    });
    Array.prototype.forEach.call(
      document.querySelectorAll(".gallery-head a.btn, .cta-row a.btn[href*='import']"),
      function (b) { b.hidden = !teacher; }
    );

    var links = teacher
      ? '<a class="btn btn-sm btn-ghost" href="users.html">账号</a>'
      : '<span class="role-tag parent">家长</span>';
    box.innerHTML = links + '<span class="nav-who">' + esc(AUTH.user.name || AUTH.user.username) + '</span>' +
      '<button class="btn btn-sm btn-ghost" id="logoutBtn" type="button">退出</button>';
    var btn = document.getElementById("logoutBtn");
    if (btn) btn.addEventListener("click", function () {
      fetch(API + "/api/auth/logout", { method: "POST", credentials: "same-origin" }).then(function () {
        window.location.href = "login.html";
      });
    });
  }

  /* ---------- 演示数据（后端离线时的降级内容） ---------- */
  var DEMO = {
    persons: [
      { id: "73aeac41", name: "小宝", templates: 1, avatar: "../data/faces/xb1.JPG" }
    ],
    timeline: [
      {
        date: "2026 · 第 46 周",
        title: "游乐园的开心一天",
        text: "小宝在游乐场玩了一整天，笑得眼睛弯成月牙。从一大段录屏里，系统自己找到了这段最亮眼的瞬间。",
        tags: ["户外", "大笑", "0.52 相似度"]
      },
      {
        date: "2026 · 第 45 周",
        title: "别着发夹的小可爱",
        text: "换了新发型，别着白色发夹。虽然和基准照看起来差别不小，人脸库还是稳稳认了出来。",
        tags: ["特写", "新造型", "0.43 相似度"]
      },
      {
        date: "2026 · 第 44 周",
        title: "第一次建档",
        text: "用一张正脸照建立人物档案，提取 512 维人脸特征。这是所有故事的开始。",
        tags: ["里程碑", "建档完成"]
      }
    ],
    drafts: [
      {
        id: "r-2026-w46",
        person: "小宝",
        status: "pending",
        text: "这一周，小宝去了游乐园。戴上新发夹的样子格外精神，笑声几乎没停过。孩子长大的痕迹，藏在每一个不经意的瞬间里。",
        photos: [
          "../data/faces/xb1.JPG",
          "../data/faces/xb1.JPG",
          "../data/faces/xb1.JPG"
        ]
      },
      {
        id: "r-2026-w45",
        person: "小宝",
        status: "approved",
        text: "换发型的一周。从最初的不太适应，到后来对着镜头做鬼脸，小宝又解锁了新的一面。",
        photos: ["../data/faces/xb1.JPG", "../data/faces/xb1.JPG"]
      }
    ]
  };

  /* ---------- 工具 ---------- */
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function toast(msg) {
    var t = document.getElementById("toast");
    if (!t) return;
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.classList.remove("show"); }, 2200);
  }

  /* 尝试从后端拉数据，失败则用演示数据 */
  function isTeacher() { return AUTH.user && AUTH.user.role === "teacher"; }

  function fetchJSON(path, fallback) {
    return fetch(API + path, { credentials: "same-origin" })
      .then(function (r) {
        if (r.status === 401) {
          var page = window.location.pathname.split("/").pop();
          if (!isLogin && page !== "index.html" && page !== "") window.location.href = "login.html";
          throw new Error("HTTP 401");
        }
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .catch(function () { return fallback; });
  }

  /* ---------- 主页 ---------- */
  function initHome() {
    // Hero 播放器：点击徽章播放/暂停
    var heroVideo = document.getElementById("heroVideo");
    var heroPlay = document.getElementById("heroPlay");
    if (heroVideo && heroPlay) {
      heroPlay.addEventListener("click", function () {
        if (heroVideo.paused) { heroVideo.play(); heroPlay.textContent = "❚❚"; }
        else { heroVideo.pause(); heroPlay.textContent = "▶"; }
      });
      heroVideo.addEventListener("click", function () { heroPlay.click(); });
    }

    // 时间轴：先用演示数据渲染，再用后端数据覆盖
    renderTimeline(DEMO.timeline);
    fetchJSON("/api/reports/73aeac41", null).then(function (data) {
      if (Array.isArray(data) && data.length) {
        renderTimeline(data.map(function (d) {
          return {
            date: d.week || d.created_at || "最近更新",
            title: d.title || "本周成长记录",
            text: d.summary || d.content || "",
            tags: d.tags || []
          };
        }));
      }
    });

    function renderTimeline(items) {
      var box = document.getElementById("timelineList");
      if (!box) return;
      box.innerHTML = "";
      items.forEach(function (it) {
        var node = el("div", "tl-item");
        node.innerHTML =
          '<div class="tl-date">' + esc(it.date) + "</div>" +
          "<h3>" + esc(it.title) + "</h3>" +
          "<p>" + esc(it.text) + "</p>" +
          '<div class="tl-tags">' + (it.tags || []).map(function (t) {
            return '<span class="tag">' + esc(t) + "</span>";
          }).join("") + "</div>";
        box.appendChild(node);
      });
    }
  }

  /* ---------- 审核台 ---------- */
  function initReview() {
    var personBox = document.getElementById("personList");
    var draftBox = document.getElementById("draftList");
    if (!personBox || !draftBox) return;

    var state = {
      persons: DEMO.persons.slice(),
      drafts: JSON.parse(JSON.stringify(DEMO.drafts)),
      active: "73aeac41",
      removedPhotos: {}
    };

    function renderPersons() {
      personBox.innerHTML = "";
      state.persons.forEach(function (p) {
        var item = el("div", "person-item" + (p.id === state.active ? " active" : ""));
        var avatar = p.avatar
          ? '<img class="avatar" src="' + esc(p.avatar) + '" alt="">'
          : '<div class="avatar-ph">👤</div>';
        item.innerHTML = avatar +
          '<div class="person-meta"><b>' + esc(p.name) + "</b><small>" +
          (p.templates || 0) + " 个模板 · " + (p.clips || 0) + " 段集锦</small></div>";
        item.addEventListener("click", function () {
          state.active = p.id;
          renderPersons();
          renderDrafts();
        });
        personBox.appendChild(item);
      });
    }

    function renderDrafts() {
      draftBox.innerHTML = "";
      var activePerson = null;
      for (var i = 0; i < state.persons.length; i++) {
        if (state.persons[i].id === state.active) { activePerson = state.persons[i].name; break; }
      }
      var list = state.drafts.filter(function (d) {
        return !activePerson || d.person === activePerson || state.persons.length === 1;
      });
      if (!list.length) {
        draftBox.appendChild(el("p", "hint", "暂无待审核周报"));
        return;
      }
      list.forEach(function (d) {
        var card = el("div", "draft-card");
        var approved = d.status === "approved";
        var statusCls = approved ? "status-approved" : "status-pending";
        var statusTxt = approved ? "已通过" : "待审核";

        var top = el("div", "draft-top");
        top.innerHTML = "<b>" + esc(d.person) + " · " + esc(d.id) + "</b>" +
          '<span class="status ' + statusCls + '">' + statusTxt + "</span>";
        card.appendChild(top);

        var ta = el("textarea");
        ta.value = d.text;
        ta.setAttribute("aria-label", "周报文案");
        card.appendChild(ta);

        var strip = el("div", "photo-strip");
        d.photos.forEach(function (src, idx) {
          var key = d.id + "-" + idx;
          var photo = el("div", "photo" + (state.removedPhotos[key] ? " removed" : ""));
          photo.innerHTML = '<img src="' + esc(src) + '" alt="配图 ' + (idx + 1) + '">' +
            '<button class="drop" type="button">剔除</button>';
          photo.querySelector(".drop").addEventListener("click", function () {
            state.removedPhotos[key] = !state.removedPhotos[key];
            renderDrafts();
            toast(state.removedPhotos[key] ? "已剔除该配图" : "已恢复该配图");
          });
          strip.appendChild(photo);
        });
        card.appendChild(strip);

        var actions = el("div", "draft-actions");
        if (!approved) {
          var ok = el("button", "btn btn-mini btn-approve", "✓ 审核通过");
          ok.addEventListener("click", function () {
            d.status = "approved";
            d.text = ta.value;
            renderDrafts();
            toast("周报已通过，已归档到成长手账");
            // 通知后端（若在线），带编辑后的文案
            fetch(API + "/api/reports/" + encodeURIComponent(d.id) + "/approve", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ summary: ta.value })
            }).catch(function () {});
          });
          actions.appendChild(ok);

          var reject = el("button", "btn btn-mini btn-reject", "打回重做");
          reject.addEventListener("click", function () {
            toast("已打回，等待重新生成");
          });
          actions.appendChild(reject);
        }
        var save = el("button", "btn btn-mini btn-ghost", "保存文案");
        save.addEventListener("click", function () {
          d.text = ta.value;
          toast("文案已保存");
        });
        actions.appendChild(save);
        card.appendChild(actions);

        draftBox.appendChild(card);
      });
    }

    renderPersons();
    renderDrafts();

    // 后端在线时用真实人物列表 + 真实周报覆盖演示数据
    fetchJSON("/api/persons", null).then(function (data) {
      if (Array.isArray(data) && data.length) {
        state.persons = data.map(function (p) {
          return { id: p.id, name: p.name, templates: p.template_count || 0, clips: p.clip_count || 0, avatar: "" };
        });
        state.active = state.persons[0].id;
        renderPersons();
        // 再拉该人物的真实周报
        var name = state.persons[0].name;
        fetchJSON("/api/reports/" + encodeURIComponent(name), null).then(function (reports) {
          if (Array.isArray(reports) && reports.length) {
            state.drafts = reports.map(function (r) {
              return {
                id: r.id, person: r.person, status: r.status,
                text: r.summary || "", title: r.title || "",
                photos: r.photos || [], tags: r.tags || []
              };
            });
          }
          renderDrafts();
        });
      }
    });
  }

  /* ---------- 判断当前页 ---------- */
  var isImport = window.location.pathname.indexOf("import") !== -1;
  var isGallery = window.location.pathname.indexOf("gallery") !== -1;

  /* ---------- 导入页 ---------- */
  function initImport() {
    var dropzone = document.getElementById("dropzone");
    var fileInput = document.getElementById("fileInput");
    var fileList = document.getElementById("fileList");
    var dateInput = document.getElementById("dateInput");
    var autoSort = document.getElementById("autoSort");
    var importBtn = document.getElementById("importBtn");
    var progressWrap = document.getElementById("progressWrap");
    var progressFill = document.getElementById("progressFill");
    var progressText = document.getElementById("progressText");
    var resultPanel = document.getElementById("resultPanel");
    var resultSummary = document.getElementById("resultSummary");
    var resultList = document.getElementById("resultList");
    var pendingBtn = document.getElementById("pendingBtn");
    var pendingPanel = document.getElementById("pendingPanel");
    var pendingList = document.getElementById("pendingList");
    if (!dropzone) return;

    var files = [];
    var pendingItems = [];

    function renderFiles() {
      fileList.innerHTML = "";
      files.forEach(function (f, idx) {
        var chip = el("span", "file-chip");
        chip.innerHTML = '<span class="fname">' + esc(f.name) + '</span><span class="x">×</span>';
        chip.querySelector(".x").addEventListener("click", function () {
          files.splice(idx, 1);
          renderFiles();
        });
        fileList.appendChild(chip);
      });
      importBtn.disabled = files.length === 0;
    }

    function addFiles(fileArr) {
      for (var i = 0; i < fileArr.length; i++) {
        var f = fileArr[i];
        var isMedia = /\.(jpe?g|png|heic|webp|mp4|mov|m4v|avi|mkv)$/i.test(f.name);
        if (isMedia) files.push(f);
      }
      renderFiles();
    }

    dropzone.addEventListener("click", function () { fileInput.click(); });
    fileInput.addEventListener("change", function () { addFiles(fileInput.files); });
    ["dragenter", "dragover"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.remove("dragover"); });
    });
    dropzone.addEventListener("drop", function (e) { addFiles(e.dataTransfer.files); });

    importBtn.addEventListener("click", function () {
      if (!files.length) return;
      importBtn.disabled = true;
      progressWrap.hidden = false;
      progressFill.style.width = "10%";
      progressText.textContent = "正在导入并识别人脸，请稍候…";

      var form = new FormData();
      files.forEach(function (f) { form.append("files", f); });
      if (dateInput.value) form.append("date", dateInput.value);
      form.append("auto_sort", autoSort.checked ? "true" : "false");

      fetch(API + "/api/import", { method: "POST", body: form })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (data) {
          progressFill.style.width = "100%";
          progressText.textContent = "导入完成";
          showResults(data.results);
          loadPending();
          toast("成功导入 " + data.imported + " 个素材");
        })
        .catch(function (e) {
          progressText.textContent = "导入失败：" + e.message;
          toast("导入失败，请检查后端是否启动");
        })
        .finally(function () { importBtn.disabled = false; });
    });

    function showResults(results) {
      resultPanel.hidden = false;
      var ok = results.filter(function (r) { return r.status === "confirmed"; }).length;
      var pend = results.length - ok;
      resultSummary.textContent = "✓ " + ok + " 个已自动归档" + (pend ? " · " + pend + " 个待确认" : "");
      resultList.innerHTML = "";
      results.forEach(function (r) {
        var row = el("div", "result-row");
        var tag = r.status === "confirmed"
          ? '<span class="rtag">' + esc(r.persons.join("、")) + ' · ' + esc(r.date) + '</span>'
          : '<span class="rtag pending">待确认</span>';
        row.innerHTML = '<span class="rname">' + esc(r.filename) + "</span>" + tag;
        resultList.appendChild(row);
      });
      pendingBtn.hidden = pend === 0;
    }

    pendingBtn.addEventListener("click", function () {
      pendingPanel.hidden = false;
      pendingPanel.scrollIntoView({ behavior: "smooth" });
    });

    function loadPending() {
      fetchJSON("/api/pending", []).then(function (items) {
        pendingItems = items || [];
        pendingList.innerHTML = "";
        pendingItems.forEach(function (it) {
          var row = el("div", "pending-item");
          var thumb = it.kind === "video"
            ? '<div class="pthumb pthumb-video">🎬</div>'
            : '<img class="pthumb" src="' + esc(it.url) + '" alt="">';
          row.innerHTML = thumb +
            '<div class="pinfo"><b>' + esc(it.filename) + "</b><small>" + esc(it.date) + "</small></div>";
          var assign = el("div", "assign-row");
          var sel = document.createElement("select");
          sel.className = "assign-select";
          fetchJSON("/api/persons", []).then(function (ps) {
            (ps || []).forEach(function (p) {
              var opt = document.createElement("option");
              opt.value = p.name; opt.textContent = p.name;
              sel.appendChild(opt);
            });
          });
          var newName = document.createElement("input");
          newName.className = "text-input";
          newName.placeholder = "或新建孩子名字";
          newName.style.maxWidth = "150px";
          var ok = el("button", "btn btn-mini", "归入并学习");
          ok.addEventListener("click", function () {
            var person = newName.value.trim() || sel.value;
            if (!person) { toast("请选择或输入孩子名字"); return; }
            fetch(API + "/api/pending/" + encodeURIComponent(it.id) + "/assign", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ person: person, learn: true })
            }).then(function (r) { return r.json(); }).then(function () {
              toast("已归入 " + person + "，并学进人脸库");
              loadPending();
            }).catch(function () { toast("归类失败"); });
          });
          assign.appendChild(sel);
          assign.appendChild(newName);
          assign.appendChild(ok);
          row.appendChild(assign);
          pendingList.appendChild(row);
        });
      });
    }
    loadPending();
  }

  /* ---------- 相册页 ---------- */
  function initGallery() {
    var peopleList = document.getElementById("peopleList");
    var dateGroups = document.getElementById("dateGroups");
    var galleryEmpty = document.getElementById("galleryEmpty");
    var pendingBadge = document.getElementById("pendingBadge");
    var showPending = document.getElementById("showPending");
    if (!peopleList) return;

    var state = { people: [], active: "", pendingCount: 0 };
    var teacher = isTeacher();

    // 家长：隐藏写操作入口 + 备份按钮
    if (!teacher) {
      var addBtn = document.querySelector(".gallery-head a.btn");
      if (addBtn) addBtn.hidden = true;
      var pendingBtn = document.getElementById("showPending");
      if (pendingBtn) pendingBtn.hidden = true;
      var emptyCta = document.querySelector("#galleryEmpty a.btn");
      if (emptyCta) emptyCta.hidden = true;
      var backupBtnParent = document.getElementById("backupBtn");
      if (backupBtnParent) backupBtnParent.hidden = true;
    }

    // 教师：一键备份导出（打包 data → zip 下载）
    var backupBtn = document.getElementById("backupBtn");
    if (backupBtn && teacher) {
      backupBtn.addEventListener("click", function () {
        var old = backupBtn.textContent;
        backupBtn.disabled = true;
        backupBtn.textContent = "打包中…";
        fetch(API + "/api/backup/export", { credentials: "same-origin" })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || ("HTTP " + r.status)); });
            return r.blob().then(function (blob) {
              var cd = r.headers.get("Content-Disposition") || "";
              var m = cd.match(/filename="([^"]+)"/);
              var fname = m ? m[1] : ("kidlens_backup_" + Date.now() + ".zip");
              var url = URL.createObjectURL(blob);
              var a = document.createElement("a");
              a.href = url; a.download = fname;
              document.body.appendChild(a); a.click();
              document.body.removeChild(a);
              setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
              toast("备份已下载：" + fname);
            });
          })
          .catch(function (e) { toast("备份失败：" + e.message); })
          .finally(function () { backupBtn.disabled = false; backupBtn.textContent = old; });
      });
    }

    function loadOverview() {
      fetchJSON("/api/gallery", { people: [], pending_count: 0 }).then(function (d) {
        state.people = d.people || [];
        state.pendingCount = d.pending_count || 0;
        renderPeople();
        showPending.hidden = state.pendingCount === 0;
        pendingBadge.textContent = state.pendingCount;
        if (state.people.length) {
          state.active = state.people[0].name;
          renderPerson();
        } else {
          galleryEmpty.hidden = false;
          dateGroups.innerHTML = "";
        }
      });
    }

    function renderPeople() {
      peopleList.innerHTML = "";
      state.people.forEach(function (p) {
        var item = el("div", "person-link" + (p.name === state.active ? " active" : ""));
        item.innerHTML = '<span class="pdot">😊</span><span>' + esc(p.name) +
          '</span><span class="pnum">' + p.total + "</span>";
        item.addEventListener("click", function () {
          state.active = p.name; renderPeople(); renderPerson();
        });
        peopleList.appendChild(item);
      });
    }

    function renderPerson() {
      if (!state.active) return;
      galleryEmpty.hidden = true;
      dateGroups.innerHTML = "";
      fetchJSON("/api/gallery/person/" + encodeURIComponent(state.active), { dates: [] }).then(function (d) {
        var groups = d.dates || [];
        if (!groups.length) {
          dateGroups.innerHTML = '<div class="gallery-empty"><b>还没有素材</b><p>给 ' +
            esc(state.active) + " 导入一些照片吧。</p></div>";
          return;
        }
        groups.forEach(function (g) {
          var box = el("div", "date-group");
          var srcLabel = g.items[0] && g.items[0].date_source === "manual" ? "手动指定" : "自动读取";
          box.innerHTML = '<div class="date-heading"><h3>' + esc(g.date) +
            '</h3><span class="date-count">' + g.count + ' 个</span><span class="date-src">' + srcLabel + "</span></div>";
          var wall = el("div", "photo-wall");
          g.items.forEach(function (it) {
            var tile = el("div", "photo-tile");
            var media = it.kind === "video"
              ? '<video src="' + esc(it.url) + '" muted preload="metadata"></video><span class="tile-play">▶</span><span class="tile-badge">视频</span>'
              : '<img src="' + esc(it.url) + '" alt="' + esc(it.filename) + '" loading="lazy">';
            tile.innerHTML = media + (teacher
              ? '<div class="tile-date-edit"><button class="tile-date-btn" type="button">📅 改日期</button></div>'
              : "");
            tile.addEventListener("click", function (e) {
              if (e.target.classList.contains("tile-date-btn")) {
                e.stopPropagation();
                var nd = window.prompt("改成哪一天？（格式 YYYY-MM-DD）", g.date);
                if (nd && /^\d{4}-\d{2}-\d{2}$/.test(nd)) {
                  fetch(API + "/api/gallery/" + encodeURIComponent(it.id) + "/date", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ date: nd })
                  }).then(function (r) { return r.json(); }).then(function () {
                    toast("日期已改为 " + nd); renderPerson();
                  });
                }
                return;
              }
              openLightbox(it, g.date);
            });
            wall.appendChild(tile);
          });
          box.appendChild(wall);
          dateGroups.appendChild(box);
        });
      });
    }

    showPending.addEventListener("click", function () {
      window.location.href = "import.html";
    });

    function openLightbox(item, date) {
      var lb = document.getElementById("lightbox");
      var stage = document.getElementById("lightboxStage");
      var meta = document.getElementById("lightboxMeta");
      lb.hidden = false;
      stage.innerHTML = item.kind === "video"
        ? '<video src="' + esc(item.url) + '" controls autoplay playsinline></video>'
        : '<img src="' + esc(item.url) + '" alt="' + esc(item.filename) + '">';
      meta.textContent = item.filename + " · " + date + (item.similarity ? " · 相似度 " + item.similarity.toFixed(2) : "");
    }
    function closeLightbox() {
      var lb = document.getElementById("lightbox");
      lb.hidden = true;
      document.getElementById("lightboxStage").innerHTML = "";
    }
    document.getElementById("lightboxClose").addEventListener("click", closeLightbox);
    document.getElementById("lightbox").addEventListener("click", function (e) {
      if (e.target.id === "lightbox") closeLightbox();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeLightbox();
    });

    loadOverview();
  }

  /* ---------- 登录页 ---------- */
  function initLogin() {
    var form = document.getElementById("loginForm");
    if (!form) return;
    var err = document.getElementById("authError");
    Array.prototype.forEach.call(document.querySelectorAll(".use-account"), function (b) {
      b.addEventListener("click", function () {
        document.getElementById("username").value = b.getAttribute("data-u");
        document.getElementById("password").value = b.getAttribute("data-p");
      });
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      err.hidden = true;
      postJSON("/api/auth/login", {
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value
      }).then(function (data) {
        var next = new URLSearchParams(window.location.search).get("next");
        var dest = next ? next : (data.user.role === "teacher" ? "gallery.html" : "gallery.html");
        window.location.href = dest;
      }).catch(function (ex) {
        err.textContent = ex.message || "登录失败";
        err.hidden = false;
      });
    });
  }

  /* ---------- 建档页（教师） ---------- */
  function initEnroll() {
    var dropzone = document.getElementById("enrollDropzone");
    var input = document.getElementById("enrollInput");
    var fileList = document.getElementById("enrollFileList");
    var btn = document.getElementById("enrollBtn");
    if (!dropzone) return;

    var files = [];
    function renderFiles() {
      fileList.innerHTML = "";
      files.forEach(function (f, idx) {
        var chip = el("span", "file-chip");
        chip.innerHTML = '<span class="fname">' + esc(f.name) + '</span><span class="x">×</span>';
        chip.querySelector(".x").addEventListener("click", function () { files.splice(idx, 1); renderFiles(); });
        fileList.appendChild(chip);
      });
      btn.disabled = files.length === 0 || !document.getElementById("childName").value.trim();
    }
    function addFiles(arr) {
      for (var i = 0; i < arr.length; i++) {
        if (/\.(jpe?g|png|heic|webp)$/i.test(arr[i].name) && files.length < 5) files.push(arr[i]);
      }
      renderFiles();
    }
    dropzone.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () { addFiles(input.files); });
    ["dragenter", "dragover"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) { e.preventDefault(); dropzone.classList.remove("dragover"); });
    });
    dropzone.addEventListener("drop", function (e) { addFiles(e.dataTransfer.files); });
    document.getElementById("childName").addEventListener("input", renderFiles);

    btn.addEventListener("click", function () {
      var name = document.getElementById("childName").value.trim();
      if (!name || !files.length) return;
      btn.disabled = true;
      var prog = document.getElementById("enrollProgress");
      var res = document.getElementById("enrollResult");
      prog.hidden = false; res.hidden = true;
      var form = new FormData();
      form.append("name", name);
      form.append("nickname", document.getElementById("childNick").value.trim());
      files.forEach(function (f) { form.append("files", f); });
      fetch(API + "/api/enroll", { method: "POST", credentials: "same-origin", body: form })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || "HTTP " + r.status); });
          return r.json();
        })
        .then(function (data) {
          prog.hidden = true;
          res.hidden = false;
          res.textContent = "✓ " + data.name + "：" + data.action + "，现有 " + data.templates + " 个模板";
          files = []; renderFiles(); loadEnrolled();
          toast("建档完成，可以导入素材了");
        })
        .catch(function (ex) {
          prog.hidden = true;
          res.hidden = false;
          res.textContent = "建档失败：" + ex.message;
        })
        .finally(function () { btn.disabled = false; });
    });

    function loadEnrolled() {
      fetchAuthJSON("/api/persons", []).then(function (ps) {
        var box = document.getElementById("enrolledList");
        box.innerHTML = "";
        (ps || []).forEach(function (p) {
          var row = el("div", "pending-item");
          row.innerHTML = '<div class="pinfo"><b>' + esc(p.name) + '</b><small>' +
            (p.template_count || 0) + ' 个模板</small></div>';
          box.appendChild(row);
        });
        if (!(ps || []).length) box.innerHTML = '<p class="hint">还没有建档的孩子。</p>';
      });
    }
    loadEnrolled();
  }

  /* ---------- 账号管理页（教师） ---------- */
  function initUsers() {
    var addBtn = document.getElementById("addParentBtn");
    if (!addBtn) return;
    var children = [];
    var choices = document.getElementById("childChoices");
    var parentBox = document.getElementById("parentList");

    function renderChoices() {
      choices.innerHTML = "";
      children.forEach(function (name) {
        var lab = el("label", "child-choice");
        lab.innerHTML = '<input type="checkbox" value="' + esc(name) + '"><span>' + esc(name) + '</span>';
        choices.appendChild(lab);
      });
      if (!children.length) choices.innerHTML = '<p class="hint">先去「建立档案」添加孩子。</p>';
    }
    function selectedChildren() {
      return Array.prototype.filter.call(choices.querySelectorAll("input:checked"), function (i) { return i.value; })
        .map(function (i) { return i.value; });
    }
    function loadParents() {
      fetchAuthJSON("/api/auth/parents", []).then(function (ps) {
        parentBox.innerHTML = "";
        (ps || []).forEach(function (p) {
          var row = el("div", "pending-item");
          var names = (p.children || []).join("、") || "（未绑定）";
          row.innerHTML = '<div class="pinfo"><b>' + esc(p.name) + ' <small>@' + esc(p.username) + '</small></b>' +
            '<small>可见：' + esc(names) + '</small></div>';
          var del = el("button", "btn btn-mini btn-ghost", "删除");
          del.addEventListener("click", function () {
            if (!window.confirm("删除家长账号 " + p.username + "？")) return;
            fetch(API + "/api/auth/parents/" + encodeURIComponent(p.username),
              { method: "DELETE", credentials: "same-origin" })
              .then(function () { toast("已删除"); loadParents(); });
          });
          row.appendChild(del);
          parentBox.appendChild(row);
        });
        if (!(ps || []).length) parentBox.innerHTML = '<p class="hint">还没有家长账号。</p>';
      });
    }
    fetchAuthJSON("/api/auth/children", []).then(function (d) { children = d || []; renderChoices(); });
    loadParents();

    function checkReady() {
      addBtn.disabled = !document.getElementById("newUsername").value.trim() ||
        !document.getElementById("newPassword").value.trim();
    }
    ["newUsername", "newPassword"].forEach(function (id) {
      document.getElementById(id).addEventListener("input", checkReady);
    });
    addBtn.addEventListener("click", function () {
      var body = {
        username: document.getElementById("newUsername").value.trim(),
        password: document.getElementById("newPassword").value.trim(),
        name: document.getElementById("newName").value.trim(),
        children: selectedChildren()
      };
      postJSON("/api/auth/parents", body).then(function () {
        toast("家长账号已创建");
        document.getElementById("newUsername").value = "";
        document.getElementById("newPassword").value = "";
        document.getElementById("newName").value = "";
        checkReady(); loadParents();
      }).catch(function (ex) { toast("创建失败：" + ex.message); });
    });
  }

  /* ---------- 启动 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("toast")) {
      var toastBox = el("div", "toast");
      toastBox.id = "toast";
      document.body.appendChild(toastBox);
    }
    function start() {
      if (isLogin) initLogin();
      else if (isEnroll) initEnroll();
      else if (isUsers) initUsers();
      else if (isImport) initImport();
      else if (isGallery) initGallery();
      else if (isReview) initReview();
      else initHome();
    }
    bootstrap(start);
  });
})();
