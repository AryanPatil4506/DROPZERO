import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { startSession } from "../lib/session";
import collage from "./login-collage.html?raw";
import "./login.css";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function Logo({ fill, stroke }: { fill: string; stroke: string }) {
  return (
    <svg className="logo-mark" viewBox="0 0 24 24" aria-hidden>
      <rect width="24" height="24" rx="6" fill={fill} />
      <path d="M4 7h4.5c2.2 0 2.9 1.4 3.8 3.6l1.2 3c.7 1.8 1.4 2.4 3 2.4H20" fill="none" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12.4" cy="10.6" r="1.9" fill={stroke} />
    </svg>
  );
}

/**
 * Demo sign-in: there is no auth backend yet (CONTRACT_REQUESTS.md), so any valid email and a
 * non-empty password start a session for this browser tab. Nothing is sent or stored.
 */
export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const value = email.trim();
    const next = {
      email: !value ? "Enter your email." : !EMAIL.test(value) ? "That doesn't look like an email address." : undefined,
      password: password ? undefined : "Enter your password.",
    };
    setErrors(next);
    setNotice(null);
    if (next.email) return document.getElementById("email")?.focus();
    if (next.password) return document.getElementById("password")?.focus();
    setBusy(true);
    // TODO(auth): POST /api/auth/login once the backend has accounts (CONTRACT_REQUESTS.md).
    setTimeout(() => {
      startSession(value);
      navigate(from, { replace: true });
    }, 450);
  };

  return (
    <div className="login-page">
      <main className="page">
        <section className="visual">
          <a className="brand" href="/landing/index.html" aria-label="DROPZERO home">
            <Logo fill="#ffffff" stroke="#ff5b1f" />
            <span>DROPZERO</span>
          </a>
          <div className="streaks" aria-hidden>
            <span className="streak s1" />
            <span className="streak s2" />
            <span className="streak s3" />
          </div>
          {/* static decorative markup, no user data */}
          <div className="collage" aria-hidden dangerouslySetInnerHTML={{ __html: collage }} />
          <p className="visual-note">Illustrative report · values are examples</p>
        </section>

        <section className="auth">
          <a className="brand brand-mobile" href="/landing/index.html" aria-label="DROPZERO home">
            <Logo fill="#ff5b1f" stroke="#0a0a0b" />
            <span>DROPZERO</span>
          </a>

          <form className="form" onSubmit={onSubmit} noValidate>
            <h1>Sign in to DROPZERO</h1>

            <div className="field">
              <label className="sr-only" htmlFor="email">Email</label>
              <input
                className="input"
                id="email"
                type="email"
                placeholder="Email"
                autoComplete="email"
                inputMode="email"
                value={email}
                aria-invalid={!!errors.email}
                aria-describedby="email-error"
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (errors.email) setErrors((x) => ({ ...x, email: undefined }));
                }}
              />
              <p className="error" id="email-error" hidden={!errors.email}>{errors.email}</p>
            </div>

            <div className="field">
              <label className="sr-only" htmlFor="password">Password</label>
              <div className="input-wrap">
                <input
                  className="input"
                  id="password"
                  type={show ? "text" : "password"}
                  placeholder="Password"
                  autoComplete="current-password"
                  value={password}
                  aria-invalid={!!errors.password}
                  aria-describedby="password-error"
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (errors.password) setErrors((x) => ({ ...x, password: undefined }));
                  }}
                />
                <button className="eye" type="button" aria-label={show ? "Hide password" : "Show password"} aria-pressed={show} onClick={() => setShow((s) => !s)}>
                  <svg className="eye-closed" viewBox="0 0 20 20" aria-hidden>
                    <path d="M3 3l14 14M8.6 8.7a2 2 0 002.8 2.8M6.2 6.3C4.3 7.5 3 10 3 10s2.6 5 7 5c1.4 0 2.6-.4 3.6-1M10 5c4.4 0 7 5 7 5s-.6 1.2-1.7 2.4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <svg className="eye-open" viewBox="0 0 20 20" aria-hidden>
                    <path d="M3 10s2.6-5 7-5 7 5 7 5-2.6 5-7 5-7-5-7-5z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                    <circle cx="10" cy="10" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                </button>
              </div>
              <p className="error" id="password-error" hidden={!errors.password}>{errors.password}</p>
            </div>

            <div className="row">
              <label className="check">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                <span className="check-box" aria-hidden />
                Remember me
              </label>
              <a
                className="link-muted"
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setNotice("Password reset isn't available yet — it arrives with accounts.");
                }}
              >
                Forgot password?
              </a>
            </div>

            <button className="submit" type="submit" aria-busy={busy} disabled={busy}>
              <span className="submit-label">Sign in</span>
              <span className="spinner" aria-hidden />
            </button>

            <p className="notice" role="status" hidden={!notice}>{notice}</p>
            <p className="demo-note">Demo sign-in: accounts aren't connected yet, so any email and password open the app. Nothing is sent or stored.</p>

            <p className="signup">
              Don't have an account? <a href="/landing/index.html#start">Sign up now</a>
            </p>
          </form>
        </section>
      </main>
    </div>
  );
}
