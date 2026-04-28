import { useState } from "react";
import { getAuthToken, setAuthToken } from "../api/client";

export function TokenBanner() {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const current = getAuthToken();

  if (editing) {
    return (
      <div className="banner">
        <input
          type="password"
          placeholder="Paste CAVE auth token"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button onClick={() => { setAuthToken(draft.trim() || null); setEditing(false); setDraft(""); window.location.reload(); }}>
          Save
        </button>
        <button onClick={() => setEditing(false)}>Cancel</button>
      </div>
    );
  }

  return (
    <div className="banner">
      <span>Auth: {current ? "Bearer token set" : "cookie / dev bypass"}</span>
      <button onClick={() => setEditing(true)}>{current ? "Change" : "Paste token"}</button>
      {current && (
        <button onClick={() => { setAuthToken(null); window.location.reload(); }}>
          Clear
        </button>
      )}
    </div>
  );
}
