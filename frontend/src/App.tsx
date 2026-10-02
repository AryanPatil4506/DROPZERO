import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import AppShell from "./components/AppShell";
import { getSession, storageBlocked } from "./lib/session";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import NewProject from "./pages/NewProject";
import NotFound from "./pages/NotFound";
import Projects from "./pages/Projects";
import SimulatePage from "./pages/Simulate";
import ValidationPage from "./pages/Validation";

function RequireSession() {
  const location = useLocation();
  if (!getSession() && !storageBlocked()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** The marketing landing page is static (public/landing/); "/" sends visitors there first. */
function Landing() {
  useEffect(() => {
    window.location.replace("/landing/index.html");
  }, []);
  return null;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route path="/projects" element={<Projects />} />
          <Route path="/new" element={<NewProject />} />
          <Route path="/projects/:id" element={<Dashboard />} />
          <Route path="/projects/:id/simulate" element={<SimulatePage />} />
          <Route path="/validation" element={<ValidationPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
