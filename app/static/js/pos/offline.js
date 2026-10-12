// ShopDesk offline queue: stores pending sales in IndexedDB and syncs when
// the connection returns. Idempotency key is the IndexedDB primary key, so
// retrying the same key never duplicates the sale on the server.

const DB_NAME = "shopdesk";
const STORE = "pending_sales";
const DB_VERSION = 1;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "idempotency_key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueueSale(payload) {
  // payload must already have an idempotency_key (UUID).
  const db = await openDb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put({
      idempotency_key: payload.idempotency_key,
      payload,
      enqueued_at: new Date().toISOString(),
      attempts: 0,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function listPending() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function deletePending(idempotency_key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(idempotency_key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function needsReviewList() {
  // A separate object store: sales that were rejected at sync time.
  const db = await openDb();
  if (!db.objectStoreNames.contains("needs_review")) {
    return [];
  }
  return new Promise((resolve, reject) => {
    const tx = db.transaction("needs_review", "readonly");
    const req = tx.objectStore("needs_review").getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function setNeedsReview(idempotency_key, reason, payload) {
  const db = await openDb();
  if (!db.objectStoreNames.contains("needs_review")) {
    // Upgrade if needed (we open the DB at version 1 — make a tiny v2 next time).
    return;
  }
  await new Promise((resolve, reject) => {
    const tx = db.transaction("needs_review", "readwrite");
    tx.objectStore("needs_review").put({
      idempotency_key,
      reason,
      payload,
      at: new Date().toISOString(),
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function syncPending(csrfToken) {
  const items = await listPending();
  for (const item of items) {
    try {
      const r = await fetch("/api/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        credentials: "same-origin",
        body: JSON.stringify(item.payload),
      });
      if (r.ok) {
        await deletePending(item.idempotency_key);
      } else if (r.status >= 400 && r.status < 500) {
        // Server says no. Mark needs-review, keep the payload so the owner can decide.
        const body = await r.json().catch(() => ({}));
        await deletePending(item.idempotency_key);
        await setNeedsReview(item.idempotency_key, body.detail || "rejected", item.payload);
      } else {
        // 5xx or network — leave in queue.
        item.attempts = (item.attempts || 0) + 1;
      }
    } catch (e) {
      // Offline again — leave in queue.
    }
  }
}

// Public: hook the pending badge in the base.html header.
export async function updatePendingBadge() {
  const items = await listPending();
  const badge = document.getElementById("pending-badge");
  if (badge) {
    if (items.length > 0) {
      badge.textContent = "Pending: " + items.length;
      badge.classList.add("show");
    } else {
      badge.classList.remove("show");
    }
  }
}

// Register service worker and auto-sync on reconnect.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  window.addEventListener("online", () => {
    const csrf = document.cookie
      .split(";")
      .map((s) => s.trim())
      .find((c) => c.startsWith("shopdesk_csrf="))
      ?.split("=")[1];
    if (csrf) syncPending(csrf).then(updatePendingBadge);
  });
  // Initial badge.
  updatePendingBadge();
}
