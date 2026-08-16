"use client";

import { useState } from "react";
import { requestDevToken } from "@/lib/api/client";

export interface Session {
  token: string;
  tenantId: string;
  role: string;
  /** Prefix codes from the token's region_scope claim; empty = full access (ADR-003). */
  regionScope: string[];
}

const ROLES = ["owner", "admin", "analyst", "viewer"] as const;

/**
 * DISPATCH-2 D-4 (ADR-003, D-16): v1 console login is email + magic link.
 * /backend has no magic-link send/verify endpoints yet (out of DISPATCH-2's
 * scope for C) — so that path is shown but disabled, and says so, rather
 * than pretending to send an email it can't (05_scoring_spec.md §6's
 * "don't invent" rule applies to UI copy too, not just factor evidence).
 *
 * The working path today is ADR-003's documented dev-only escape hatch
 * (POST /v1/dev/token), which genuinely exercises tenant switching,
 * role-gated UI, and region_scope — not a mock.
 *
 * The session this yields is held in memory only by the caller (page.tsx)
 * — never write it to localStorage/sessionStorage (ADR-003 §5, D-17).
 */
export default function LoginPanel({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const [email, setEmail] = useState("");
  const [tenantId, setTenantId] = useState("tnt_demo");
  const [role, setRole] = useState<(typeof ROLES)[number]>("analyst");
  const [regionScopeInput, setRegionScopeInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitDevToken() {
    if (!tenantId.trim()) return;
    setPending(true);
    setError(null);
    try {
      const regionScope = regionScopeInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const { accessToken } = await requestDevToken({ tenantId: tenantId.trim(), role, regionScope });
      onAuthenticated({ token: accessToken, tenantId: tenantId.trim(), role, regionScope });
    } catch (err) {
      setError(err instanceof Error ? err.message : "개발용 토큰 발급에 실패했습니다.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 20,
      }}
    >
      <div style={{ width: 280 }}>
        <h2 style={{ fontSize: 15, margin: "0 0 8px" }}>로그인</h2>
        <label style={{ fontSize: 12, color: "#52514e" }}>이메일</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          style={{ width: "100%", fontSize: 13, padding: "6px 8px", margin: "4px 0 6px", boxSizing: "border-box" }}
        />
        <button
          type="button"
          disabled
          title="매직링크 발송은 아직 backend에 연결되지 않았습니다"
          style={{ width: "100%", fontSize: 13, padding: "6px 8px", opacity: 0.5, cursor: "not-allowed" }}
        >
          매직링크 받기
        </button>
        <p style={{ fontSize: 11, color: "#898781", margin: "6px 0 0" }}>
          매직링크 로그인은 준비 중입니다(backend 미구현). 지금은 아래 개발용 로그인을 쓰세요.
        </p>
      </div>

      <div style={{ width: 280, borderTop: "1px solid rgba(11, 11, 11, 0.10)", paddingTop: 16 }}>
        <h3 style={{ fontSize: 13, margin: "0 0 8px", color: "#52514e" }}>개발용 로그인 (ADR-003 임시 조치)</h3>

        <label style={{ fontSize: 12, color: "#52514e" }}>테넌트 ID</label>
        <input
          value={tenantId}
          onChange={(e) => setTenantId(e.target.value)}
          style={{ width: "100%", fontSize: 13, padding: "6px 8px", margin: "4px 0 8px", boxSizing: "border-box" }}
        />

        <label style={{ fontSize: 12, color: "#52514e" }}>역할</label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}
          style={{ width: "100%", fontSize: 13, padding: "6px 8px", margin: "4px 0 8px", boxSizing: "border-box" }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        <label style={{ fontSize: 12, color: "#52514e" }}>지역 범위 (콤마 구분 접두코드, 비우면 전체)</label>
        <input
          value={regionScopeInput}
          onChange={(e) => setRegionScopeInput(e.target.value)}
          placeholder="41, 11"
          style={{ width: "100%", fontSize: 13, padding: "6px 8px", margin: "4px 0 8px", boxSizing: "border-box" }}
        />

        <button
          type="button"
          onClick={() => void submitDevToken()}
          disabled={pending || !tenantId.trim()}
          style={{ width: "100%", fontSize: 13, padding: "6px 8px" }}
        >
          {pending ? "발급 중..." : "개발용 토큰 발급"}
        </button>

        {error && (
          <p style={{ fontSize: 12, color: "#d03b3b", marginTop: 8 }}>{error}</p>
        )}
      </div>
    </div>
  );
}
