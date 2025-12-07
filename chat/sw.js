const CACHE_NAME = "chat-pwa-cache-v1";
const OFFLINE_URL = "/chat/index.html";
const ASSETS = [
  "/chat/",
  "/chat/index.html",
  "/chat/app.webmanifest",
  "/chat/sw.js",
  "/chat/icons/icon-192.png",
  "/chat/icons/icon-512.png"
];

const DB_NAME = "chat-sync";
const STORE_NAME = "queue";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method === "GET" && request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  if (request.method === "GET" && request.url.startsWith(self.location.origin + "/chat")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetchAndCache(request))
    );
  }
});

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "queue-chat") {
    event.waitUntil(handleQueueChat(data));
  } else if (data.type === "flush-queue") {
    event.waitUntil(flushQueue());
  }
});

self.addEventListener("sync", (event) => {
  if (event.tag === "chat-sync") {
    event.waitUntil(flushQueue());
  }
});

async function fetchAndCache(request) {
  const response = await fetch(request);
  if (response && response.ok) {
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
  }
  return response;
}

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function addToQueue(item) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).add(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getQueue() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function deleteFromQueue(id) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function handleQueueChat(data) {
  const record = {
    kind: data.kind,
    backendBase: data.backendBase,
    headers: data.headers || {},
    payload: data.payload || {},
    placeholderId: data.placeholderId || null,
    conversationId: data.conversationId || null,
    clientMessageId: data.clientMessageId || null,
    createdAt: Date.now()
  };
  await addToQueue(record);
  try {
    if ("sync" in self.registration) {
      await self.registration.sync.register("chat-sync");
    } else {
      await flushQueue();
    }
  } catch (err) {
    await notifyClients("queue-error", { message: "Sync registration failed." });
  }
  await notifyClients("queue-status", { message: "Queued message for background sync." });
}

async function flushQueue() {
  const items = await getQueue();
  if (!items.length) {
    return;
  }
  const placeholderMap = {};
  for (const item of items) {
    try {
      let conversationId = item.conversationId;
      if (item.placeholderId && placeholderMap[item.placeholderId]) {
        conversationId = placeholderMap[item.placeholderId];
      }

      let url = "";
      if (item.kind === "start") {
        url = `${item.backendBase}/v1/widget/start`;
      } else if (item.kind === "message") {
        const resolved = conversationId || placeholderMap[item.placeholderId];
        if (!resolved) {
          // Start message not processed yet; retry later
          continue;
        }
        conversationId = resolved;
        url = `${item.backendBase}/v1/widget/${conversationId}/message`;
      } else {
        continue;
      }

      const res = await fetch(url, {
        method: "POST",
        headers: item.headers || {},
        body: JSON.stringify(item.payload || {})
      });
      if (!res.ok) {
        throw new Error(`status ${res.status}`);
      }
      const data = await res.json();
      const replyText = data.reply_text || data.replyText;
      const resolvedConversationId =
        data.conversation_id || data.conversationId || conversationId || item.placeholderId;
      if (item.placeholderId && resolvedConversationId) {
        placeholderMap[item.placeholderId] = resolvedConversationId;
      }
      await deleteFromQueue(item.id);
      await notifyClients("chat-response", {
        conversationId: resolvedConversationId,
        replyText,
        clientMessageId: item.clientMessageId
      });
    } catch (err) {
      await notifyClients("queue-error", {
        message: "Background sync failed; will retry when connection is back."
      });
      throw err;
    }
  }
  await notifyClients("queue-status", { message: "" });
}

async function notifyClients(type, payload) {
  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage({ type, ...payload });
  }
}
