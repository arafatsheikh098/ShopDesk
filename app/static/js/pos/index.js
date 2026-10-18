// ShopDesk POS — Modern ES module.
// Manages cart, catalog quick-touch grid, audio feedback, barcode scanning, and offline sync.

const root = document.getElementById("pos-app");
if (!root) {
  // POS page is not active; nothing to do.
} else {
  const csrf = root.dataset.csrf;
  const products = JSON.parse(root.dataset.products || "[]");

  /** @type {Map<number, any>} */
  const byId = new Map(products.map((p) => [p.id, p]));

  /** @type {Map<string, number>} */
  const byBarcode = new Map(
    products.filter((p) => p.barcode).map((p) => [p.barcode, p.id])
  );

  /** Cart: {productId, name, unit_price, quantity} */
  const cart = new Map();

  const $ = (id) => document.getElementById(id);

  // Audio chime feedback
  let audioEnabled = true;
  const soundToggleBtn = $("pos-sound-toggle");
  if (soundToggleBtn) {
    soundToggleBtn.addEventListener("click", () => {
      audioEnabled = !audioEnabled;
      soundToggleBtn.textContent = audioEnabled ? "🔊 Sound ON" : "🔇 Sound OFF";
      soundToggleBtn.classList.toggle("secondary", audioEnabled);
    });
  }

  function playChime(success = true) {
    if (!audioEnabled) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      if (success) {
        osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
        osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.1); // A5
      } else {
        osc.frequency.setValueAtTime(300, ctx.currentTime);
        osc.frequency.setValueAtTime(200, ctx.currentTime + 0.1);
      }
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.16);
    } catch (e) {
      // Audio autoplay policy or unavailable
    }
  }

  function recompute() {
    let subtotal = 0;
    let totalQty = 0;
    for (const line of cart.values()) {
      subtotal += line.unit_price * line.quantity;
      totalQty += line.quantity;
    }
    $("subtotal").textContent = (subtotal / 100).toFixed(2);
    const kind = $("discount-kind").value;
    const v = Math.max(0, parseInt($("discount-value").value || "0", 10) || 0);
    let d = 0;
    if (kind === "percent") d = Math.floor((subtotal * Math.min(100, v)) / 100);
    else if (kind === "amount") d = Math.min(subtotal, v);
    const total = subtotal - d;
    $("total").textContent = (total / 100).toFixed(2);

    const countBadge = $("cart-item-count");
    if (countBadge) {
      countBadge.textContent = `${totalQty} item${totalQty === 1 ? "" : "s"}`;
    }

    const emptyState = $("cart-empty-state");
    if (emptyState) {
      emptyState.style.display = cart.size === 0 ? "block" : "none";
    }

    return { subtotal, discount: d, total };
  }

  function render() {
    const tbody = document.querySelector("#cart tbody");
    tbody.innerHTML = "";
    for (const line of cart.values()) {
      const tr = document.createElement("tr");

      const tdN = document.createElement("td");
      tdN.style.fontWeight = "600";
      tdN.textContent = line.name;

      const tdQ = document.createElement("td");
      const qInp = document.createElement("input");
      qInp.type = "number";
      qInp.min = "1";
      qInp.value = String(line.quantity);
      qInp.style.width = "3.8em";
      qInp.onchange = () => {
        const q = Math.max(1, parseInt(qInp.value, 10) || 1);
        line.quantity = q;
        render();
      };
      tdQ.appendChild(qInp);

      const tdU = document.createElement("td");
      tdU.style.fontFamily = "var(--font-mono)";
      tdU.textContent = (line.unit_price / 100).toFixed(2);

      const tdT = document.createElement("td");
      tdT.style.fontFamily = "var(--font-mono)";
      tdT.style.fontWeight = "700";
      tdT.textContent = ((line.unit_price * line.quantity) / 100).toFixed(2);

      const tdX = document.createElement("td");
      const rm = document.createElement("button");
      rm.className = "btn danger";
      rm.textContent = "x";
      rm.title = "Remove item";
      rm.onclick = () => {
        cart.delete(line.productId);
        render();
      };
      tdX.appendChild(rm);

      tr.append(tdN, tdQ, tdU, tdT, tdX);
      tbody.appendChild(tr);
    }
    recompute();
  }

  function addByBarcode(barcode) {
    const pid = byBarcode.get(barcode);
    if (pid !== undefined) {
      addToCart(pid);
      return true;
    }
    return false;
  }

  function addToCart(productId) {
    const p = byId.get(productId);
    if (!p) return;
    const existing = cart.get(p.id);
    if (existing) {
      existing.quantity += 1;
    } else {
      cart.set(p.id, {
        productId: p.id,
        name: p.name,
        unit_price: p.sell_price,
        quantity: 1,
      });
    }
    playChime(true);
    render();
  }

  // --- Visual Catalog Grid & Category Filter ---
  let selectedCategory = "all";

  function setupCatalog() {
    const chipsContainer = $("category-chips");
    const gridContainer = $("product-grid");
    if (!gridContainer) return;

    // Extract unique categories
    const categories = new Set();
    for (const p of products) {
      if (p.category) categories.add(p.category);
    }

    if (chipsContainer) {
      for (const cat of categories) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "category-chip";
        btn.dataset.cat = cat;
        btn.textContent = cat;
        btn.onclick = () => {
          document.querySelectorAll(".category-chip").forEach((c) => c.classList.remove("active"));
          btn.classList.add("active");
          selectedCategory = cat;
          filterCatalog();
        };
        chipsContainer.appendChild(btn);
      }

      const allBtn = chipsContainer.querySelector('[data-cat="all"]');
      if (allBtn) {
        allBtn.onclick = () => {
          document.querySelectorAll(".category-chip").forEach((c) => c.classList.remove("active"));
          allBtn.classList.add("active");
          selectedCategory = "all";
          filterCatalog();
        };
      }
    }

    filterCatalog();
  }

  function filterCatalog() {
    const gridContainer = $("product-grid");
    if (!gridContainer) return;
    gridContainer.innerHTML = "";

    const query = ($("barcode") ? $("barcode").value.trim().toLowerCase() : "");

    const filtered = products.filter((p) => {
      const matchCat = selectedCategory === "all" || p.category === selectedCategory;
      if (!matchCat) return false;
      if (!query) return true;
      return (
        p.name.toLowerCase().includes(query) ||
        p.sku.toLowerCase().includes(query) ||
        (p.barcode && p.barcode.toLowerCase().includes(query))
      );
    });

    if (filtered.length === 0) {
      gridContainer.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-muted);">No products match filter</div>';
      return;
    }

    for (const p of filtered) {
      const card = document.createElement("div");
      card.className = "product-item-card";
      card.onclick = () => addToCart(p.id);

      let stockClass = "stock-ok";
      if (p.stock <= 0) stockClass = "stock-out";
      else if (p.stock <= 10) stockClass = "stock-low";

      card.innerHTML = `
        <div class="product-card-top">
          <div>
            <div class="product-card-name">${p.name}</div>
            <div class="product-card-sku">${p.sku}</div>
          </div>
          <span class="product-card-stock ${stockClass}">${p.stock} ${p.unit || ''}</span>
        </div>
        <div class="product-card-bottom">
          <span class="product-card-price">৳${(p.sell_price / 100).toFixed(2)}</span>
          <button type="button" class="btn btn-sm" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;">+ Add</button>
        </div>
      `;
      gridContainer.appendChild(card);
    }
  }

  // --- Barcode / Search Input Handler ---
  const barcodeInp = $("barcode");
  if (barcodeInp) {
    barcodeInp.addEventListener("input", () => {
      filterCatalog();
    });

    barcodeInp.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        const v = ev.target.value.trim();
        if (!v) return;
        if (!addByBarcode(v)) {
          // fall back to search by name/sku
          const matches = products.filter(
            (p) =>
              p.sku === v ||
              (p.name || "").toLowerCase().includes(v.toLowerCase())
          );
          if (matches.length === 1) {
            addToCart(matches[0].id);
          } else if (matches.length > 1) {
            addToCart(matches[0].id);
          } else {
            playChime(false);
          }
        }
        ev.target.value = "";
        filterCatalog();
      }
    });
  }

  // Discount & Payment Listeners
  $("discount-kind").addEventListener("change", recompute);
  $("discount-value").addEventListener("input", recompute);

  document.querySelectorAll(".discount-quick-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pct = btn.dataset.pct;
      if (pct === "0") {
        $("discount-kind").value = "none";
        $("discount-value").value = "0";
      } else {
        $("discount-kind").value = "percent";
        $("discount-value").value = pct;
      }
      recompute();
    });
  });

  // Quick Tender buttons
  const tenderExact = $("tender-exact");
  if (tenderExact) {
    tenderExact.addEventListener("click", () => {
      const { total } = recompute();
      $("paid").value = (total / 100).toFixed(2);
    });
  }

  document.querySelectorAll(".quick-tender-chip[data-add]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const add = parseInt(btn.dataset.add, 10) || 0;
      const current = parseFloat($("paid").value || "0") || 0;
      $("paid").value = (current + add).toFixed(2);
    });
  });

  // Keyboard Shortcuts
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "F2") {
      ev.preventDefault();
      $("barcode")?.focus();
    } else if (ev.key === "F4") {
      ev.preventDefault();
      $("paid")?.focus();
    }
  });

  // Finish Sale Click Handler
  $("finish").addEventListener("click", async () => {
    if (cart.size === 0) {
      $("msg").textContent = "cart is empty";
      playChime(false);
      return;
    }
    const { subtotal, discount, total } = recompute();
    const lines = [...cart.values()].map((l) => ({
      product_id: l.productId,
      quantity: l.quantity,
      unit_price: l.unit_price,
    }));
    const payment_method = $("payment-method").value;
    const paid_minor = Math.round(parseFloat($("paid").value || "0") * 100);
    const customer_name = $("customer-name").value.trim();
    const customer_phone = $("customer-phone").value.trim();
    const idempotency_key = crypto.randomUUID();
    const payload = {
      idempotency_key,
      lines,
      discount_minor: discount,
      payment_method,
      paid_minor: payment_method === "due" ? 0 : paid_minor,
      customer_name: customer_name || undefined,
      customer_phone: customer_phone || undefined,
    };
    let r;
    try {
      r = await fetch("/api/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(payload),
        credentials: "same-origin",
      });
    } catch (e) {
      // Network error — queue for sync.
      const { enqueueSale, updatePendingBadge } = await import("/static/js/pos/offline.js");
      await enqueueSale(payload);
      await updatePendingBadge();
      $("msg").textContent = "queued (offline) — sale will sync";
      playChime(true);
      cart.clear();
      render();
      return;
    }
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      $("msg").textContent = "error: " + (body.detail || r.status);
      playChime(false);
      return;
    }
    $("msg").textContent =
      "sale " + body.sale_number + " total " + (body.total / 100).toFixed(2);
    playChime(true);
    cart.clear();
    render();
    // Re-fetch products so stock counts are fresh.
    location.reload();
  });

  $("search-sale").addEventListener("click", async () => {
    const q = $("sale-search").value.trim();
    if (!q) return;
    const resultBox = $("sale-result");
    resultBox.style.display = "block";
    resultBox.textContent = "Searching...";

    const r = await fetch("/api/sales/" + encodeURIComponent(q), {
      credentials: "same-origin",
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      resultBox.textContent = "Sale not found";
      return;
    }
    const lines = (body.lines || [])
      .map(
        (l) =>
          `• ${l.product_name} × ${l.quantity} @ ৳${(l.unit_price / 100).toFixed(2)}`
      )
      .join("<br>");
    resultBox.innerHTML =
      `<div style="font-size: 1rem; margin-bottom: 0.35rem;"><b>Sale #${body.sale_number}</b> &nbsp;<span class="badge badge-success">${body.status}</span></div>` +
      `<div>Total: <b>৳${(body.total / 100).toFixed(2)}</b></div>` +
      `<div style="margin: 0.5rem 0; font-size: 0.825rem; color: var(--text-secondary);">${lines}</div>` +
      `<a class="btn btn-sm" href="/invoices/${body.sale_number}.pdf" target="_blank" style="margin-top: 0.5rem;">📄 Download Invoice PDF</a>`;
  });

  setupCatalog();
  render();
}
