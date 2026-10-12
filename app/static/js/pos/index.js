// ShopDesk POS — minimal ES module. Reads the product list from a data attr,
// manages a cart, and POSTs the sale to /api/sales.

const root = document.getElementById("pos-app");
if (!root) {
  // The POS page is not active; nothing to do.
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

  function recompute() {
    let subtotal = 0;
    for (const line of cart.values()) {
      subtotal += line.unit_price * line.quantity;
    }
    $("subtotal").textContent = (subtotal / 100).toFixed(2);
    const kind = $("discount-kind").value;
    const v = Math.max(0, parseInt($("discount-value").value || "0", 10) || 0);
    let d = 0;
    if (kind === "percent") d = Math.floor((subtotal * Math.min(100, v)) / 100);
    else if (kind === "amount") d = Math.min(subtotal, v);
    const total = subtotal - d;
    $("total").textContent = (total / 100).toFixed(2);
    return { subtotal, discount: d, total };
  }

  function render() {
    const tbody = document.querySelector("#cart tbody");
    tbody.innerHTML = "";
    for (const line of cart.values()) {
      const tr = document.createElement("tr");
      const tdN = document.createElement("td");
      tdN.textContent = line.name;
      const tdQ = document.createElement("td");
      const qInp = document.createElement("input");
      qInp.type = "number";
      qInp.min = "1";
      qInp.value = String(line.quantity);
      qInp.style.width = "4em";
      qInp.onchange = () => {
        const q = Math.max(1, parseInt(qInp.value, 10) || 1);
        line.quantity = q;
        render();
      };
      tdQ.appendChild(qInp);
      const tdU = document.createElement("td");
      tdU.textContent = (line.unit_price / 100).toFixed(2);
      const tdT = document.createElement("td");
      tdT.textContent = ((line.unit_price * line.quantity) / 100).toFixed(2);
      const tdX = document.createElement("td");
      const rm = document.createElement("button");
      rm.className = "btn danger";
      rm.textContent = "x";
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
    render();
  }

  $("barcode").addEventListener("keydown", (ev) => {
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
          // add the first match
          addToCart(matches[0].id);
        }
      }
      ev.target.value = "";
    }
  });

  $("discount-kind").addEventListener("change", recompute);
  $("discount-value").addEventListener("input", recompute);

  $("finish").addEventListener("click", async () => {
    if (cart.size === 0) {
      $("msg").textContent = "cart is empty";
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
      cart.clear();
      render();
      return;
    }
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      $("msg").textContent = "error: " + (body.detail || r.status);
      return;
    }
    $("msg").textContent =
      "sale " + body.sale_number + " total " + (body.total / 100).toFixed(2);
    cart.clear();
    render();
    // Re-fetch products so stock counts are fresh.
    location.reload();
  });

  $("search-sale").addEventListener("click", async () => {
    const q = $("sale-search").value.trim();
    if (!q) return;
    const r = await fetch("/api/sales/" + encodeURIComponent(q), {
      credentials: "same-origin",
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      $("sale-result").textContent = "not found";
      return;
    }
    const lines = (body.lines || [])
      .map(
        (l) =>
          `${l.product_name} x${l.quantity} @ ${(l.unit_price / 100).toFixed(2)}`
      )
      .join("<br>");
    $("sale-result").innerHTML =
      `<b>${body.sale_number}</b> total ${(body.total / 100).toFixed(2)}` +
      ` status ${body.status}<br>${lines}` +
      `<br><a class="btn" href="/invoices/${body.sale_number}.pdf">Invoice PDF</a>`;
  });

  render();
}
