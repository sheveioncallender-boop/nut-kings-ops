(() => {
  "use strict";
  const PROFILE_KEY = "nutkings_role_profile_v1_3_0";
  const PLAN_KEY = "nutkings_dispatch_plan_v1_3_0";
  const state = { profile: null, plan: null, selectedVan: 0, selectedArea: 0, nativeFetch: window.fetch.bind(window) };
  const labels = {
    manager: "Manager / Administrator",
    office_receiving: "Office Receiving",
    raw_material_issue: "Raw Materials Employee",
    finished_goods_entry: "Finished Goods Entry",
    dispatcher: "Dispatcher",
  };
  const operationMatchers = [
    ["RM_RECEIPT", /RM_RECEIPT|RAW MATERIALS? RECEIV|RECEIVE RAW/i],
    ["RM_ISSUE", /RM_ISSUE|RAW MATERIALS? ISSU|ISSUE RAW/i],
    ["FG_RECEIPT", /FG_RECEIPT|FINISHED GOODS (RECEIV|ENTRY)|ENTER FINISHED/i],
    ["FG_TRUCK", /FG_TRUCK|LOAD (TRUCK|VAN)|VAN LOAD|DISPATCH FROM WAREHOUSE/i],
    ["TRUCK_DELIVERY", /TRUCK_DELIVERY|VAN DELIVERY|CUSTOMER DELIVERY/i],
    ["TRUCK_RETURN", /TRUCK_RETURN|VAN RETURN|RETURN FROM (TRUCK|VAN)/i],
  ];
  function esc(value) { return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c])); }
  async function rpc(url, params = {}) {
    const response = await state.nativeFetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({jsonrpc: "2.0", method: "call", params, id: Date.now()}),
    });
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    const payload = await response.json();
    if (payload.error) throw new Error(payload.error?.data?.message || payload.error?.message || "Request failed");
    return payload.result;
  }
  function cached(key) { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch (_) { return null; } }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {} }
  function inferOperation(element) {
    const source = [element?.dataset?.operation, element?.dataset?.operationCode, element?.dataset?.code, element?.getAttribute?.("href"), element?.textContent].filter(Boolean).join(" ");
    const match = operationMatchers.find(([, regex]) => regex.test(source));
    return match ? match[0] : "";
  }
  function can(code) { return !code || !state.profile || state.profile.operations?.[code] !== false; }
  function applyRoleVisibility(root = document) {
    if (!state.profile) return;
    root.querySelectorAll("[data-operation],[data-operation-code],[data-code],button,a,.operation-card,.nk-operation-card").forEach(el => {
      const code = inferOperation(el);
      if (!code) return;
      const denied = !can(code);
      el.classList.toggle("nk-operation-denied", denied);
      if (denied) { el.setAttribute("aria-hidden", "true"); el.setAttribute("tabindex", "-1"); }
      else { el.removeAttribute("aria-hidden"); if (el.getAttribute("tabindex") === "-1") el.removeAttribute("tabindex"); }
    });
  }
  function headerAnchor() { return document.querySelector("header,.nk-header,.app-header,.workspace-header,nav") || document.body.firstElementChild; }
  function renderRoleStrip() {
    if (!state.profile || document.querySelector(".nk-role-strip")) return;
    const strip = document.createElement("section");
    strip.className = "nk-role-strip";
    const roleCodes = state.profile.roles?.length ? state.profile.roles : ["manager"];
    strip.innerHTML = `<div><strong>${esc(state.profile.user?.name || "Nut Kings User")}</strong><small>${esc(state.profile.enforcement_enabled ? "Role-controlled operational access is active" : "Role configuration mode — enforcement is not yet enabled")}</small></div><div class="nk-role-badges">${roleCodes.map(r => `<span class="nk-role-badge ${state.profile.enforcement_enabled ? "" : "nk-soft"}">${esc(labels[r] || r)}</span>`).join("")}</div>`;
    const anchor = headerAnchor();
    if (anchor?.parentNode) anchor.parentNode.insertBefore(strip, anchor.nextSibling); else document.body.prepend(strip);
  }
  function activeOperation() {
    const active = document.querySelector("[data-operation].active,[data-operation-code].active,.operation-card.active,.nk-operation-card.active,[aria-selected='true']");
    const code = inferOperation(active);
    if (code) return code;
    const text = `${location.hash} ${location.pathname} ${document.querySelector("h1,h2,.page-title")?.textContent || ""}`;
    const match = operationMatchers.find(([, regex]) => regex.test(text));
    return match ? match[0] : "";
  }
  function ensureGuide() {
    if (!state.profile?.operations?.FG_TRUCK && !state.profile?.is_manager) return null;
    let guide = document.querySelector(".nk-demand-guide");
    if (guide) return guide;
    guide = document.createElement("section");
    guide.className = "nk-demand-guide";
    guide.hidden = true;
    guide.innerHTML = `<div class="nk-demand-head"><div><div class="nk-demand-kicker">SERVICE AREA DEMAND</div><h3>Van Load Guide</h3><p>Adjust the product mix and quantities from what sells and returns in this service area.</p></div></div><div class="nk-demand-grid"><label>Van<select id="nk-demand-van"><option value="">Select van</option></select></label><label>Service Area<select id="nk-demand-area"><option value="">Select service area</option></select></label><button type="button" id="nk-demand-generate">Generate Suggestions</button></div><div class="nk-demand-status" id="nk-demand-status">Select a van and service area. Suggestions never move stock until the dispatcher confirms the normal load.</div><div id="nk-demand-results"></div>`;
    const main = document.querySelector("main,.nk-main,.app-main,.workspace-main,#app") || document.body;
    main.prepend(guide);
    const vanSelect = guide.querySelector("#nk-demand-van");
    const areaSelect = guide.querySelector("#nk-demand-area");
    (state.profile.vans || []).forEach(v => vanSelect.insertAdjacentHTML("beforeend", `<option value="${v.id}" data-area="${v.primary_service_area_id || ""}">${esc(v.name)}</option>`));
    (state.profile.service_areas || []).forEach(a => areaSelect.insertAdjacentHTML("beforeend", `<option value="${a.id}">${esc(a.name)} (${esc(a.code)})</option>`));
    vanSelect.addEventListener("change", () => {
      state.selectedVan = Number(vanSelect.value || 0);
      const areaId = Number(vanSelect.selectedOptions[0]?.dataset?.area || 0);
      if (areaId) { areaSelect.value = String(areaId); state.selectedArea = areaId; }
      syncExistingVanSelect(state.selectedVan);
    });
    areaSelect.addEventListener("change", () => { state.selectedArea = Number(areaSelect.value || 0); });
    guide.querySelector("#nk-demand-generate").addEventListener("click", generatePlan);
    return guide;
  }
  function syncExistingVanSelect(vanId) {
    document.querySelectorAll("select[id*='truck' i],select[id*='van' i],select[name*='truck' i],select[name*='van' i]").forEach(select => {
      if (select.closest(".nk-demand-guide")) return;
      const matching = [...select.options].find(o => Number(o.value) === Number(vanId));
      if (matching) { select.value = matching.value; select.dispatchEvent(new Event("change", {bubbles:true})); }
    });
  }
  function updateGuideVisibility() {
    const guide = ensureGuide();
    if (!guide) return;
    const op = activeOperation();
    const dispatchVisible = op === "FG_TRUCK" || /dispatch|van load|load truck/i.test(document.body.innerText || "");
    guide.hidden = !dispatchVisible;
  }
  function setStatus(message, offline = false) {
    const el = document.querySelector("#nk-demand-status");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("nk-demand-offline", offline);
  }
  async function generatePlan() {
    const guide = ensureGuide();
    const van = Number(guide.querySelector("#nk-demand-van").value || 0);
    const area = Number(guide.querySelector("#nk-demand-area").value || 0);
    if (!van || !area) { setStatus("Select both a van and service area."); return; }
    state.selectedVan = van; state.selectedArea = area;
    const button = guide.querySelector("#nk-demand-generate");
    button.disabled = true; setStatus("Calculating recent sales, returns, van stock and warehouse availability...");
    try {
      state.plan = await rpc("/nutkings/api/dispatch-plan/generate", {truck_id: van, service_area_id: area});
      save(PLAN_KEY, state.plan); renderPlan(state.plan); setStatus(`Plan ${state.plan.name} generated from ${state.plan.history_trip_count} completed service-area trip(s).`);
    } catch (error) {
      const fallback = cached(PLAN_KEY);
      if (fallback && fallback.van?.id === van && fallback.service_area?.id === area) {
        state.plan = fallback; renderPlan(fallback); setStatus("Offline: showing the last synchronized demand plan for this van and area.", true);
      } else setStatus(error.message || "Unable to generate suggestions.", !navigator.onLine);
    } finally { button.disabled = false; }
  }
  function renderPlan(plan) {
    const target = document.querySelector("#nk-demand-results");
    if (!target) return;
    const lines = plan.lines || [];
    if (!lines.length) { target.innerHTML = `<div class="nk-demand-status">No product history is available yet. The dispatcher can continue with a manual load while the system builds service-area history.</div>`; return; }
    target.innerHTML = `<div class="nk-demand-summary"><span><strong>${esc(plan.history_trip_count)}</strong> history trips</span><span><strong>${esc(plan.suggested_total_qty)}</strong> suggested units</span><span><strong>${esc(plan.actual_total_qty)}</strong> planned units</span>${plan.insufficient_history ? '<span><strong>Insufficient history</strong> — manual quantities required</span>' : ''}</div><div class="nk-demand-table-wrap"><table class="nk-demand-table"><thead><tr><th>Product</th><th>On Van</th><th>Last Sold</th><th>Last Returned</th><th>Avg. Sold</th><th>FG Available</th><th>Suggested</th><th>Actual Load</th><th>Direction</th></tr></thead><tbody>${lines.map(line => `<tr data-line-id="${line.id}"><td><strong>${esc(line.product_name)}</strong><br><small>${esc(line.barcode || line.internal_reference || "")}</small></td><td>${line.current_van_qty}</td><td>${line.last_sold_qty}</td><td>${line.last_returned_qty}</td><td>${Number(line.weighted_average_sold || 0).toFixed(1)}</td><td class="${line.warehouse_shortage ? 'nk-demand-shortage' : ''}">${line.warehouse_available_qty}</td><td>${line.suggested_load_qty}</td><td><input class="nk-demand-qty" type="number" min="0" step="1" value="${line.actual_load_qty}" aria-label="Actual load for ${esc(line.product_name)}"></td><td><span class="nk-demand-tag ${esc(line.recommendation_status)}" title="${esc(line.recommendation_reason)}">${esc(line.recommendation_status)}</span></td></tr>`).join("")}</tbody></table></div><div class="nk-demand-actions"><button type="button" class="secondary" id="nk-demand-use-suggested">Use Suggested Quantities</button><button type="button" id="nk-demand-save">Save Dispatch Plan</button><button type="button" id="nk-demand-approve">Approve for Loading</button></div>`;
    target.querySelector("#nk-demand-use-suggested").addEventListener("click", () => {
      target.querySelectorAll("tbody tr").forEach((row, index) => { row.querySelector("input").value = lines[index].suggested_load_qty; });
    });
    target.querySelector("#nk-demand-save").addEventListener("click", () => savePlan(false));
    target.querySelector("#nk-demand-approve").addEventListener("click", () => savePlan(true));
  }
  async function savePlan(approve) {
    if (!state.plan) return;
    const rows = [...document.querySelectorAll(".nk-demand-table tbody tr")];
    const lines = rows.map(row => ({id: Number(row.dataset.lineId), actual_load_qty: Number(row.querySelector("input")?.value || 0)}));
    setStatus(approve ? "Saving and approving the dispatcher load plan..." : "Saving the dispatcher load plan...");
    try {
      state.plan = await rpc("/nutkings/api/dispatch-plan/save", {plan_id: state.plan.id, lines, approve});
      save(PLAN_KEY, state.plan); renderPlan(state.plan); setStatus(approve ? "Load plan approved. Scan the actual products through the normal van dispatch workflow." : "Dispatch plan saved.");
    } catch (error) { setStatus(error.message || "Unable to save the plan.", !navigator.onLine); }
  }
  function installAuthorizationGuard() {
    document.addEventListener("click", event => {
      const action = event.target.closest("[data-operation],[data-operation-code],[data-code],button,a,.operation-card,.nk-operation-card");
      if (!action) return;
      const code = inferOperation(action);
      if (code && !can(code)) { event.preventDefault(); event.stopImmediatePropagation(); alert("This Nut Kings Ops login is not authorized for that operation."); }
      setTimeout(updateGuideVisibility, 80);
    }, true);
  }
  function extractRecord(result) {
    const seen = new Set();
    function walk(obj) {
      if (!obj || typeof obj !== "object" || seen.has(obj)) return null;
      seen.add(obj);
      if (obj.picking_id) return {model:"stock.picking", id:Number(obj.picking_id)};
      if (obj.trip_id) return {model:"nutkings.trip", id:Number(obj.trip_id)};
      if ((obj.model === "stock.picking" || obj.model === "nutkings.trip") && obj.id) return {model:obj.model, id:Number(obj.id)};
      for (const value of Object.values(obj)) { const found = walk(value); if (found) return found; }
      return null;
    }
    return walk(result);
  }
  function installOperationTagging() {
    window.fetch = async function(input, init = {}) {
      const response = await state.nativeFetch(input, init);
      try {
        const url = typeof input === "string" ? input : input?.url || "";
        if (state.selectedArea && state.selectedVan && /nutkings\/api/i.test(url) && !/tag-operation-area|dispatch-plan/i.test(url)) {
          const clone = response.clone();
          const data = await clone.json();
          const record = extractRecord(data.result || data);
          if (record) rpc("/nutkings/api/tag-operation-area", {model: record.model, record_id: record.id, service_area_id: state.selectedArea, truck_id: state.selectedVan, dispatch_plan_id: state.plan?.id || false}).catch(() => {});
        }
      } catch (_) {}
      return response;
    };
  }
  async function init() {
    state.profile = cached(PROFILE_KEY);
    if (state.profile) { renderRoleStrip(); applyRoleVisibility(); ensureGuide(); updateGuideVisibility(); }
    try { state.profile = await rpc("/nutkings/api/session-profile", {}); save(PROFILE_KEY, state.profile); }
    catch (_) { if (!state.profile) return; }
    renderRoleStrip(); applyRoleVisibility(); ensureGuide(); updateGuideVisibility(); installAuthorizationGuard(); installOperationTagging();
    const observer = new MutationObserver(() => { applyRoleVisibility(); updateGuideVisibility(); });
    observer.observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:["class","aria-selected"]});
    window.addEventListener("online", () => setStatus("Connection restored. Generate or refresh suggestions for current information."));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once:true}); else init();
})();
