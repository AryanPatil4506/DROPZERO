import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="grid min-h-[60vh] place-items-center p-8 text-center">
      <div>
        <p className="eyebrow">404</p>
        <h1 className="mt-2 text-2xl font-medium">This page doesn't exist</h1>
        <Link to="/" className="pill-ghost mt-5">Back to projects</Link>
      </div>
    </div>
  );
}
