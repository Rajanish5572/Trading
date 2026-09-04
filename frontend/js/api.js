// Thin fetch wrapper. Every backend call goes through here so error
// handling (and, later, auth headers if you add them) lives in one place.
const Api = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(await Api._errText(res));
    return res.json();
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await Api._errText(res));
    return res.json();
  },
  async put(path, body) {
    const res = await fetch(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await Api._errText(res));
    return res.json();
  },
  async del(path) {
    const res = await fetch(path, { method: "DELETE" });
    if (!res.ok) throw new Error(await Api._errText(res));
    return res.json();
  },
  async _errText(res) {
    try {
      const j = await res.json();
      return j.detail || res.statusText;
    } catch {
      return res.statusText;
    }
  },
};
